"""Panel y enlace de alta. Requisitos BOT-RF-13 a 17."""
import re
from datetime import timedelta

from bot.cifrado import Cifrador
from bot.empresas import crear_empresa, crear_enlace, secretos_de
from bot.whatsapp import Envio
from conftest import DUENO, LLAVE, PASSWORD, SECRETO_META, TOKEN, csrf_de

ALTA_COMPLETA = {
    "nombre": "Boutique Las Palmas", "dueno_nombre": "Rosa", "dueno_numero": "+591 7000 0099", "trato": "usted",
    "info_horario": "Lunes a sábado de 9 a 19", "anthropic_key": LLAVE, "saldo_usd": "5",
    "meta_app_id": "1234567890", "meta_app_secret": SECRETO_META, "phone_number_id": "1098765432", "whatsapp_token": TOKEN,
}


def _enlace(web, admin_csrf, nombre="Boutique Las Palmas"):
    web.post("/panel/empresas", data={"csrf": admin_csrf, "nombre": nombre})
    detalle = web.get("/panel/empresas/1").get_data(as_text=True)
    return re.search(r'id="enlace-alta" type="text" value="https://bot\.test(/alta/[^"]+)"', detalle).group(1)


# ------------------------------------------------------------------ BOT-RF-14 acceso
def test_RF14_el_panel_pide_contrasena(web):
    r = web.get("/panel/")
    assert r.status_code == 302 and "/panel/entrar" in r.headers["Location"]


def test_RF14_contrasena_incorrecta_no_entra_y_se_bloquea_tras_5_intentos(web):
    token = csrf_de(web.get("/panel/entrar"))
    for _ in range(5):
        assert web.post("/panel/entrar", data={"csrf": token, "password": "mala"}).status_code == 401
    # Ni siquiera la correcta entra mientras dura el bloqueo
    r = web.post("/panel/entrar", data={"csrf": token, "password": PASSWORD})
    assert "Demasiados intentos" in r.get_data(as_text=True)


def test_RF14_un_formulario_sin_csrf_se_rechaza(admin):
    web, _ = admin
    assert web.post("/panel/empresas", data={"nombre": "Sin token"}).status_code == 400


