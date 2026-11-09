"""Messenger e Instagram (v3.3). Requisitos BOT-RF-32 a BOT-RF-35."""
from bot import reglas
from bot.canales import Conector, Mensajeria, Messenger, partir_texto
from bot.cifrado import Cifrador
from bot.servicios import CANAL_APAGADO, DERIVADO, EN_REVISION, RESPONDIDO
from conftest import DUENO, SECRETO_META, TOKEN, WhatsAppFalso

PAGINA = "1122334455"
IG = "17841400000000001"
PSID = "fb:6655443322110"
IGSID = "ig:9988776655443"


def _pagina(payload_objeto, propio, *eventos):
    return {"object": payload_objeto, "entry": [{"id": propio, "time": 1, "messaging": list(eventos)}]}


def _texto(remitente, mid, texto, propio=PAGINA):
    return {"sender": {"id": remitente}, "recipient": {"id": propio}, "timestamp": 1, "message": {"mid": mid, "text": texto}}


def _conectar(almacen, empresa, ahora, config, **cambios):
    """Deja la empresa con una página conectada (como si se hubiera usado la pantalla Canales)."""
    canales = {"pagina_id": PAGINA, "pagina_nombre": "Sentirse Única", "ig_id": IG, "ig_usuario": "sentirse_unica",
               "messenger": True, "instagram": True, **cambios}
    return almacen.actualizar_empresa(empresa["id"], {
        "canales": canales, "pagina_token_cif": Cifrador(config.clave_maestra).cifrar("EAAPAGINA" + "p" * 60)}, ahora)


# ------------------------------------------------------------------ reglas
def test_RF32_extrae_mensajes_de_messenger_e_ignora_ecos():
    datos = _pagina("page", PAGINA,
                    _texto("6655443322110", "m_1", " Hola "),
                    {"sender": {"id": PAGINA}, "recipient": {"id": "6655443322110"}, "message": {"mid": "m_2", "text": "eco", "is_echo": True}},
                    {"sender": {"id": "6655443322110"}, "recipient": {"id": PAGINA}, "read": {"watermark": 1}},
                    {"sender": {"id": "6655443322110"}, "message": {"mid": "m_3", "attachments": [{"type": "image", "payload": {"url": "https://cdn.fb/x.jpg"}}]}},
                    {"sender": {"id": "6655443322110"}, "message": {"mid": "m_4", "sticker_id": 369239263222822, "attachments": [{"type": "image", "payload": {"url": "https://cdn.fb/s.png", "sticker_id": 369239263222822}}]}},
                    {"sender": {"id": "6655443322110"}, "timestamp": 7, "postback": {"title": "Ver precios", "payload": "PRECIOS"}})
    mensajes = reglas.extraer_mensajes(datos)
    assert [(m.id, m.numero, m.tipo, m.texto, m.media_id) for m in mensajes] == [
        ("m_1", PSID, "text", "Hola", ""),
        ("m_3", PSID, "image", "", "https://cdn.fb/x.jpg"),
        ("m_4", PSID, "sticker", "", ""),
        ("postback:6655443322110:7", PSID, "text", "Ver precios", ""),
    ]
    assert reglas.extraer_fallas(datos) == []


def test_RF32_extrae_mensajes_de_instagram_y_no_los_propios():
    datos = _pagina("instagram", IG, _texto("9988776655443", "ig_1", "¿Precio?", IG), _texto(IG, "ig_2", "respuesta del negocio", IG))
    assert [(m.numero, m.texto) for m in reglas.extraer_mensajes(datos)] == [(IGSID, "¿Precio?")]


def test_RF32_canal_e_identificacion_de_cada_contacto():
    assert [reglas.canal_de(x) for x in ("59170000001", PSID, IGSID)] == ["whatsapp", "messenger", "instagram"]
    assert reglas.id_social(IGSID) == "9988776655443"
    assert reglas.etiqueta_contacto("59170000001") == "+59170000001"
    assert reglas.etiqueta_contacto(IGSID) == "de Instagram (...5443)"


