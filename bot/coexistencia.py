"""Coexistencia (v3.4): el bot responde en el número del WhatsApp Business del negocio,
sin sacarlo de la app del celular. Requisitos BOT-RF-36 a BOT-RF-39.

Cómo funciona (documentación de Meta, «Onboarding WhatsApp Business app users», 09/11/2026):

1. En el panel, el botón abre el registro de Meta (Embedded Signup) con
   `featureType: "whatsapp_business_app_onboarding"`. La dueña escanea un QR con su
   WhatsApp Business. Meta devuelve un código y el id de la cuenta de WhatsApp (WABA).
2. `Registro` cambia el código por un token del negocio, comprueba que el número sigue en la
   app del celular (`is_on_biz_app`), suscribe la app a la WABA y los campos del webhook.
   **Nunca llama a `/register`:** registrar el número en la API lo sacaría de la app del celular.
3. Dentro de las 24 h se piden, una sola vez cada una y en este orden, la sincronización de
   contactos (`smb_app_state_sync`) y la del historial (`history`).

Cada método devuelve (ok, datos) o (False, texto que explica qué pasó), como `canales.Conector`.
"""
import logging
from datetime import datetime, timedelta

import requests

from .whatsapp import GRAPH, error_de_meta

log = logging.getLogger(__name__)

# Campos del webhook de la cuenta de WhatsApp: los mensajes de siempre, más lo que manda la
# coexistencia (lo que la dueña escribe desde el celular, el historial, los contactos y los
# avisos de desconexión).
CAMPOS_WABA = "messages,smb_message_echoes,history,smb_app_state_sync,account_update"
SINCRONIZACIONES = ("smb_app_state_sync", "history")  # en este orden (contactos, después historial)
NOMBRES_SINCRONIZACION = {"smb_app_state_sync": "contactos", "history": "historial"}
HORAS_PARA_SINCRONIZAR = 24
EVENTO_FIN = "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"

# Avisos de Meta (account_update), en palabras simples para la Actividad del panel
EVENTOS_DE_CUENTA = {
    "PARTNER_REMOVED": "se desconectó el bot del WhatsApp Business",
    "ACCOUNT_OFFBOARDED": "el número salió de la coexistencia (cambio de celular, número o se volvió a registrar)",
    "ACCOUNT_RECONNECTED": "el número se volvió a conectar al bot",
}
MOTIVOS_DE_DESCONEXION = {
    "PRIMARY_INACTIVITY": "la app WhatsApp Business del celular no se abrió en unos 14 días",
    "COMPANION_INACTIVITY": "un dispositivo vinculado no se usó en unos 30 días",
    "BUSINESS_DOWNGRADE": "el número dejó de ser de WhatsApp Business",
    "CHANGE_NUMBER": "se cambió el número en la app",
    "USER_RE_REGISTERED": "el número se volvió a registrar en un celular",
    "ACCOUNT_DISCONNECTED": "se desconectó desde la app del celular",
}
ERROR_HISTORIAL_APAGADO = 2593109  # la dueña eligió no compartir el historial


def config_de(empresa: dict) -> dict:
    """Lo que la empresa tiene guardado de la coexistencia, con valores por defecto."""
    c = dict((empresa or {}).get("coexistencia") or {})
    c.setdefault("config_id", "")
    c.setdefault("estado", "sin_conectar")  # sin_conectar | conectada | desconectada
    c.setdefault("waba_id", "")
    c.setdefault("phone_number_id", "")
    c.setdefault("numero", "")
    c.setdefault("nombre", "")
    c.setdefault("conectada", "")
    c.setdefault("sincronizacion", {})
    c.setdefault("pasos", [])
    return c


def puede_sincronizar(config: dict, tipo: str, ahora: datetime) -> tuple[bool, str]:
    """Cada sincronización va una sola vez, en orden y dentro de las 24 h de la conexión."""
    if config.get("estado") != "conectada" or not config.get("conectada"):
        return False, "Primero conecta el WhatsApp Business."
    if (config.get("sincronizacion") or {}).get(tipo, {}).get("request_id"):
        return False, f"La sincronización de {NOMBRES_SINCRONIZACION[tipo]} ya se pidió (Meta deja hacerla una sola vez)."
    if tipo == "history" and not (config.get("sincronizacion") or {}).get("smb_app_state_sync", {}).get("request_id"):
        return False, "Primero hay que sincronizar los contactos."
    try:
        desde = datetime.fromisoformat(config["conectada"])
    except ValueError:
        return False, "No se sabe cuándo se conectó: vuelve a conectar."
    if ahora - desde > timedelta(hours=HORAS_PARA_SINCRONIZAR):
        return False, ("Pasaron más de 24 horas desde la conexión: Meta ya no deja sincronizar. Para hacerlo hay "
                       "que desconectar el bot desde el WhatsApp Business y volver a conectar.")
    return True, ""


