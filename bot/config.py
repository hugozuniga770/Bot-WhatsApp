"""Configuracion del bot.

Lee las variables de entorno: el archivo .env en tu PC o las variables del
servicio en Render. Si falta algo obligatorio, se detiene con un mensaje claro
en vez de arrancar a medias.
"""
import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

OBLIGATORIAS = (
    "ANTHROPIC_API_KEY",
    "WHATSAPP_TOKEN",
    "PHONE_NUMBER_ID",
    "VERIFY_TOKEN",
    "APP_SECRET",
)


class ConfigIncompleta(Exception):
    """Falta una variable obligatoria o tiene un valor que no sirve."""


@dataclass(frozen=True)
class Config:
    whatsapp_token: str
    phone_number_id: str
    verify_token: str
    app_secret: str
    instrucciones: str
    graph_version: str = "v23.0"
    modelo: str = "claude-haiku-5-5"
    max_tokens: int = 600
    limite_historial: int = 20
    pausa_horas: float = 12.0
    duena_numero: str = ""
    mongodb_uri: str = ""
    mongodb_base: str = "bot_whatsapp"


def _numero(entorno, clave, defecto, tipo):
    valor = entorno.get(clave, "").strip()
    if not valor:
        return defecto
    try:
        return tipo(valor)
    except ValueError:
        raise ConfigIncompleta(f"{clave} debe ser un numero y vale '{valor}'.") from None


def cargar(entorno=None) -> Config:
    entorno = os.environ if entorno is None else entorno

    faltan = [clave for clave in OBLIGATORIAS if not entorno.get(clave, "").strip()]
    if faltan:
        raise ConfigIncompleta(
            "Faltan estas variables de entorno: "
            + ", ".join(faltan)
            + ". Revisa tu .env (en tu PC) o las variables del servicio en Render."
        )

    archivo = Path(entorno.get("INSTRUCCIONES_ARCHIVO", "").strip() or RAIZ / "instrucciones.md")
    if not archivo.is_file():
        raise ConfigIncompleta(f"No encuentro el manual del bot en {archivo}.")

    return Config(
        whatsapp_token=entorno["WHATSAPP_TOKEN"].strip(),
        phone_number_id=entorno["PHONE_NUMBER_ID"].strip(),
        verify_token=entorno["VERIFY_TOKEN"].strip(),
        app_secret=entorno["APP_SECRET"].strip(),
        instrucciones=archivo.read_text(encoding="utf-8"),
        graph_version=entorno.get("GRAPH_VERSION", "").strip() or "v23.0",
        modelo=entorno.get("CLAUDE_MODEL", "").strip() or "claude-haiku-5-5",
        max_tokens=_numero(entorno, "MAX_TOKENS", 600, int),
        limite_historial=_numero(entorno, "HISTORY_LIMIT", 20, int),
        pausa_horas=_numero(entorno, "PAUSA_HORAS", 12.0, float),
        duena_numero=entorno.get("DUENA_NUMERO", "").strip(),
        mongodb_uri=entorno.get("MONGODB_URI", "").strip(),
        mongodb_base=entorno.get("MONGODB_BASE", "").strip() or "bot_whatsapp",
    )