# ------------------------------------------------------------------ atención
def test_RF33_messenger_sin_conectar_no_responde(servicios, empresa, mensaje, whatsapp, ahora):
    assert servicios.atender(empresa, mensaje("Hola", numero=PSID), ahora) == CANAL_APAGADO
    assert whatsapp.enviados == []


def test_RF33_messenger_conectado_responde_por_su_canal_sin_agenda(servicios, almacen, empresa, mensaje, whatsapp, asistente, ahora, config):
    empresa = _conectar(almacen, empresa, ahora, config)
    assert servicios.atender(empresa, mensaje("¿Cuánto cuesta?", numero=PSID), ahora) == RESPONDIDO
    assert whatsapp.enviados == [(PSID, "Hola, ¿en qué le puedo ayudar?")]
    assert "por Messenger" in asistente.extra_sistema and "WhatsApp del negocio" in asistente.extra_sistema
    assert almacen.historial(empresa["id"], PSID)[-1]["role"] == "assistant"


def test_RF33_un_canal_apagado_no_responde(servicios, almacen, empresa, mensaje, whatsapp, ahora, config):
    empresa = _conectar(almacen, empresa, ahora, config, instagram=False)
    assert servicios.atender(empresa, mensaje("Hola", numero=IGSID), ahora) == CANAL_APAGADO
    assert whatsapp.enviados == []


def test_RF34_en_prueba_solo_responde_a_las_cuentas_de_prueba(servicios, almacen, empresa, mensaje, whatsapp, ahora, config):
    empresa = _conectar(almacen, empresa, ahora, config)
    empresa = almacen.actualizar_empresa(empresa["id"], {"estado": "revision"}, ahora)
    # Una cuenta que no es de prueba: no se le responde y queda como candidata (una sola vez)
    assert servicios.atender(empresa, mensaje("Hola", numero=IGSID), ahora) == EN_REVISION
    assert servicios.atender(almacen.empresa(empresa["id"]), mensaje("Hola otra vez", numero=IGSID), ahora) == EN_REVISION
    guardada = almacen.empresa(empresa["id"])
    assert [x["id"] for x in guardada["canales"]["candidatos"]] == [IGSID] and whatsapp.enviados == []
    assert any("sin respuesta: el bot está en prueba" in e["detalle"] for e in almacen.eventos(empresa["id"]))
    # Marcada como de prueba, sí se le responde
    canales = dict(guardada["canales"], probadores=[IGSID])
    empresa = almacen.actualizar_empresa(empresa["id"], {"canales": canales}, ahora)
    assert servicios.atender(empresa, mensaje("Hola", numero=IGSID), ahora) == RESPONDIDO


def test_RF33_derivar_desde_instagram_avisa_al_dueno_por_whatsapp(servicios, almacen, empresa, mensaje, whatsapp, asistente, ahora, config):
    empresa = _conectar(almacen, empresa, ahora, config)
    asistente.respuestas = ["Le paso con Rosa. [PASAR_A_HUMANO]"]
    assert servicios.atender(empresa, mensaje("Quiero hablar con alguien", numero=IGSID), ahora) == DERIVADO
    assert whatsapp.enviados[0] == (IGSID, "Le paso con Rosa.")
    assert whatsapp.enviados[1][0] == DUENO and "El cliente de Instagram (...5443) necesita atención" in whatsapp.enviados[1][1]


# ------------------------------------------------------------------ envío
class Respuesta:
    def __init__(self, datos=None, ok=True, contenido=b"", estado=200):
        self._datos, self.ok, self.content, self.status_code = datos or {}, ok, contenido, estado
        self.headers, self.text = {"Content-Type": "image/jpeg"}, ""

    def json(self):
        return self._datos


