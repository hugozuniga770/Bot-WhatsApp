"""Coexistencia del número del WhatsApp Business (v3.4). Requisitos BOT-RF-36 a BOT-RF-39."""
from datetime import timedelta

import pytest

from bot import coexistencia as X
from bot import reglas
from bot.cifrado import Cifrador
from bot.servicios import AVISO, DUPLICADO, ECO, PAUSADO
from conftest import CLIENTE, SECRETO_META, TOKEN

WABA = "102938475610293"
NUMERO_REAL = "765432109876543"   # Phone number ID del número del negocio (inventado)
NUMERO_PRUEBA = "1352450434628435"
TOKEN_NEGOCIO = "EAANEGOCIO" + "n" * 80


def _aviso_waba(campo, valor, pnid=NUMERO_REAL, waba=WABA):
    return {"object": "whatsapp_business_account", "entry": [{"id": waba, "changes": [{
        "field": campo, "value": {"messaging_product": "whatsapp", "metadata": {"phone_number_id": pnid}, **valor}}]}]}


def _eco(id_, a, texto):
    return _aviso_waba("smb_message_echoes", {"message_echoes": [
        {"from": "59175000000", "to": a, "id": id_, "timestamp": "1", "type": "text", "text": {"body": texto}}]})


# ------------------------------------------------------------------ reglas
def test_RF37_extrae_lo_que_el_negocio_escribe_desde_el_celular():
    ecos = reglas.extraer_ecos(_eco("wamid.eco1", "+591 7000 0001", " Hola, soy Rosa "))
    assert ecos == [reglas.EcoDelNegocio("wamid.eco1", "59170000001", "text", "Hola, soy Rosa")]
    # Los ecos no son mensajes de clientes, y los de otro número no se toman
    assert reglas.extraer_mensajes(_eco("wamid.eco1", "59170000001", "x")) == []
    assert reglas.extraer_ecos(_eco("e", "59170000001", "x"), {"whatsapp": "999999"}) == []


def test_RF38_avisos_de_historial_contactos_y_cuenta():
    historial = _aviso_waba("history", {"history": [{"metadata": {"phase": 0, "chunk_order": 1, "progress": 100}, "threads": [
        {"id": "59170000001", "messages": [{"from": "59170000001", "id": "h1", "type": "text", "text": {"body": "privado"}}]}]}]})
    apagado = _aviso_waba("history", {"errors": [{"code": 2593109, "title": "History sync is turned off"}]})
    contactos = _aviso_waba("smb_app_state_sync", {"state_sync": [{"type": "contact", "contact": {"phone_number": "59170000001"}, "action": "add"}] * 3})
    baja = {"object": "whatsapp_business_account", "entry": [{"id": WABA, "changes": [{"field": "account_update", "value": {
        "phone_number": "59175000000", "event": "PARTNER_REMOVED", "disconnection_info": {"reason": "PRIMARY_INACTIVITY", "initiated_by": "SYSTEM"}}}]}]}
    assert reglas.extraer_avisos_coexistencia(historial) == [{"campo": "history", "fase": 0, "progreso": 100, "error": None}]
    assert reglas.extraer_avisos_coexistencia(apagado)[0]["error"] == 2593109
    assert reglas.extraer_avisos_coexistencia(contactos) == [{"campo": "smb_app_state_sync", "contactos": 3}]
    assert reglas.extraer_avisos_coexistencia(baja) == [{"campo": "account_update", "evento": "PARTNER_REMOVED",
                                                         "motivo": "PRIMARY_INACTIVITY", "quien": "SYSTEM"}]
    # De otra cuenta de WhatsApp, no
    assert reglas.extraer_avisos_coexistencia(baja, {"waba": "111111111"}) == []
    assert "14 días" in X.texto_aviso_de_cuenta("PARTNER_REMOVED", "PRIMARY_INACTIVITY", "SYSTEM")


def test_RF39_cada_sincronizacion_una_vez_en_orden_y_dentro_de_24_horas(ahora):
    conectada = {"estado": "conectada", "conectada": ahora.isoformat(), "sincronizacion": {}}
    assert X.puede_sincronizar(conectada, "smb_app_state_sync", ahora)[0]
    assert "Primero hay que sincronizar los contactos" in X.puede_sincronizar(conectada, "history", ahora)[1]
    hecha = {**conectada, "sincronizacion": {"smb_app_state_sync": {"request_id": "r1"}}}
    assert "una sola vez" in X.puede_sincronizar(hecha, "smb_app_state_sync", ahora)[1]
    assert X.puede_sincronizar(hecha, "history", ahora)[0]
    assert "24 horas" in X.puede_sincronizar(hecha, "history", ahora + timedelta(hours=25))[1]
    assert not X.puede_sincronizar({"estado": "sin_conectar"}, "smb_app_state_sync", ahora)[0]


