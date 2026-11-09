"""Webhook de cada empresa (/webhook/<slug>). Requisitos BOT-RF-07, 08, 09 y 12."""
from bot.cifrado import Cifrador
from bot.empresas import crear_empresa
from conftest import CLIENTE, SECRETO_META


def _con_secreto(almacen, empresa, config, ahora):
    cif = Cifrador(config.clave_maestra).cifrar(SECRETO_META)
    return almacen.actualizar_empresa(empresa["id"], {"meta_app_secret_cif": cif}, ahora)


def test_RF08_verificacion_con_el_token_de_la_empresa_devuelve_el_challenge(web, empresa, almacen):
    # Dado que Meta verifica el webhook de la empresa con su token
    r = web.get(f"/webhook/{empresa['slug']}", query_string={
        "hub.mode": "subscribe", "hub.verify_token": empresa["verify_token"], "hub.challenge": "12345"})
    # Entonces se le devuelve el número y el panel registra la conexión
    assert (r.status_code, r.get_data(as_text=True)) == (200, "12345")
    assert "webhook" in almacen.actividad(empresa["id"])


def test_RF08_token_incorrecto_o_empresa_inexistente_se_rechaza(web, empresa):
    r = web.get(f"/webhook/{empresa['slug']}", query_string={"hub.mode": "subscribe", "hub.verify_token": "otro", "hub.challenge": "1"})
    assert r.status_code == 403
    assert web.get("/webhook/no-existe", query_string={"hub.mode": "subscribe"}).status_code == 404


def test_RF07_webhook_firmado_con_el_secreto_de_la_empresa_se_atiende(web, empresa, almacen, config, payload, firmar, whatsapp, ahora):
    # Dada una empresa con su App Secret guardado (cifrado)
    _con_secreto(almacen, empresa, config, ahora)
    cuerpo, firma = firmar(payload({"id": "wamid.1", "from": CLIENTE, "type": "text", "text": {"body": "Hola"}}))
    # Cuando Meta manda un mensaje firmado
    r = web.post(f"/webhook/{empresa['slug']}", data=cuerpo, headers={"X-Hub-Signature-256": firma, "Content-Type": "application/json"})
    # Entonces se responde 200 y el cliente recibe su respuesta
    assert r.status_code == 200 and whatsapp.enviados[0][0] == CLIENTE


def test_RF07_sin_firma_o_con_el_secreto_de_otra_empresa_se_rechaza(web, empresa, almacen, config, payload, firmar, whatsapp, ahora):
    # Dadas dos empresas, cada una con su App Secret
    _con_secreto(almacen, empresa, config, ahora)
    otra = crear_empresa(almacen, "Otra", ahora)
    otra = almacen.actualizar_empresa(otra["id"], {"estado": "activa", "meta_app_secret_cif": Cifrador(config.clave_maestra).cifrar("f" * 32)}, ahora)
    datos = payload({"id": "wamid.1", "from": CLIENTE, "type": "text", "text": {"body": "Hola"}})
    cuerpo, firma_de_la_primera = firmar(datos)
    # Cuando llega sin firma, o firmado con el secreto de la primera al webhook de la segunda
    sin_firma = web.post(f"/webhook/{empresa['slug']}", json=datos)
    cruzado = web.post(f"/webhook/{otra['slug']}", data=cuerpo, headers={"X-Hub-Signature-256": firma_de_la_primera, "Content-Type": "application/json"})
    # Entonces ambos se rechazan y nadie recibe respuesta
    assert (sin_firma.status_code, cruzado.status_code) == (403, 403)
    assert whatsapp.enviados == []


def test_RF09_meta_avisa_que_no_pudo_entregar_y_el_panel_lo_muestra(admin, empresa, almacen, config, payload, firmar, whatsapp, ahora):
    # Dada una empresa con su App Secret, y Meta avisa que un mensaje del bot no se entregó
    _con_secreto(almacen, empresa, config, ahora)
    cuerpo, firma = firmar(payload(estados=[{"id": "wamid.9", "status": "failed", "recipient_id": "59170000123",
                                             "errors": [{"code": 131030, "title": "Recipient not in allowed list"}]}]))
    web, _ = admin
    # Cuando llega el aviso firmado
    r = web.post(f"/webhook/{empresa['slug']}", data=cuerpo, headers={"X-Hub-Signature-256": firma, "Content-Type": "application/json"})
    # Entonces se responde 200, no se contesta a nadie y la Actividad del panel explica el motivo
    assert r.status_code == 200 and whatsapp.enviados == []
    detalle = web.get(f"/panel/empresas/{empresa['id']}").get_data(as_text=True)
    assert "Meta no pudo entregar un mensaje a ...0123: ese número no está en la lista de destinatarios de prueba" in detalle