class SesionFalsa:
    def __init__(self, respuestas=None):
        self.pedidos = []
        self.respuestas = respuestas or {}

    def _responder(self, metodo, url, **kw):
        self.pedidos.append((metodo, url, kw))
        for ruta, r in self.respuestas.items():
            if ruta in url:
                return r
        return Respuesta({"success": True})

    def post(self, url, **kw):
        return self._responder("POST", url, **kw)

    def get(self, url, **kw):
        return self._responder("GET", url, **kw)

    def request(self, metodo, url, **kw):
        return self._responder(metodo, url, **kw)


def test_RF33_mensajeria_manda_cada_destino_por_su_canal_y_parte_los_textos_largos():
    whatsapp, sesion = WhatsAppFalso(), SesionFalsa()
    m = Mensajeria(whatsapp, Messenger(PAGINA, "TOKEN-PAGINA", "v23.0", sesion=sesion))
    assert m.enviar_texto("59170000001", "Hola")
    assert m.enviar_texto(IGSID, ("palabra " * 300).strip())  # 2399 letras: Instagram acepta hasta 1000
    assert whatsapp.enviados == [("59170000001", "Hola")]
    assert len(sesion.pedidos) == 3
    metodo, url, kw = sesion.pedidos[0]
    assert url.endswith(f"/v23.0/{PAGINA}/messages") and kw["params"] == {"access_token": "TOKEN-PAGINA"}
    assert kw["json"]["recipient"] == {"id": "9988776655443"} and all(len(p[2]["json"]["message"]["text"]) <= 1000 for p in sesion.pedidos)
    assert m.descargar_media("https://cdn.fb/x.jpg")[0] and sesion.pedidos[-1][1] == "https://cdn.fb/x.jpg"


def test_RF33_sin_pagina_conectada_no_se_puede_mandar_por_messenger():
    envio = Mensajeria(WhatsAppFalso(), None).enviar_texto(PSID, "Hola")
    assert not envio and "Canales" in envio.detalle


def test_RF33_partir_texto_respeta_el_limite_y_no_pierde_nada():
    texto = "Primera parte. " * 100
    partes = partir_texto(texto, 200)
    assert all(len(p) <= 200 for p in partes) and " ".join(partes).split() == texto.split()


def test_RF35_conector_revisa_permisos_y_trae_paginas_con_instagram():
    sesion = SesionFalsa({
        "debug_token": Respuesta({"data": {"is_valid": True, "app_id": "123456", "expires_at": 0, "type": "SYSTEM_USER",
                                            "scopes": ["pages_show_list", "pages_manage_metadata", "pages_messaging", "business_management"]}}),
        "me/accounts": Respuesta({"data": [{"id": PAGINA, "name": "Sentirse Única", "access_token": "TP",
                                            "instagram_business_account": {"id": IG, "username": "sentirse_unica"}},
                                           {"id": "999", "name": "Otra", "access_token": "TO"}]}),
    })
    conector = Conector("v23.0", sesion=sesion)
    ok, revision = conector.revisar_token(TOKEN, "123456", SECRETO_META)
    assert ok and revision["faltan"] == {"messenger": [], "instagram": ["instagram_basic", "instagram_manage_messages"]}
    ok, paginas = conector.paginas(TOKEN)
    assert ok and paginas[0] == {"id": PAGINA, "nombre": "Sentirse Única", "token": "TP", "ig_id": IG, "ig_usuario": "sentirse_unica"}
    assert paginas[1]["ig_id"] == ""
    assert conector.revisar_token(TOKEN, "", "") == (False, "Faltan el App ID o el App Secret de la empresa (Editar datos y llaves).")


