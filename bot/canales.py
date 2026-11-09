"""Messenger e Instagram (v3.3): enviar mensajes y conectar una página casi sola.

- `Messenger` habla con la API de Messenger de Meta usando el token de la página. La misma
  API sirve para Instagram cuando la cuenta de Instagram está unida a esa página.
- `Mensajeria` es lo que usa `servicios.py`: recibe un destino ("59170000001", "fb:…",
  "ig:…") y lo manda por el canal que corresponde. Así `servicios.py` no cambia de forma.
- `Conector` hace la parte tediosa de Meta: revisa el token, busca las páginas y sus
  cuentas de Instagram, suscribe la página a la app y registra el webhook de la app.
"""
import logging

import requests

from . import reglas
from .whatsapp import GRAPH, Envio, error_de_meta

log = logging.getLogger(__name__)

# Permisos que necesita el token para cada canal (documentación de Meta, 09/11/2026)
PERMISOS = {
    "messenger": ("pages_show_list", "pages_manage_metadata", "pages_messaging"),
    "instagram": ("pages_show_list", "pages_manage_metadata", "instagram_basic", "instagram_manage_messages"),
}
# Campos del webhook que se suscriben (lo que el bot necesita: mensajes y botones)
CAMPOS_PAGINA = "messages,messaging_postbacks"
CAMPOS_INSTAGRAM = "messages"

# Errores frecuentes al enviar por Messenger o Instagram, explicados para el panel
MOTIVOS_SOCIALES = {
    10: "la app no tiene permiso para responder en esta página (falta la revisión de la app de Meta o el permiso)",
    200: "la app no tiene permiso para responder en esta página (falta la revisión de la app de Meta o el permiso)",
    190: "el token de la página no es válido o venció; vuelve a conectar la página en Canales",
    551: "esa persona no está disponible en este momento",
    2018278: "pasaron más de 24 horas desde el último mensaje de esa persona, y Meta no deja escribirle primero",
    2534022: "pasaron más de 24 horas desde el último mensaje de esa persona, y Meta no deja escribirle primero",
}


def partir_texto(texto: str, limite: int) -> list[str]:
    """Corta un texto largo en partes que entren en el canal, sin cortar palabras si se puede."""
    texto = (texto or "").strip()
    partes = []
    while len(texto) > limite:
        corte = max(texto.rfind("\n", 0, limite), texto.rfind(". ", 0, limite) + 1, texto.rfind(" ", 0, limite))
        if corte <= limite // 3:
            corte = limite
        partes.append(texto[:corte].strip())
        texto = texto[corte:].strip()
    if texto:
        partes.append(texto)
    return partes


class Messenger:
    """API de Messenger de una página (sirve para Messenger y para Instagram)."""

    def __init__(self, pagina_id: str, token_pagina: str, version: str = "v23.0", sesion=None, timeout: int = 20):
        self._pagina = pagina_id
        self._token = token_pagina
        self._version = version
        self._sesion = sesion or requests.Session()
        self._timeout = timeout

    def _enviar(self, destino: str, mensaje: dict) -> Envio:
        cuerpo = {"recipient": {"id": reglas.id_social(destino)}, "messaging_type": "RESPONSE", "message": mensaje}
        try:
            r = self._sesion.post(f"{GRAPH}/{self._version}/{self._pagina}/messages", json=cuerpo,
                                  params={"access_token": self._token}, timeout=self._timeout)
        except requests.RequestException as e:
            log.exception("No se pudo conectar con Meta para enviar a %s", reglas.ocultar_numero(destino))
            return Envio(False, None, f"Sin conexión con Meta: {e.__class__.__name__}")
        if r.ok:
            return Envio(True)
        codigo, mensaje_error = error_de_meta(r)
        log.error("Meta rechazo el envio a %s: %s %s", reglas.ocultar_numero(destino), codigo, mensaje_error)
        return Envio(False, codigo, mensaje_error)

    def enviar_texto(self, destino: str, texto: str) -> Envio:
        envio = Envio(False, None, "Mensaje vacío")
        for parte in partir_texto(texto, reglas.LIMITE_TEXTO[reglas.canal_de(destino)]):
            envio = self._enviar(destino, {"text": parte})
            if not envio:
                break
        return envio

    def enviar_imagen(self, destino: str, enlace: str, texto: str = "") -> Envio:
        envio = self._enviar(destino, {"attachment": {"type": "image", "payload": {"url": enlace, "is_reusable": False}}})
        if envio and texto:
            return self.enviar_texto(destino, texto)
        return envio

    def descargar(self, url: str, maximo: int = 5 * 1024 * 1024):
        """Messenger e Instagram mandan la dirección del archivo directamente."""
        try:
            r = self._sesion.get(url, timeout=self._timeout)
            if not r.ok:
                return False, (r.status_code, "No se pudo bajar el archivo.")
            if len(r.content) > maximo:
                return False, (None, "El archivo pesa más de 5 MB.")
            return True, (r.content, r.headers.get("Content-Type", "application/octet-stream"))
        except requests.RequestException as e:
            return False, (None, e.__class__.__name__)