# ------------------------------------------------------------------ atención
def test_RF37_si_la_duena_responde_a_mano_el_bot_se_calla_en_ese_chat(servicios, almacen, empresa, mensaje, whatsapp, ahora):
    eco = reglas.EcoDelNegocio("wamid.eco1", CLIENTE, "text", "Hola, le escribo yo")
    assert servicios.registrar_eco(empresa, eco, ahora) == ECO
    assert servicios.registrar_eco(empresa, eco, ahora) == DUPLICADO  # Meta puede repetirlo
    assert almacen.historial(empresa["id"], CLIENTE)[-1] == {"role": "assistant", "content": "Hola, le escribo yo"}
    # Un aviso en la Actividad, una sola vez aunque siga respondiendo
    servicios.registrar_eco(empresa, reglas.EcoDelNegocio("wamid.eco2", CLIENTE, "image"), ahora)
    manuales = [e for e in almacen.eventos(empresa["id"], 10) if e["tipo"] == "manual"]
    assert len(manuales) == 1 and "respondió a mano a ...0001" in manuales[0]["detalle"] and "12 h" in manuales[0]["detalle"]
    assert "[Rosa mandó una foto desde el WhatsApp Business]" in almacen.historial(empresa["id"], CLIENTE)[-1]["content"]
    # Y el cliente que vuelve a escribir no recibe respuesta del bot
    assert servicios.atender(empresa, mensaje("¿Y el precio?"), ahora + timedelta(minutes=5)) == PAUSADO
    assert whatsapp.enviados == []


def test_RF38_la_actividad_cuenta_el_historial_y_avisa_la_desconexion(servicios, almacen, empresa, ahora):
    empresa = almacen.actualizar_empresa(empresa["id"], {"coexistencia": {"estado": "conectada", "waba_id": WABA}}, ahora)
    assert servicios.registrar_aviso_coexistencia(empresa, {"campo": "history", "fase": 0, "progreso": 40, "error": None}, ahora) == AVISO
    servicios.registrar_aviso_coexistencia(empresa, {"campo": "history", "fase": 0, "progreso": 100, "error": None}, ahora)
    servicios.registrar_aviso_coexistencia(empresa, {"campo": "history", "fase": 0, "progreso": 100, "error": None}, ahora)
    servicios.registrar_aviso_coexistencia(empresa, {"campo": "history", "fase": None, "progreso": None, "error": 2593109}, ahora)
    servicios.registrar_aviso_coexistencia(empresa, {"campo": "account_update", "evento": "PARTNER_REMOVED",
                                                     "motivo": "PRIMARY_INACTIVITY", "quien": "SYSTEM"}, ahora)
    detalles = [e["detalle"] for e in almacen.eventos(empresa["id"], 20)]
    assert sum("historial recibido (parte 1 de 3)" in d for d in detalles) == 1
    assert any("eligió no compartir el historial" in d for d in detalles)
    assert any("no se abrió en unos 14 días" in d for d in detalles)
    assert almacen.empresa(empresa["id"])["coexistencia"]["estado"] == "desconectada"
    # No se guarda el contenido del historial (D-42)
    assert almacen.historial(empresa["id"], CLIENTE) == []


# ------------------------------------------------------------------ webhook
def test_RF37_webhook_con_un_eco_firmado_pausa_el_chat(web, almacen, empresa, config, firmar, ahora):
    almacen.actualizar_empresa(empresa["id"], {"meta_app_secret_cif": Cifrador(config.clave_maestra).cifrar(SECRETO_META),
                                               "phone_number_id": NUMERO_REAL}, ahora)
    cuerpo, firma = firmar(_eco("wamid.eco9", CLIENTE, "Le atiendo yo"))
    r = web.post(f"/webhook/{empresa['slug']}", data=cuerpo, headers={"X-Hub-Signature-256": firma, "Content-Type": "application/json"})
    assert r.status_code == 200
    assert almacen.pausado_hasta(empresa["id"], CLIENTE) is not None


# ------------------------------------------------------------------ registro (llamadas a Meta)
class Respuesta:
    def __init__(self, datos=None, ok=True):
        self._datos, self.ok, self.status_code, self.text = datos or {}, ok, 200 if ok else 400, ""

    def json(self):
        return self._datos


