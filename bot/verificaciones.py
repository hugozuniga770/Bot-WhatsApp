"""Verificaciones de cada empresa (BOT-RF-16): que cada llave funcione de verdad.

Cada chequeo devuelve un estado y un texto que explica que pasa y como
arreglarlo, en palabras de quien llena el formulario.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import anthropic
import requests

from .reglas import hace
from .whatsapp import WhatsApp

CALIDAD = {"GREEN": "alta", "YELLOW": "media", "RED": "baja"}


@dataclass
class Chequeo:
    clave: str
    titulo: str
    estado: str  # ok | atencion | falla | pendiente
    detalle: str

    def a_dict(self):
        return asdict(self)


def verificar_claude(api_key: str, modelo: str, cliente=None) -> Chequeo:
    def c(estado, detalle):
        return Chequeo("claude", "Llave de Claude", estado, detalle)

    if not api_key:
        return c("pendiente", "Falta la llave de Claude.")
    try:
        cliente = cliente or anthropic.Anthropic(api_key=api_key, timeout=20.0, max_retries=0)
        # Una respuesta de 1 token: prueba la llave, el modelo y que haya saldo (cuesta casi nada).
        cliente.messages.create(model=modelo, max_tokens=1, messages=[{"role": "user", "content": "Responde: ok"}])
        return c("ok", f"La llave funciona, la cuenta tiene créditos y el modelo {modelo} responde.")
    except anthropic.AuthenticationError:
        return c("falla", "La llave no es válida: está mal copiada o fue borrada. Crea otra en platform.claude.com, en Claves de API.")
    except anthropic.PermissionDeniedError:
        return c("falla", "La llave no tiene permiso para usar Claude. Revisa en platform.claude.com a qué espacio de trabajo pertenece.")
    except anthropic.NotFoundError:
        return c("falla", f"El modelo {modelo} no está disponible para esta llave.")
    except anthropic.RateLimitError:
        return c("atencion", "La llave funciona, pero llegó a su límite de uso en este momento. Vuelve a probar en un minuto.")
    except anthropic.APIConnectionError:
        return c("atencion", "No se pudo conectar con Claude. Vuelve a probar en un momento.")
    except anthropic.APIStatusError as e:
        if "credit" in str(e).lower():
            return c("falla", "La cuenta no tiene créditos. Cárgalos en platform.claude.com, en Facturación (Billing).")
        return c("falla", f"Claude rechazó la prueba (error {e.status_code}).")


def verificar_meta(token: str, phone_number_id: str, app_id: str, app_secret: str,
                   version: str, ahora: datetime, sesion=None) -> list[Chequeo]:
    def numero(estado, detalle):
        return Chequeo("numero", "Número de WhatsApp", estado, detalle)

    def acceso(estado, detalle):
        return Chequeo("token", "Token y app de Meta", estado, detalle)

    if not token or not phone_number_id:
        return [numero("pendiente", "Falta el token o el Phone number ID."),
                acceso("pendiente", "Falta el token de Meta.")]

    wa = WhatsApp(token, phone_number_id, version, sesion=sesion)
    resultado = []
    try:
        ok, datos = wa.info_numero()
        if ok:
            calidad = datos.get("quality_rating", "")
            texto = ", ".join(x for x in (datos.get('display_phone_number', ''), datos.get('verified_name', '')) if x) or "Número encontrado"
            if calidad == "RED":
                resultado.append(numero("atencion", f"{texto}. Calidad baja: Meta puede limitar los mensajes. Revisa si los clientes están bloqueando o reportando el número."))
            elif calidad == "YELLOW":
                resultado.append(numero("atencion", f"{texto}. Calidad media: cuida que el bot no moleste a los clientes."))
            else:
                extra = f", calidad {CALIDAD[calidad]}" if calidad in CALIDAD else ""
                resultado.append(numero("ok", f"{texto}{extra}."))
        else:
            codigo, mensaje = datos
            if codigo == 190:
                resultado.append(numero("falla", "El token no es válido o ya venció. Genera uno nuevo en Meta (o el permanente, paso 7)."))
            elif codigo == 100:
                resultado.append(numero("falla", "El Phone number ID no existe o el token no tiene acceso a ese número. Cópialo otra vez de Meta, en Configuración de la API."))
            else:
                resultado.append(numero("falla", f"Meta respondió: {mensaje or codigo}"))
    except requests.RequestException:
        resultado.append(numero("atencion", "No se pudo conectar con Meta. Vuelve a probar en un momento."))

    if not app_id or not app_secret:
        resultado.append(acceso("pendiente", "Falta el App ID o el App Secret."))
        return resultado
    try:
        ok, datos = wa.depurar_token(app_id, app_secret)
        if not ok:
            resultado.append(acceso("falla", "El App ID o el App Secret no coinciden. Cópialos de Meta, en Configuración de la app → Básica."))
        elif not datos.get("is_valid"):
            resultado.append(acceso("falla", "Meta dice que el token no es válido. Genera uno nuevo."))
        elif str(datos.get("app_id", "")) not in ("", str(app_id)):
            resultado.append(acceso("falla", "El token es de otra app de Meta: no coincide con el App ID."))
        else:
            permisos = set(datos.get("scopes") or [])
            vence = int(datos.get("expires_at") or 0)
            if permisos and "whatsapp_business_messaging" not in permisos:
                resultado.append(acceso("falla", "Al token le falta el permiso whatsapp_business_messaging."))
            elif vence == 0:
                resultado.append(acceso("ok", "El token no vence y tiene los permisos de WhatsApp."))
            else:
                dias = (datetime.fromtimestamp(vence, tz=timezone.utc) - ahora).total_seconds() / 86400
                if dias < 2:
                    resultado.append(acceso("atencion", "El token es temporal y vence en menos de 2 días. Crea el permanente (paso 7 de la guía)."))
                elif dias < 7:
                    resultado.append(acceso("atencion", f"El token vence en {int(dias)} días. Reemplázalo por uno permanente."))
                else:
                    resultado.append(acceso("ok", f"El token es válido y vence en {int(dias)} días."))
    except requests.RequestException:
        resultado.append(acceso("atencion", "No se pudo conectar con Meta. Vuelve a probar en un momento."))
    return resultado


def verificar_webhook(actividad: dict, ahora: datetime) -> Chequeo:
    ultimo = actividad.get("webhook")
    if ultimo is None:
        return Chequeo("webhook", "Conexión con Meta (webhook)", "pendiente",
                       "Todavía no llega ningún aviso de Meta. Conecta el webhook (paso 5) y escríbele al número.")
    return Chequeo("webhook", "Conexión con Meta (webhook)", "ok", f"El último aviso de Meta llegó {hace(ultimo, ahora)}.")


def estado_general(chequeos: list[dict]) -> str:
    estados = {c["estado"] for c in chequeos}
    for estado in ("falla", "atencion", "pendiente"):
        if estado in estados:
            return estado
    return "ok" if chequeos else "pendiente"


class Verificador:
    """Lo que el panel usa para probar llaves. En los tests se reemplaza por un doble."""

    def __init__(self, version: str):
        self.version = version

    def claude(self, api_key: str, modelo: str) -> Chequeo:
        return verificar_claude(api_key, modelo)

    def meta(self, token, phone_number_id, app_id, app_secret, ahora) -> list[Chequeo]:
        return verificar_meta(token, phone_number_id, app_id, app_secret, self.version, ahora)

    def enviar_prueba(self, token: str, phone_number_id: str, numero: str, texto: str):
        return WhatsApp(token, phone_number_id, self.version).enviar_texto(numero, texto)
