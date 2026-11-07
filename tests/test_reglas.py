"""Reglas puras (bot/reglas.py). Requisitos BOT-RF-02, 07 y 09."""
import hashlib
import hmac

from bot import reglas


def test_RF02_historial_se_recorta_y_empieza_por_el_cliente():
    # Dado un historial largo cuyo recorte empezaría con una respuesta del bot
    historial = [{"role": r, "content": str(i)} for i, r in enumerate(["user", "assistant"] * 5)]
    # Cuando se recorta a los últimos 5 mensajes
    recorte = reglas.recortar_historial(historial, 5)
    # Entonces quedan 4: se descarta la respuesta suelta del inicio
    assert [m["role"] for m in recorte] == ["user", "assistant", "user", "assistant"]
    assert recorte[0]["content"] == "6"


def test_RF07_firma_correcta_se_acepta_y_alterada_se_rechaza():
    # Dado un cuerpo firmado con el App Secret
    cuerpo = b'{"entry": []}'
    firma = "sha256=" + hmac.new(b"secreto", cuerpo, hashlib.sha256).hexdigest()
    # Cuando se verifica con el mismo secreto, con un cuerpo alterado y sin firma
    # Entonces solo la primera se acepta
    assert reglas.firma_valida(cuerpo, firma, "secreto")
    assert not reglas.firma_valida(b'{"entry": [1]}', firma, "secreto")
    assert not reglas.firma_valida(cuerpo, None, "secreto")


def test_RF09_extrae_mensajes_e_ignora_estados_de_entrega(payload):
    # Dado un aviso de Meta con un texto, una imagen y un estado "leído"
    datos = payload(
        {"id": "wamid.1", "from": "591700", "type": "text", "text": {"body": "  Hola  "}},
        {"id": "wamid.2", "from": "591700", "type": "image", "image": {"id": "x"}},
        estados=[{"id": "wamid.0", "status": "read"}],
    )
    # Cuando se extraen los mensajes
    mensajes = reglas.extraer_mensajes(datos)
    # Entonces salen solo los dos mensajes, y el texto llega limpio
    assert [(m.id, m.tipo, m.texto) for m in mensajes] == [("wamid.1", "text", "Hola"), ("wamid.2", "image", "")]