class SesionFalsa:
    def __init__(self, respuestas):
        self.pedidos, self.respuestas = [], respuestas

    def request(self, metodo, url, **kw):
        self.pedidos.append((metodo, url, kw))
        return next((r for ruta, r in self.respuestas.items() if ruta in url), Respuesta({"success": True}))


def test_RF36_registro_canjea_el_codigo_sincroniza_y_nunca_registra_el_numero():
    sesion = SesionFalsa({"oauth/access_token": Respuesta({"access_token": TOKEN_NEGOCIO}),
                          "smb_app_data": Respuesta({"messaging_product": "whatsapp", "request_id": "req-1"})})
    registro = X.Registro("v23.0", sesion=sesion)
    assert registro.canjear_codigo("123456", SECRETO_META, "CODIGO") == (True, TOKEN_NEGOCIO)
    metodo, url, kw = sesion.pedidos[0]
    assert url.endswith("/v23.0/oauth/access_token") and kw["params"] == {"client_id": "123456", "client_secret": SECRETO_META, "code": "CODIGO"}
    assert registro.sincronizar(NUMERO_REAL, TOKEN_NEGOCIO, "smb_app_state_sync") == (True, "req-1")
    metodo, url, kw = sesion.pedidos[-1]
    assert (metodo, kw["json"]) == ("POST", {"messaging_product": "whatsapp", "sync_type": "smb_app_state_sync"})
    assert kw["headers"] == {"Authorization": f"Bearer {TOKEN_NEGOCIO}"} and TOKEN_NEGOCIO not in url
    with pytest.raises(ValueError):
        registro._pedir("POST", f"{NUMERO_REAL}/register", TOKEN_NEGOCIO)
    assert X.elegir_numero([{"id": "1", "is_on_biz_app": False}, {"id": "2", "is_on_biz_app": True}]) == {"id": "2", "is_on_biz_app": True}


# ------------------------------------------------------------------ panel
class RegistroFalso:
    def __init__(self, en_la_app=True, codigo_ok=True):
        self.llamadas, self.en_la_app, self.codigo_ok = [], en_la_app, codigo_ok

    def canjear_codigo(self, app_id, app_secret, codigo):
        self.llamadas.append(("codigo", codigo))
        return (True, TOKEN_NEGOCIO) if self.codigo_ok else (False, "Meta respondió: el código venció")

    def wabas_del_token(self, app_id, app_secret, token):
        self.llamadas.append(("wabas", token))
        return True, list(getattr(self, "wabas", [WABA]))

    def numeros_de(self, waba_id, token):
        self.llamadas.append(("numeros", waba_id))
        return True, [{"id": NUMERO_REAL, "display_phone_number": "+591 75000000", "verified_name": "Tienda", "is_on_biz_app": self.en_la_app}]

    def numero(self, pnid, token):
        self.llamadas.append(("numero", pnid))
        return True, {"id": pnid, "display_phone_number": "+591 75000000", "verified_name": "Tienda de Prueba",
                      "is_on_biz_app": self.en_la_app, "platform_type": "CLOUD_API"}

    def suscribir_waba(self, waba_id, token):
        self.llamadas.append(("waba", waba_id, token))
        return True, "La cuenta de WhatsApp avisa al bot."

    def sincronizar(self, pnid, token, tipo):
        self.llamadas.append(("sync", tipo, pnid, token))
        return True, f"req-{tipo}"


class ConectorFalso:
    def __init__(self):
        self.llamadas = []

    def suscribir_app(self, app_id, app_secret, objeto, campos, callback, verify_token):
        self.llamadas.append((objeto, campos, callback))
        return True, "Webhook registrado."


@pytest.fixture
def con_llaves(almacen, empresa, config, ahora):
    cif = Cifrador(config.clave_maestra)
    return almacen.actualizar_empresa(empresa["id"], {
        "meta_app_id": "123456", "meta_app_secret_cif": cif.cifrar(SECRETO_META), "whatsapp_token_cif": cif.cifrar(TOKEN),
        "phone_number_id": NUMERO_PRUEBA, "estado": "revision", "coexistencia": {"config_id": "998877665544"}}, ahora)


def test_RF36_la_pantalla_pide_sesion_y_carga_meta_solo_ahi(web, admin, con_llaves):
    assert web.get(f"/panel/empresas/{con_llaves['id']}/coexistencia").status_code in (200, 302)
    cliente, _ = admin
    r = cliente.get(f"/panel/empresas/{con_llaves['id']}/coexistencia")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Conectar el WhatsApp Business de Rosa" in html and 'data-config-id="998877665544"' in html
    assert "connect.facebook.net" in r.headers["Content-Security-Policy"]
    assert "connect.facebook.net" not in cliente.get(f"/panel/empresas/{con_llaves['id']}").headers["Content-Security-Policy"]
    assert "WhatsApp para Windows" in html and "Agregar número de teléfono" in html