# ------------------------------------------------------------------ webhook y panel
def test_RF32_webhook_de_messenger_firmado_se_atiende(web, almacen, empresa, config, firmar, whatsapp, ahora):
    empresa = _conectar(almacen, empresa, ahora, config)
    almacen.actualizar_empresa(empresa["id"], {"meta_app_secret_cif": Cifrador(config.clave_maestra).cifrar(SECRETO_META)}, ahora)
    cuerpo, firma = firmar(_pagina("page", PAGINA, _texto("6655443322110", "m_1", "Hola")))
    r = web.post(f"/webhook/{empresa['slug']}", data=cuerpo, headers={"X-Hub-Signature-256": firma, "Content-Type": "application/json"})
    assert r.status_code == 200 and whatsapp.enviados[0][0] == PSID
    assert "webhook_messenger" in almacen.actividad(empresa["id"])


class ConectorFalso:
    def __init__(self):
        self.llamadas = []
        self.paginas_ok = [{"id": PAGINA, "nombre": "Sentirse Única", "token": "TOKEN-DE-PAGINA-SECRETO", "ig_id": IG, "ig_usuario": "sentirse_unica"}]

    def revisar_token(self, token, app_id, app_secret):
        self.llamadas.append(("revisar", token))
        return True, {"permisos": [], "faltan": {"messenger": [], "instagram": []}, "vence": 0, "tipo": "SYSTEM_USER"}

    def paginas(self, token):
        self.llamadas.append(("paginas", token))
        return True, self.paginas_ok

    def suscribir_pagina(self, pagina_id, token_pagina):
        self.llamadas.append(("pagina", pagina_id, token_pagina))
        return True, "La página avisa al bot cuando le escriben."

    def suscribir_app(self, app_id, app_secret, objeto, campos, callback, verify_token):
        self.llamadas.append(("app", objeto, callback, verify_token))
        return True, "Webhook registrado."

    def pagina_suscrita(self, pagina_id, token_pagina, app_id):
        self.llamadas.append(("suscrita", pagina_id, token_pagina))
        return False, "La app ya no está suscrita a la página. Vuelve a conectar en Canales."


def _con_llaves(almacen, empresa, config, ahora):
    cif = Cifrador(config.clave_maestra)
    return almacen.actualizar_empresa(empresa["id"], {"meta_app_id": "123456", "meta_app_secret_cif": cif.cifrar(SECRETO_META),
                                                      "whatsapp_token_cif": cif.cifrar(TOKEN), "phone_number_id": "1352450434628435"}, ahora)


def test_RF35_panel_busca_las_paginas_y_conecta_messenger_e_instagram(app, admin, almacen, empresa, config, ahora):
    conector = app.extensions["bot"].conector = ConectorFalso()
    empresa = _con_llaves(almacen, empresa, config, ahora)
    web, csrf = admin
    assert "Conectar Messenger e Instagram" in web.get(f"/panel/empresas/{empresa['id']}/canales").get_data(as_text=True)
    # Paso 1: sin pegar token, usa el de WhatsApp y muestra las páginas (sin sus tokens)
    html = web.post(f"/panel/empresas/{empresa['id']}/canales/buscar", data={"csrf": csrf}).get_data(as_text=True)
    assert "Sentirse Única" in html and "@sentirse_unica" in html and "TOKEN-DE-PAGINA-SECRETO" not in html
    assert conector.llamadas[0] == ("revisar", TOKEN)
    # Paso 2: conecta los dos canales
    r = web.post(f"/panel/empresas/{empresa['id']}/canales/conectar",
                 data={"csrf": csrf, "pagina_id": PAGINA, "messenger": "1", "instagram": "1"})
    assert r.status_code == 302
    guardada = almacen.empresa(empresa["id"])
    k = guardada["canales"]
    assert (k["pagina_id"], k["ig_usuario"], k["messenger"], k["instagram"]) == (PAGINA, "sentirse_unica", True, True)
    assert Cifrador(config.clave_maestra).descifrar(guardada["pagina_token_cif"]) == "TOKEN-DE-PAGINA-SECRETO"
    assert "TOKEN-DE-PAGINA-SECRETO" not in str(k)
    webhook = f"https://bot.test/webhook/{empresa['slug']}"
    assert ("pagina", PAGINA, "TOKEN-DE-PAGINA-SECRETO") in conector.llamadas
    assert ("app", "page", webhook, empresa["verify_token"]) in conector.llamadas
    assert ("app", "instagram", webhook, empresa["verify_token"]) in conector.llamadas
    assert all(p["estado"] == "ok" for p in k["pasos"])
    assert "Messenger e Instagram conectado" in web.get(f"/panel/empresas/{empresa['id']}/canales").get_data(as_text=True)


