"""Rutas que llama Meta (bot/app.py). Requisitos BOT-RF-07 y 08."""
from conftest import CLIENTE, VERIFY


def test_RF07_webhook_sin_firma_valida_se_rechaza_y_no_responde(cliente_web, payload, whatsapp):
    # Dado un aviso con un mensaje, pero sin la firma de Meta
    datos = payload({"id": "wamid.1", "from": CLIENTE, "type": "text", "text": {"body": "Hola"}})
    # Cuando llega al webhook
    r = cliente_web.post("/webhook", json=datos, headers={"X-Hub-Signature-256": "sha256=falsa"})
    # Entonces se rechaza con 403 y nadie recibe respuesta
    assert r.status_code == 403
    assert whatsapp.enviados == []


def test_RF07_webhook_firmado_se_atiende(cliente_web, payload, firmar, whatsapp):
    # Dado un aviso firmado con el App Secret
    cuerpo, firma = firmar(payload({"id": "wamid.1", "from": CLIENTE, "type": "text", "text": {"body": "Hola"}}))
    # Cuando llega al webhook
    r = cliente_web.post("/webhook", data=cuerpo, headers={"X-Hub-Signature-256": firma, "Content-Type": "application/json"})
    # Entonces Meta recibe 200 y el cliente, su respuesta
    assert r.status_code == 200
    assert whatsapp.enviados[0][0] == CLIENTE


def test_RF08_verificacion_con_token_correcto_devuelve_el_challenge(cliente_web):
    # Dado que Meta verifica el webhook con la palabra correcta
    # Cuando llama a GET /webhook
    r = cliente_web.get("/webhook", query_string={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "12345"})
    # Entonces se le devuelve el número que mandó
    assert (r.status_code, r.get_data(as_text=True)) == (200, "12345")


def test_RF08_verificacion_con_token_incorrecto_se_rechaza(cliente_web):
    # Dado un intento de verificación con otra palabra
    # Cuando llama a GET /webhook
    r = cliente_web.get("/webhook", query_string={"hub.mode": "subscribe", "hub.verify_token": "otra", "hub.challenge": "12345"})
    # Entonces se rechaza
    assert r.status_code == 403