def test_RF36_sin_sesion_no_se_ve_ni_se_conecta(web, con_llaves):
    nuevo = web.__class__(web.application)
    assert nuevo.get(f"/panel/empresas/{con_llaves['id']}/coexistencia").status_code == 302
    assert nuevo.post(f"/panel/empresas/{con_llaves['id']}/coexistencia/finalizar", json={}).status_code == 302


def test_RF36_conectar_cambia_al_numero_del_negocio_y_sincroniza_en_orden(app, admin, almacen, con_llaves, config):
    registro = app.extensions["bot"].registro = RegistroFalso()
    conector = app.extensions["bot"].conector = ConectorFalso()
    web, csrf = admin
    r = web.post(f"/panel/empresas/{con_llaves['id']}/coexistencia/finalizar", json={"code": "CODIGO", "waba_id": WABA},
                 headers={"X-CSRF": csrf})
    datos = r.get_json()
    assert datos["ok"] and all(p["estado"] == "ok" for p in datos["pasos"])
    guardada = almacen.empresa(con_llaves["id"])
    x = guardada["coexistencia"]
    assert guardada["phone_number_id"] == NUMERO_REAL
    assert Cifrador(config.clave_maestra).descifrar(guardada["whatsapp_token_cif"]) == TOKEN_NEGOCIO
    assert (x["estado"], x["waba_id"], x["numero"]) == ("conectada", WABA, "+591 75000000")
    assert x["prueba"]["phone_number_id"] == NUMERO_PRUEBA  # para poder volver
    assert TOKEN_NEGOCIO not in str(x)
    # Los campos del webhook antes que las sincronizaciones, y contactos antes que historial
    assert conector.llamadas == [("whatsapp_business_account", X.CAMPOS_WABA, f"https://bot.test/webhook/{con_llaves['slug']}")]
    assert [c[1] for c in registro.llamadas if c[0] == "sync"] == ["smb_app_state_sync", "history"]
    assert set(x["sincronizacion"]) == {"smb_app_state_sync", "history"}
    # La empresa sigue en prueba: no se activa sola
    assert guardada["estado"] == "revision"
    # Sincronizar otra vez no vuelve a pedir nada a Meta
    web.post(f"/panel/empresas/{con_llaves['id']}/coexistencia/sincronizar", data={"csrf": csrf})
    assert len([c for c in registro.llamadas if c[0] == "sync"]) == 2


def test_RF36_si_el_numero_no_esta_en_la_app_o_falla_el_codigo_no_cambia_nada(app, admin, almacen, con_llaves):
    web, csrf = admin
    for registro in (RegistroFalso(en_la_app=False), RegistroFalso(codigo_ok=False)):
        app.extensions["bot"].registro = registro
        app.extensions["bot"].conector = ConectorFalso()
        datos = web.post(f"/panel/empresas/{con_llaves['id']}/coexistencia/finalizar", json={"code": "C", "waba_id": WABA},
                         headers={"X-CSRF": csrf}).get_json()
        assert not datos["ok"] and "No se cambió nada" in datos["mensaje"]
        assert not any(c[0] in ("waba", "sync") for c in registro.llamadas)
        guardada = almacen.empresa(con_llaves["id"])
        assert guardada["phone_number_id"] == NUMERO_PRUEBA and guardada["coexistencia"].get("estado", "sin_conectar") == "sin_conectar"
    # Sin CSRF, ni siquiera se intenta
    assert web.post(f"/panel/empresas/{con_llaves['id']}/coexistencia/finalizar", json={"code": "C", "waba_id": WABA}).status_code == 400
    # Datos raros de la página, tampoco
    assert web.post(f"/panel/empresas/{con_llaves['id']}/coexistencia/finalizar", json={"code": "C", "waba_id": "abc"},
                    headers={"X-CSRF": csrf}).status_code == 400


