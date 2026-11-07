"""Fixtures compartidas. Ningun test usa la red, ni Meta, ni Claude, ni MongoDB:
WhatsApp y el asistente se reemplazan por dobles que anotan lo que reciben."""
import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest

from bot.almacen import AlmacenMemoria
from bot.app import crear_app
from bot.config import Config
from bot.reglas import MensajeEntrante
from bot.servicios import Servicios

CLIENTE = "59170000001"
DUENA = "59170000099"
SECRETO = "secreto-de-prueba"
VERIFY = "palabra-de-prueba"


class WhatsAppFalso:
    def __init__(self):
        self.enviados = []

    def enviar_texto(self, numero, texto):
        self.enviados.append((numero, texto))
        return True


class AsistenteFalso:
    def __init__(self):
        self.respuestas = ["Hola, ¿en qué le puedo ayudar?"]
        self.error = None
        self.historiales = []

    def responder(self, historial):
        self.historiales.append([dict(m) for m in historial])
        if self.error:
            raise self.error
        return self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]


@pytest.fixture
def ahora():
    return datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)


@pytest.fixture
def almacen():
    return AlmacenMemoria()


@pytest.fixture
def whatsapp():
    return WhatsAppFalso()


@pytest.fixture
def asistente():
    return AsistenteFalso()


@pytest.fixture
def servicios(almacen, whatsapp, asistente):
    return Servicios(almacen, whatsapp, asistente, limite_historial=20, pausa_horas=12, duena_numero=DUENA)


@pytest.fixture
def mensaje():
    contador = {"n": 0}

    def armar(texto="Hola", tipo="text", numero=CLIENTE, id=None):
        contador["n"] += 1
        return MensajeEntrante(id or f"wamid.{contador['n']}", numero, tipo, texto if tipo == "text" else "")

    return armar


@pytest.fixture
def payload():
    def armar(*mensajes, estados=()):
        return {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "WABA_ID",
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "PHONE_ID"},
                        "messages": list(mensajes),
                        "statuses": list(estados),
                    },
                }],
            }],
        }

    return armar


@pytest.fixture
def cliente_web(servicios, ahora):
    config = Config(
        whatsapp_token="token", phone_number_id="PHONE_ID",
        verify_token=VERIFY, app_secret=SECRETO, instrucciones="manual",
    )
    app = crear_app(config=config, servicios=servicios, ejecutar=lambda f, *a: f(*a), reloj=lambda: ahora)
    return app.test_client()


@pytest.fixture
def firmar():
    def armar(datos):
        cuerpo = json.dumps(datos).encode()
        firma = "sha256=" + hmac.new(SECRETO.encode(), cuerpo, hashlib.sha256).hexdigest()
        return cuerpo, firma

    return armar
