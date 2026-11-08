"""Verificaciones contra Claude y Meta (bot/verificaciones.py). Requisito BOT-RF-16.

Claude y Meta se reemplazan por dobles que responden como lo harian de verdad
(mismos codigos y forma de error), sin tocar la red."""
from datetime import datetime, timedelta, timezone

import anthropic
import httpx2 as httpx  # el SDK de Anthropic 2.x trae su propio cliente HTTP (httpx2)

from bot.verificaciones import estado_general, verificar_claude, verificar_meta, verificar_webhook

AHORA = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)


class ClaudeFalso:
    def __init__(self, error=None):
        self.error = error
        self.messages = self

    def create(self, **kwargs):
        if self.error:
            raise self.error
        return object()


def error_claude(clase, codigo, mensaje):
    respuesta = httpx.Response(codigo, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    return clase(mensaje, response=respuesta, body=None)


class Respuesta:
    def __init__(self, codigo, datos):
        self.ok, self._datos, self.text = codigo < 400, datos, ""

    def json(self):
        return self._datos


class MetaFalsa:
    """Responde a /{phone_number_id} y a /debug_token como la Graph API."""

    def __init__(self, calidad="GREEN", depurar=None, numero_ok=True):
        self.calidad, self.numero_ok = calidad, numero_ok
        self.depurar = depurar or (200, {"data": {"is_valid": True, "app_id": "123456789", "expires_at": 0,
                                                  "scopes": ["whatsapp_business_messaging", "whatsapp_business_management"]}})

    def get(self, url, params=None, **kwargs):
        if url.endswith("/debug_token"):
            return Respuesta(*self.depurar)
        if not self.numero_ok:
            return Respuesta(400, {"error": {"code": 190, "message": "Error validating access token"}})
        return Respuesta(200, {"display_phone_number": "+591 7501 3150", "verified_name": "Tienda", "quality_rating": self.calidad})


def meta(**kwargs):
    return {c.clave: c for c in verificar_meta("EAA" + "x" * 80, "1098765432", "123456789", "a" * 32, "v23.0", AHORA, sesion=MetaFalsa(**kwargs))}


def test_RF16_llave_de_claude_que_funciona():
    assert verificar_claude("sk-ant-x", "claude-haiku-5-5", cliente=ClaudeFalso()).estado == "ok"


def test_RF16_llave_de_claude_invalida_o_sin_creditos_se_explica():
    invalida = verificar_claude("sk-ant-x", "m", cliente=ClaudeFalso(error_claude(anthropic.AuthenticationError, 401, "invalid x-api-key")))
    sin_credito = verificar_claude("sk-ant-x", "m", cliente=ClaudeFalso(error_claude(
        anthropic.BadRequestError, 400, "Your credit balance is too low to access the Anthropic API.")))
    assert (invalida.estado, sin_credito.estado) == ("falla", "falla")
    assert "no es válida" in invalida.detalle and "no tiene créditos" in sin_credito.detalle
    assert verificar_claude("", "m").estado == "pendiente"


def test_RF16_numero_y_token_de_meta_correctos():
    r = meta()
    assert (r["numero"].estado, r["token"].estado) == ("ok", "ok")
    assert "+591 7501 3150" in r["numero"].detalle and "no vence" in r["token"].detalle


def test_RF16_token_vencido_o_app_secret_equivocado_se_explican():
    vencido = meta(numero_ok=False)["numero"]
    secreto_malo = meta(depurar=(400, {"error": {"code": 190, "message": "Invalid OAuth access token"}}))["token"]
    assert vencido.estado == "falla" and "venció" in vencido.detalle
    assert secreto_malo.estado == "falla" and "App Secret no coinciden" in secreto_malo.detalle


def test_RF16_token_temporal_y_calidad_baja_dan_atencion():
    pronto = int((AHORA + timedelta(hours=20)).timestamp())
    temporal = meta(depurar=(200, {"data": {"is_valid": True, "app_id": "123456789", "expires_at": pronto,
                                            "scopes": ["whatsapp_business_messaging"]}}))["token"]
    assert temporal.estado == "atencion" and "permanente" in temporal.detalle
    assert meta(calidad="RED")["numero"].estado == "atencion"


def test_RF16_el_webhook_y_el_estado_general():
    assert verificar_webhook({}, AHORA).estado == "pendiente"
    assert verificar_webhook({"webhook": AHORA - timedelta(minutes=3)}, AHORA).estado == "ok"
    assert estado_general([{"estado": "ok"}, {"estado": "atencion"}]) == "atencion"
    assert estado_general([{"estado": "ok"}, {"estado": "falla"}, {"estado": "pendiente"}]) == "falla"