def test_RF39_pasadas_24_horas_no_se_pide_la_sincronizacion(app, admin, almacen, con_llaves, ahora):
    registro = app.extensions["bot"].registro = RegistroFalso()
    app.extensions["bot"].conector = ConectorFalso()
    vieja = {**con_llaves["coexistencia"], "estado": "conectada", "phone_number_id": NUMERO_REAL,
             "conectada": (ahora - timedelta(hours=30)).isoformat(), "sincronizacion": {}}
    almacen.actualizar_empresa(con_llaves["id"], {"coexistencia": vieja}, ahora)
    web, csrf = admin
    r = web.post(f"/panel/empresas/{con_llaves['id']}/coexistencia/sincronizar", data={"csrf": csrf}, follow_redirects=True)
    assert "24 horas" in r.get_data(as_text=True) and not any(c[0] == "sync" for c in registro.llamadas)


def test_RF36_volver_al_numero_de_prueba(app, admin, almacen, con_llaves, config):
    app.extensions["bot"].registro = RegistroFalso()
    app.extensions["bot"].conector = ConectorFalso()
    web, csrf = admin
    web.post(f"/panel/empresas/{con_llaves['id']}/coexistencia/finalizar", json={"code": "C", "waba_id": WABA}, headers={"X-CSRF": csrf})
    web.post(f"/panel/empresas/{con_llaves['id']}/coexistencia/volver", data={"csrf": csrf})
    guardada = almacen.empresa(con_llaves["id"])
    assert guardada["phone_number_id"] == NUMERO_PRUEBA
    assert Cifrador(config.clave_maestra).descifrar(guardada["whatsapp_token_cif"]) == TOKEN
    assert guardada["coexistencia"]["estado"] == "sin_conectar"


def test_RF36_el_id_de_la_configuracion_son_solo_numeros(admin, almacen, con_llaves):
    web, csrf = admin
    r = web.post(f"/panel/empresas/{con_llaves['id']}/coexistencia/configuracion", data={"csrf": csrf, "config_id": "<script>"},
                 follow_redirects=True)
    assert "solo números" in r.get_data(as_text=True)
    web.post(f"/panel/empresas/{con_llaves['id']}/coexistencia/configuracion", data={"csrf": csrf, "config_id": " 1234 5678 "})
    assert almacen.empresa(con_llaves["id"])["coexistencia"]["config_id"] == "12345678"


# ------------------------------------------------------------------ v3.4.1 (C-22)
def test_RF36_si_meta_no_manda_el_id_de_la_cuenta_el_bot_la_busca_con_el_token(app, admin, almacen, con_llaves):
    """El 09/11/2026 la ventana de Meta devolvió el código pero no el aviso con la cuenta de WhatsApp."""
    registro = app.extensions["bot"].registro = RegistroFalso()
    app.extensions["bot"].conector = ConectorFalso()
    web, csrf = admin
    datos = web.post(f"/panel/empresas/{con_llaves['id']}/coexistencia/finalizar", json={"code": "CODIGO", "waba_id": ""},
                     headers={"X-CSRF": csrf}).get_json()
    assert datos["ok"], datos
    assert ("wabas", TOKEN_NEGOCIO) in registro.llamadas and ("numeros", WABA) in registro.llamadas
    assert almacen.empresa(con_llaves["id"])["coexistencia"]["waba_id"] == WABA


def test_RF36_sin_cuenta_en_el_token_no_cambia_nada_y_la_actividad_dice_lo_que_aviso_meta(app, admin, almacen, con_llaves):
    registro = RegistroFalso()
    registro.wabas = []
    app.extensions["bot"].registro = registro
    app.extensions["bot"].conector = ConectorFalso()
    web, csrf = admin
    datos = web.post(f"/panel/empresas/{con_llaves['id']}/coexistencia/finalizar",
                     json={"code": "CODIGO", "eventos": ["CANCEL (QR_CODE)"]}, headers={"X-CSRF": csrf}).get_json()
    assert not datos["ok"] and "QR" in datos["mensaje"]
    assert almacen.empresa(con_llaves["id"])["phone_number_id"] == NUMERO_PRUEBA
    assert "Meta avisó: CANCEL (QR_CODE)" in almacen.eventos(con_llaves["id"], 1)[0]["detalle"]


def test_RF36_registro_lee_las_cuentas_del_token():
    sesion = SesionFalsa({"debug_token": Respuesta({"data": {"granular_scopes": [
        {"scope": "business_management"}, {"scope": "whatsapp_business_management", "target_ids": [WABA]},
        {"scope": "whatsapp_business_messaging", "target_ids": [WABA]}]}})})
    assert X.Registro("v23.0", sesion=sesion).wabas_del_token("123456", SECRETO_META, TOKEN_NEGOCIO) == (True, [WABA])
    metodo, url, kw = sesion.pedidos[0]
    assert kw["params"]["access_token"] == f"123456|{SECRETO_META}" and kw["params"]["input_token"] == TOKEN_NEGOCIO
