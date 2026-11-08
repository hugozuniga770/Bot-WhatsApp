"""Configuracion del servicio.

Desde la v2.0 las llaves de cada empresa NO van en variables de entorno: se
cargan desde el panel y se guardan cifradas en la base. Aqui solo quedan las
del servicio en si.
"""
import hashlib
import hmac
import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

OBLIGATORIAS = ("CLAVE_MAESTRA", "ADMIN_PASSWORD")


class ConfigIncompleta(Exception):
    """Falta una variable obligatoria o tiene un valor que no sirve."""


@dataclass(frozen=True)
class Config:
    clave_maestra: str
    admin_password: str
    plantilla_manual: str
    secret_key: str = ""
    database_url: str = ""
    url_publica: str = ""
    graph_version: str = "v23.0"
    zona_horaria: str = "America/La_Paz"
    cookie_segura: bool = True


def _derivar(clave_maestra: str, uso: str) -> str:
    return hmac.new(clave_maestra.encode(), uso.encode(), hashlib.sha256).hexdigest()


def cargar(entorno=None) -> Config:
    entorno = os.environ if entorno is None else entorno

    faltan = [clave for clave in OBLIGATORIAS if not entorno.get(clave, "").strip()]
    if faltan:
        raise ConfigIncompleta(
            "Faltan estas variables de entorno: "
            + ", ".join(faltan)
            + ". Revisa tu .env (en tu PC) o las variables del servicio en Render."
        )
    clave_maestra = entorno["CLAVE_MAESTRA"].strip()
    if len(clave_maestra) < 16:
        raise ConfigIncompleta("CLAVE_MAESTRA debe tener al menos 16 caracteres.")
    admin_password = entorno["ADMIN_PASSWORD"].strip()
    if len(admin_password) < 10:
        raise ConfigIncompleta("ADMIN_PASSWORD debe tener al menos 10 caracteres.")

    archivo = Path(entorno.get("INSTRUCCIONES_ARCHIVO", "").strip() or RAIZ / "instrucciones.md")
    if not archivo.is_file():
        raise ConfigIncompleta(f"No encuentro la plantilla del manual en {archivo}.")

    url_publica = (entorno.get("URL_PUBLICA", "").strip() or entorno.get("RENDER_EXTERNAL_URL", "").strip()).rstrip("/")
    return Config(
        clave_maestra=clave_maestra,
        admin_password=admin_password,
        plantilla_manual=archivo.read_text(encoding="utf-8"),
        secret_key=entorno.get("SECRET_KEY", "").strip() or _derivar(clave_maestra, "sesiones"),
        database_url=entorno.get("DATABASE_URL", "").strip(),
        url_publica=url_publica,
        graph_version=entorno.get("GRAPH_VERSION", "").strip() or "v23.0",
        zona_horaria=entorno.get("ZONA_HORARIA", "").strip() or "America/La_Paz",
        cookie_segura=bool(entorno.get("RENDER")) or url_publica.startswith("https://"),
    )