def test_RF35_un_token_nuevo_se_guarda_cifrado_y_uno_corto_se_rechaza(app, admin, almacen, empresa, config, ahora):
    app.extensions["bot"].conector = ConectorFalso()
    empresa = _con_llaves(almacen, empresa, config, ahora)
    web, csrf = admin
    corto = web.post(f"/panel/empresas/{empresa['id']}/canales/buscar", data={"csrf": csrf, "token": "EAAcorto"}, follow_redirects=True)
    assert "texto largo" in corto.get_data(as_text=True)
    nuevo = "EAA" + "n" * 90
    web.post(f"/panel/empresas/{empresa['id']}/canales/buscar", data={"csrf": csrf, "token": nuevo})
    assert Cifrador(config.clave_maestra).descifrar(almacen.empresa(empresa["id"])["canal_token_cif"]) == nuevo


def test_RF34_panel_enciende_apaga_y_marca_cuentas_de_prueba(app, admin, almacen, empresa, config, ahora):
    empresa = _conectar(almacen, empresa, ahora, config, candidatos=[{"id": PSID, "fecha": ahora.isoformat()}])
    web, csrf = admin
    web.post(f"/panel/empresas/{empresa['id']}/canales/interruptor", data={"csrf": csrf, "canal": "instagram", "activo": "0"})
    web.post(f"/panel/empresas/{empresa['id']}/canales/probador", data={"csrf": csrf, "id": PSID})
    k = almacen.empresa(empresa["id"])["canales"]
    assert (k["instagram"], k["probadores"], k["candidatos"]) == (False, [PSID], [])
    malo = web.post(f"/panel/empresas/{empresa['id']}/canales/probador", data={"csrf": csrf, "id": "<script>"}, follow_redirects=True)
    assert "no es válida" in malo.get_data(as_text=True)
    web.post(f"/panel/empresas/{empresa['id']}/canales/probador", data={"csrf": csrf, "id": PSID, "accion": "quitar"})
    assert almacen.empresa(empresa["id"])["canales"]["probadores"] == []


def test_RF35_verificar_todo_revisa_la_pagina_conectada_sin_bloquear_whatsapp(app, admin, almacen, empresa, config, ahora):
    conector = app.extensions["bot"].conector = ConectorFalso()
    empresa = _conectar(almacen, empresa, ahora, config)
    web, csrf = admin
    web.post(f"/panel/empresas/{empresa['id']}/verificar", data={"csrf": csrf})
    chequeos = almacen.empresa(empresa["id"])["ultima_verificacion"]["chequeos"]
    canal = next(ch for ch in chequeos if ch["clave"] == "canales")
    assert canal["estado"] == "atencion" and "Vuelve a conectar" in canal["detalle"]
    assert conector.llamadas[0][0] == "suscrita"
    # Una página con problemas no impide activar el bot de WhatsApp
    web.post(f"/panel/empresas/{empresa['id']}/estado", data={"csrf": csrf, "estado": "activa"})
    assert almacen.empresa(empresa["id"])["estado"] == "activa"


def test_RF35_las_pantallas_de_canales_piden_sesion(web, empresa):
    assert web.get(f"/panel/empresas/{empresa['id']}/canales").status_code == 302
    assert web.post(f"/panel/empresas/{empresa['id']}/canales/conectar").status_code == 302