def texto_aviso_de_cuenta(evento: str, motivo: str = "", quien: str = "") -> str:
    """'Meta avisa: se desconectó el bot … (motivo: la app no se abrió en 14 días).'"""
    base = EVENTOS_DE_CUENTA.get(evento, f"cambio en la cuenta de WhatsApp ({evento})")
    detalle = MOTIVOS_DE_DESCONEXION.get(motivo, motivo)
    por = {"USER": " desde el celular", "SYSTEM": " automáticamente"}.get(quien, "")
    return f"Coexistencia: {base}{por}" + (f" (motivo: {detalle})." if detalle else ".")


class Registro:
    """Las llamadas a Meta para conectar el número. En los tests se reemplaza por un doble."""

    def __init__(self, version: str = "v23.0", sesion=None, timeout: int = 20):
        self._version = version
        self._sesion = sesion or requests.Session()
        self._timeout = timeout

    def _pedir(self, metodo: str, ruta: str, token: str = "", **kwargs):
        if "/register" in ruta:  # salvaguarda: este módulo nunca registra el número (sacaría a la dueña de su app)
            raise ValueError("La coexistencia nunca llama a /register.")
        cabeceras = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            r = self._sesion.request(metodo, f"{GRAPH}/{self._version}/{ruta}", headers=cabeceras,
                                     timeout=self._timeout, **kwargs)
        except requests.RequestException as e:
            log.error("Sin conexión con Meta (%s): %s", ruta.split("?")[0], e.__class__.__name__)
            return False, "No se pudo conectar con Meta. Vuelve a probar en un momento."
        if r.ok:
            try:
                return True, r.json()
            except ValueError:
                return True, {}
        codigo, mensaje = error_de_meta(r)
        return False, f"Meta respondió: {mensaje or codigo}"

    def canjear_codigo(self, app_id: str, app_secret: str, codigo: str):
        """El código del registro se cambia por el token del negocio (vale una sola vez y por poco tiempo)."""
        if not (app_id and app_secret and codigo):
            return False, "Faltan el App ID, el App Secret o el código del registro."
        ok, datos = self._pedir("GET", "oauth/access_token",
                                params={"client_id": app_id, "client_secret": app_secret, "code": codigo})
        if not ok:
            return False, datos
        token = datos.get("access_token") or ""
        return (True, token) if token else (False, "Meta no devolvió el token del negocio.")

    def numeros_de(self, waba_id: str, token: str):
        ok, datos = self._pedir("GET", f"{waba_id}/phone_numbers", token, params={
            "fields": "id,display_phone_number,verified_name,is_on_biz_app,platform_type"})
        return (True, datos.get("data") or []) if ok else (False, datos)

    def numero(self, phone_number_id: str, token: str):
        return self._pedir("GET", phone_number_id, token, params={
            "fields": "id,display_phone_number,verified_name,is_on_biz_app,platform_type"})

    def suscribir_waba(self, waba_id: str, token: str):
        ok, datos = self._pedir("POST", f"{waba_id}/subscribed_apps", token)
        if not ok:
            return False, datos
        return (True, "La cuenta de WhatsApp avisa al bot.") if datos.get("success", True) else \
            (False, "Meta no confirmó la suscripción de la cuenta de WhatsApp.")

    def sincronizar(self, phone_number_id: str, token: str, tipo: str):
        """POST /<número>/smb_app_data. Devuelve (True, request_id) o (False, motivo)."""
        if tipo not in SINCRONIZACIONES:
            raise ValueError(tipo)
        ok, datos = self._pedir("POST", f"{phone_number_id}/smb_app_data", token,
                                json={"messaging_product": "whatsapp", "sync_type": tipo})
        if not ok:
            return False, datos
        return True, str(datos.get("request_id") or "sin-id")


def elegir_numero(numeros: list[dict], phone_number_id: str = "") -> dict | None:
    """El número de la coexistencia: el indicado, o el único que está en la app del celular."""
    if phone_number_id:
        return next((n for n in numeros if str(n.get("id")) == str(phone_number_id)), None)
    en_la_app = [n for n in numeros if n.get("is_on_biz_app")]
    if len(en_la_app) == 1:
        return en_la_app[0]
    return numeros[0] if len(numeros) == 1 else None