class Mensajeria:
    """Manda cada mensaje por su canal. Tiene la misma forma que `WhatsApp`."""

    def __init__(self, whatsapp, messenger=None):
        self._whatsapp = whatsapp
        self._messenger = messenger

    def _canal(self, destino: str):
        if reglas.canal_de(destino) == "whatsapp":
            return self._whatsapp
        return self._messenger

    def enviar_texto(self, destino: str, texto: str) -> Envio:
        canal = self._canal(destino)
        if canal is None:
            return Envio(False, None, "Messenger e Instagram no están conectados en Canales.")
        return canal.enviar_texto(destino, texto)

    def enviar_imagen(self, destino: str, enlace: str, texto: str = "") -> Envio:
        canal = self._canal(destino)
        if canal is None:
            return Envio(False, None, "Messenger e Instagram no están conectados en Canales.")
        return canal.enviar_imagen(destino, enlace, texto)

    def descargar_media(self, media_id: str):
        if media_id.startswith("https://"):
            if self._messenger is None:
                return False, (None, "Messenger e Instagram no están conectados en Canales.")
            return self._messenger.descargar(media_id)
        return self._whatsapp.descargar_media(media_id)


# ------------------------------------------------------------------ conexión guiada
class Conector:
    """Lo que el panel usa para conectar una página. En los tests se reemplaza por un doble.

    Cada método devuelve (ok, datos) o (False, texto que explica qué pasó).
    """

    def __init__(self, version: str = "v23.0", sesion=None, timeout: int = 20):
        self._version = version
        self._sesion = sesion or requests.Session()
        self._timeout = timeout

    def _url(self, ruta: str) -> str:
        return f"{GRAPH}/{self._version}/{ruta}"

    def _pedir(self, metodo: str, ruta: str, **kwargs):
        try:
            r = self._sesion.request(metodo, self._url(ruta), timeout=self._timeout, **kwargs)
        except requests.RequestException:
            return False, "No se pudo conectar con Meta. Vuelve a probar en un momento."
        if r.ok:
            try:
                return True, r.json()
            except ValueError:
                return True, {}
        codigo, mensaje = error_de_meta(r)
        if codigo == 190:
            return False, "El token no es válido o venció. Genera uno nuevo en Meta."
        return False, f"Meta respondió: {mensaje or codigo}"

    def revisar_token(self, token: str, app_id: str, app_secret: str) -> tuple[bool, dict | str]:
        """Qué permisos tiene el token, si vence y si es de esta app."""
        if not app_id or not app_secret:
            return False, "Faltan el App ID o el App Secret de la empresa (Editar datos y llaves)."
        ok, datos = self._pedir("GET", "debug_token", params={"input_token": token, "access_token": f"{app_id}|{app_secret}"})
        if not ok:
            return False, datos
        info = datos.get("data") or {}
        if not info.get("is_valid"):
            return False, "Meta dice que el token no es válido. Genera uno nuevo."
        if str(info.get("app_id", "")) not in ("", str(app_id)):
            return False, "El token es de otra app de Meta: no coincide con el App ID de la empresa."
        permisos = set(info.get("scopes") or [])
        return True, {
            "permisos": sorted(permisos),
            "faltan": {canal: [p for p in necesarios if p not in permisos] for canal, necesarios in PERMISOS.items()},
            "vence": int(info.get("expires_at") or 0),
            "tipo": info.get("type", ""),
        }

    def paginas(self, token: str) -> tuple[bool, list[dict] | str]:
        """Las páginas a las que llega el token, con su cuenta de Instagram si tienen una."""
        ok, datos = self._pedir("GET", "me/accounts", params={
            "access_token": token, "limit": 50,
            "fields": "id,name,access_token,instagram_business_account{id,username}"})
        if not ok:
            return False, datos
        paginas = []
        for p in datos.get("data") or []:
            ig = p.get("instagram_business_account") or {}
            paginas.append({"id": str(p.get("id", "")), "nombre": p.get("name", ""), "token": p.get("access_token", ""),
                            "ig_id": str(ig.get("id") or ""), "ig_usuario": ig.get("username") or ""})
        return True, [p for p in paginas if p["id"]]

    def suscribir_pagina(self, pagina_id: str, token_pagina: str) -> tuple[bool, str]:
        """Que Meta avise al webhook de la app cuando alguien le escribe a esta página."""
        ok, datos = self._pedir("POST", f"{pagina_id}/subscribed_apps",
                                params={"access_token": token_pagina, "subscribed_fields": CAMPOS_PAGINA})
        if not ok:
            return False, datos
        return (True, "La página avisa al bot cuando le escriben.") if datos.get("success", True) else \
            (False, "Meta no confirmó la suscripción de la página.")

    def suscribir_app(self, app_id: str, app_secret: str, objeto: str, campos: str,
                      callback: str, verify_token: str) -> tuple[bool, str]:
        """Registra el webhook de la app para `page` (Messenger) o `instagram`.

        Meta llama al webhook con el token de verificación antes de aceptarlo, así que
        el servicio tiene que estar en línea en esa dirección.
        """
        ok, datos = self._pedir("POST", f"{app_id}/subscriptions", params={
            "access_token": f"{app_id}|{app_secret}", "object": objeto, "callback_url": callback,
            "fields": campos, "verify_token": verify_token, "include_values": "true"})
        if not ok:
            return False, datos
        return (True, "Webhook registrado.") if datos.get("success", True) else (False, "Meta no confirmó el webhook.")

    def pagina_suscrita(self, pagina_id: str, token_pagina: str, app_id: str) -> tuple[bool, str]:
        """Para Verificar todo: el token de la página sirve y la app sigue suscrita."""
        ok, datos = self._pedir("GET", f"{pagina_id}/subscribed_apps", params={"access_token": token_pagina})
        if not ok:
            return False, datos
        for app in datos.get("data") or []:
            if str(app.get("id", "")) == str(app_id):
                campos = set(app.get("subscribed_fields") or [])
                if "messages" not in campos:
                    return False, "La app está suscrita a la página, pero no a los mensajes. Vuelve a conectar en Canales."
                return True, "La página está conectada y avisa al bot."
        return False, "La app ya no está suscrita a la página. Vuelve a conectar en Canales."


def explicar_falla(codigo) -> str:
    return MOTIVOS_SOCIALES.get(codigo, f"Meta respondió con el código {codigo}")


# ------------------------------------------------------------------ configuración guardada
def config_de(empresa: dict) -> dict:
    """Lo que la empresa tiene guardado de Messenger e Instagram, con valores por defecto."""
    c = dict(empresa.get("canales") or {})
    c.setdefault("pagina_id", "")
    c.setdefault("pagina_nombre", "")
    c.setdefault("ig_id", "")
    c.setdefault("ig_usuario", "")
    c.setdefault("messenger", False)
    c.setdefault("instagram", False)
    c.setdefault("probadores", [])
    c.setdefault("candidatos", [])
    c.setdefault("pasos", [])
    return c


def canal_encendido(empresa: dict, canal: str) -> bool:
    """WhatsApp siempre; Messenger e Instagram solo si se conectaron y están encendidos."""
    if canal == "whatsapp":
        return True
    c = config_de(empresa)
    if not c["pagina_id"] or not empresa.get("pagina_token_cif"):
        return False
    if canal == "instagram" and not c["ig_id"]:
        return False
    return bool(c.get(canal))
