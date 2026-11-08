"""Fixtures compartidas. Ningun test usa la red, ni Meta, ni Claude:
WhatsApp, el asistente y las verificaciones se reemplazan por dobles.

Los tests de AlmacenPostgres corren solo si existe TEST_DATABASE_URL (en el CI
la pone un Postgres temporal). OJO: esos tests VACIAN las tablas. Nunca pongas
ahi la base de produccion."""
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone

import pytest

from bot.almacen import AlmacenMemoria, AlmacenPostgres
from bot.app import crear_app
from bot.asistente import Respuesta
from bot.config import RAIZ, Config
from bot.empresas import crear_empresa
from bot.reglas import MensajeEntrante
from bot.servicios import Servicios
from bot.verificaciones import Chequeo
from bot.whatsapp import Envio

CLIENTE = "59170000001"
DUENO = "59170000099"
SECRETO_META = "0123456789abcdef0123456789abcdef"
PASSWORD = "contraseña-de-prueba"
LLAVE = "sk-ant-api03-llave-de-prueba-0000"
TOKEN = "EAA" + "x" * 80


class WhatsAppFalso:
    def __init__(self):
        self.enviados = []
        self.ok = True

    def enviar_texto(self, numero, texto):
        self.enviados.append((numero, texto))
        return Envio(self.ok, None if self.ok else 131047, "" if self.ok else "fuera de la ventana")


class AsistenteFalso:
    def __init__(self):
        self.respuestas = ["Hola, ¿en qué le puedo ayudar?"]
        self.error = None
        self.historiales = []

    def responder(self, historial):
        self.historiales.append([dict(m) for m in historial])
        if self.error:
            raise self.error
        texto = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        return Respuesta(texto, entrada=1000, salida=50)


class VerificadorFalso:
    """Anota que se probo y devuelve lo que el test decida."""

    def __init__(self):
        self.claude_estado = "ok"
        self.meta_estado = "ok"
        self.envio = Envio(True)
        self.llamadas = []

    def claude(self, api_key, modelo):
        self.llamadas.append(("claude", api_key, modelo))
        return Chequeo("claude", "Llave de Claude", self.claude_estado, "detalle claude")

    def meta(self, token, phone_number_id, app_id, app_secret, ahora):
        self.llamadas.append(("meta", token, phone_number_id, app_id, app_secret))
        return [Chequeo("numero", "Número de WhatsApp", self.meta_estado, "detalle número"),
                Chequeo("token", "Token y app de Meta", self.meta_estado, "detalle token")]

    def enviar_prueba(self, token, phone_number_id, numero, texto):
        self.llamadas.append(("prueba", numero))
        return self.envio


@pytest.fixture
def ahora():
    return datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)  # 16:00 en Bolivia


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
def verificador():
    return VerificadorFalso()


@pytest.fixture
def empresa(almacen, ahora):
    """Una empresa activa, lista para atender."""
    e = crear_empresa(almacen, "Tienda de Prueba", ahora)
    return almacen.actualizar_empresa(e["id"], {"estado": "activa", "dueno_numero": DUENO,
                                                "dueno_nombre": "Rosa", "pausa_horas": 12}, ahora)


@pytest.fixture
def servicios(almacen, whatsapp, asistente):
    return Servicios(almacen, lambda e: whatsapp, lambda e: asistente)


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
        return {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{
            "field": "messages",
            "value": {"messaging_product": "whatsapp", "metadata": {"phone_number_id": "1"},
                      "messages": list(mensajes), "statuses": list(estados)}}]}]}
    return armar


@pytest.fixture
def config():
    return Config(clave_maestra="clave-maestra-de-prueba-123", admin_password=PASSWORD,
                  plantilla_manual=(RAIZ / "instrucciones.md").read_text(encoding="utf-8"),
                  secret_key="secreto-de-sesion", url_publica="https://bot.test", cookie_segura=False)


@pytest.fixture
def app(config, almacen, servicios, verificador, ahora):
    aplicacion = crear_app(config=config, almacen=almacen, servicios=servicios, verificador=verificador,
                           ejecutar=lambda f, *a: f(*a), reloj=lambda: ahora)
    aplicacion.config["TESTING"] = True
    return aplicacion


@pytest.fixture
def web(app):
    return app.test_client()


def csrf_de(respuesta) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', respuesta.get_data(as_text=True)).group(1)


@pytest.fixture
def admin(web):
    """Un cliente web con la sesión de administrador iniciada. Devuelve (cliente, csrf)."""
    web.post("/panel/entrar", data={"csrf": csrf_de(web.get("/panel/entrar")), "password": PASSWORD})
    return web, csrf_de(web.get("/panel/"))  # al entrar se genera un csrf nuevo


@pytest.fixture
def firmar():
    def armar(datos, secreto=SECRETO_META):
        cuerpo = json.dumps(datos).encode()
        return cuerpo, "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    return armar


def _postgres_de_prueba():
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("Sin TEST_DATABASE_URL: los tests de Postgres corren en el CI")
    return url


@pytest.fixture
def url_postgres():
    url = _postgres_de_prueba()
    almacen = AlmacenPostgres(url)
    with almacen._pool.connection() as con:
        con.execute("TRUNCATE empresas, invitaciones, mensajes, pausas, mensajes_atendidos, uso, actividad, eventos RESTART IDENTITY CASCADE")
    almacen.cerrar()
    return url


@pytest.fixture(params=["memoria", "postgres"])
def almacen_contrato(request):
    """El mismo test corre contra los dos almacenes: deben comportarse igual."""
    if request.param == "memoria":
        yield AlmacenMemoria(max_leidos=3)
        return
    almacen = AlmacenPostgres(request.getfixturevalue("url_postgres"), max_leidos=3)
    yield almacen
    almacen.cerrar()