# ------------------------------------------------------------------ BOT-RF-15 alta por enlace
def test_RF15_crear_una_empresa_da_un_enlace_para_compartir_por_whatsapp(admin, almacen):
    web, csrf = admin
    r = web.post("/panel/empresas", data={"csrf": csrf, "nombre": "Boutique Las Palmas"}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Enlace de alta" in html and "https://wa.me/?text=" in html
    assert almacen.empresa_por_slug("boutique-las-palmas")["estado"] == "borrador"
    # El enlace se muestra una sola vez
    assert "Enlace de alta" not in web.get("/panel/empresas/1").get_data(as_text=True)


def test_RF15_el_dueno_llena_el_enlace_y_la_empresa_queda_en_prueba_con_llaves_cifradas(admin, almacen, config):
    web, csrf = admin
    ruta = _enlace(web, csrf)
    formulario = web.get(ruta)
    assert "Conectemos tu WhatsApp" in formulario.get_data(as_text=True)
    # Cuando envía todos los datos
    r = web.post(ruta, data={**ALTA_COMPLETA, "csrf": csrf_de(formulario)})
    # Entonces queda en prueba, con el número normalizado y las llaves cifradas
    assert r.status_code == 302 and r.headers["Location"].endswith("/alta/gracias")
    e = almacen.empresa(1)
    assert (e["estado"], e["dueno_numero"], e["saldo_usd"], e["info"]["horario"]) == ("revision", DUENO, 5.0, "Lunes a sábado de 9 a 19")
    assert LLAVE not in str(e) and TOKEN not in str(e) and SECRETO_META not in str(e)
    assert secretos_de(e, Cifrador(config.clave_maestra))["anthropic_key"] == LLAVE
    # Y el enlace ya no sirve
    assert web.get(ruta).status_code == 404


def test_RF15_si_faltan_datos_se_explica_cada_uno_y_no_se_guarda(admin, almacen):
    web, csrf = admin
    ruta = _enlace(web, csrf)
    token = csrf_de(web.get(ruta))
    r = web.post(ruta, data={"csrf": token, "nombre": "Boutique", "anthropic_key": "hola"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "La llave de Claude empieza con sk-ant-" in html and "Falta el App ID de Meta." in html
    assert almacen.empresa(1)["estado"] == "borrador"


def test_RF15_un_enlace_vencido_no_sirve(web, almacen, ahora):
    e = crear_empresa(almacen, "Vieja", ahora - timedelta(days=8))
    token = crear_enlace(almacen, e["id"], ahora - timedelta(days=8))
    r = web.get(f"/alta/{token}")
    assert r.status_code == 404 and "venció" in r.get_data(as_text=True)


def test_RF16_en_el_enlace_se_puede_probar_la_llave_antes_de_enviar(admin, verificador):
    web, csrf = admin
    ruta = _enlace(web, csrf)
    token = csrf_de(web.get(ruta))
    r = web.post(f"{ruta}/probar/claude", json={"anthropic_key": LLAVE}, headers={"X-CSRF": token})
    assert r.get_json()[0]["estado"] == "ok"
    assert verificador.llamadas[-1][:2] == ("claude", LLAVE)


# ------------------------------------------------------------------ BOT-RF-16 verificar y activar
def test_RF16_no_se_puede_activar_sin_verificar(admin, empresa, almacen, ahora):
    web, csrf = admin
    almacen.actualizar_empresa(empresa["id"], {"estado": "revision"}, ahora)
    r = web.post(f"/panel/empresas/{empresa['id']}/estado", data={"csrf": csrf, "estado": "activa"}, follow_redirects=True)
    assert "Antes de activar, verifica" in r.get_data(as_text=True)
    assert almacen.empresa(empresa["id"])["estado"] == "revision"


def test_RF16_verificar_guarda_el_resultado_y_permite_activar(admin, empresa, almacen, ahora):
    web, csrf = admin
    almacen.actualizar_empresa(empresa["id"], {"estado": "revision"}, ahora)
    r = web.post(f"/panel/empresas/{empresa['id']}/verificar", data={"csrf": csrf}, follow_redirects=True)
    assert "Todo funciona." in r.get_data(as_text=True)
    web.post(f"/panel/empresas/{empresa['id']}/estado", data={"csrf": csrf, "estado": "activa"})
    assert almacen.empresa(empresa["id"])["estado"] == "activa"


def test_RF16_si_la_verificacion_falla_se_muestra_y_no_se_activa(admin, empresa, almacen, verificador, ahora):
    web, csrf = admin
    verificador.claude_estado = "falla"
    almacen.actualizar_empresa(empresa["id"], {"estado": "revision"}, ahora)
    r = web.post(f"/panel/empresas/{empresa['id']}/verificar", data={"csrf": csrf}, follow_redirects=True)
    assert "Hay 1 cosa(s) por revisar." in r.get_data(as_text=True)
    web.post(f"/panel/empresas/{empresa['id']}/estado", data={"csrf": csrf, "estado": "activa"})
    assert almacen.empresa(empresa["id"])["estado"] == "revision"


def test_RF16_el_mensaje_de_prueba_explica_la_regla_de_las_24_horas(admin, empresa, verificador):
    web, csrf = admin
    verificador.envio = Envio(False, 131047, "Re-engagement message")
    r = web.post(f"/panel/empresas/{empresa['id']}/prueba", data={"csrf": csrf}, follow_redirects=True)
    assert "últimas 24 horas" in r.get_data(as_text=True)
    assert verificador.llamadas[-1] == ("prueba", DUENO)


# ------------------------------------------------------------------ BOT-RF-13 y 17 en el detalle
def test_RF13_el_detalle_nunca_muestra_las_llaves_completas(admin, empresa, almacen, config, ahora):
    web, _ = admin
    almacen.actualizar_empresa(empresa["id"], {"anthropic_key_cif": Cifrador(config.clave_maestra).cifrar(LLAVE)}, ahora)
    html = web.get(f"/panel/empresas/{empresa['id']}").get_data(as_text=True)
    assert LLAVE not in html and "sk-ant-…0000" in html


def test_RF17_el_detalle_muestra_cuantos_dias_de_credito_quedan(admin, empresa, almacen, ahora):
    web, csrf = admin
    web.post(f"/panel/empresas/{empresa['id']}/saldo", data={"csrf": csrf, "saldo_usd": "5"})
    almacen.sumar_uso(empresa["id"], ahora.date(), 1_000_000, 0)  # USD 0.10 hoy
    html = web.get(f"/panel/empresas/{empresa['id']}").get_data(as_text=True)
    assert re.search(r'class="cifra">49<small>días', html)  # (5 - 0.10) / 0.10 = 49
    lista = web.get("/panel/").get_data(as_text=True)
    assert "<strong>49</strong><span>días de crédito</span>" in lista


def test_RF11_si_la_base_no_responde_el_panel_lo_explica_y_meta_reintenta(admin, almacen, empresa, firmar, payload, monkeypatch):
    # Dada una base que no responde
    from bot.almacen import BaseDeDatosNoDisponible

    def sin_base(*args, **kwargs):
        raise BaseDeDatosNoDisponible("La base de datos no respondió a tiempo.")

    web, _ = admin
    monkeypatch.setattr(almacen, "empresas", sin_base)
    monkeypatch.setattr(almacen, "empresa_por_slug", sin_base)
    # Cuando se abre el panel y cuando llega un aviso de Meta
    panel = web.get("/panel/")
    cuerpo, firma = firmar(payload())
    aviso = web.post(f"/webhook/{empresa['slug']}", data=cuerpo, headers={"X-Hub-Signature-256": firma, "Content-Type": "application/json"})
    # Entonces el panel explica qué pasa (503, no un 500) y Meta recibe 503 para reintentar después
    assert panel.status_code == 503 and "La base de datos no respondió" in panel.get_data(as_text=True)
    assert aviso.status_code == 503 and "error" in aviso.get_json()
