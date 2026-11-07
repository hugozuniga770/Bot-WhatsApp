"""Envio de mensajes por la WhatsApp Cloud API de Meta."""
import logging

import requests

from .reglas import ocultar_numero

log = logging.getLogger(__name__)


class WhatsApp:
    def __init__(self, token: str, phone_number_id: str, version: str = "v23.0", sesion=None, timeout: int = 20):
        self._url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        self._headers = {"Authorization": f"Bearer {token}"}
        self._sesion = sesion or requests.Session()
        self._timeout = timeout

    def enviar_texto(self, numero: str, texto: str) -> bool:
        cuerpo = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": numero,
            "type": "text",
            "text": {"preview_url": False, "body": texto[:4096]},
        }
        try:
            r = self._sesion.post(self._url, json=cuerpo, headers=self._headers, timeout=self._timeout)
        except requests.RequestException:
            log.exception("No se pudo conectar con Meta para enviar a %s", ocultar_numero(numero))
            return False
        if r.ok:
            log.info("Enviado a %s", ocultar_numero(numero))
            return True
        log.error("Meta rechazo el envio a %s: %s %s", ocultar_numero(numero), r.status_code, r.text[:500])
        return False
