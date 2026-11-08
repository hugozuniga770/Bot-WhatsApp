"""WhatsApp Cloud API de Meta: enviar mensajes y consultar el estado del numero."""
import logging
from dataclasses import dataclass

import requests

from .reglas import ocultar_numero

log = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com"


@dataclass(frozen=True)
class Envio:
    ok: bool
    codigo: int | None = None
    detalle: str = ""

    def __bool__(self):
        return self.ok


def error_de_meta(r) -> tuple[int | None, str]:
    """Saca el codigo y el mensaje del JSON de error de Meta."""
    try:
        error = r.json().get("error", {})
        return error.get("code"), error.get("message", "")
    except ValueError:
        return None, r.text[:300]


class WhatsApp:
    def __init__(self, token: str, phone_number_id: str, version: str = "v23.0", sesion=None, timeout: int = 20):
        self._token = token
        self._phone_id = phone_number_id
        self._version = version
        self._headers = {"Authorization": f"Bearer {token}"}
        self._sesion = sesion or requests.Session()
        self._timeout = timeout

    def _url(self, ruta: str) -> str:
        return f"{GRAPH}/{self._version}/{ruta}"

    def enviar_texto(self, numero: str, texto: str) -> Envio:
        cuerpo = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": numero,
            "type": "text",
            "text": {"preview_url": False, "body": texto[:4096]},
        }
        try:
            r = self._sesion.post(self._url(f"{self._phone_id}/messages"), json=cuerpo,
                                  headers=self._headers, timeout=self._timeout)
        except requests.RequestException as e:
            log.exception("No se pudo conectar con Meta para enviar a %s", ocultar_numero(numero))
            return Envio(False, None, f"Sin conexión con Meta: {e.__class__.__name__}")
        if r.ok:
            log.info("Enviado a %s", ocultar_numero(numero))
            return Envio(True)
        codigo, mensaje = error_de_meta(r)
        log.error("Meta rechazo el envio a %s: %s %s", ocultar_numero(numero), codigo, mensaje)
        return Envio(False, codigo, mensaje)

    def info_numero(self):
        """(ok, datos o (codigo, mensaje)). Sirve para validar el token y el Phone number ID."""
        r = self._sesion.get(self._url(self._phone_id), headers=self._headers, timeout=self._timeout,
                             params={"fields": "display_phone_number,verified_name,quality_rating"})
        return (True, r.json()) if r.ok else (False, error_de_meta(r))

    def depurar_token(self, app_id: str, app_secret: str):
        """(ok, datos o (codigo, mensaje)). Valida el App ID + App Secret y dice si el token vence."""
        r = self._sesion.get(self._url("debug_token"), timeout=self._timeout,
                             params={"input_token": self._token, "access_token": f"{app_id}|{app_secret}"})
        return (True, r.json().get("data", {})) if r.ok else (False, error_de_meta(r))
