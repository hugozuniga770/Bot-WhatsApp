"""Reglas del bot.

Todas son funciones puras: no usan la red, ni la base de datos, ni el reloj.
La hora (`ahora`) siempre llega como parametro, asi los tests deciden la hora.
"""
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta

# El asistente escribe esta marca cuando hay que pasarle el chat a la duena.
MARCA_HUMANO = "[PASAR_A_HUMANO]"


@dataclass(frozen=True)
class MensajeEntrante:
    id: str
    numero: str
    tipo: str
    texto: str = ""


def extraer_mensajes(payload) -> list[MensajeEntrante]:
    """Saca los mensajes de clientes del JSON que manda Meta.

    Ignora los avisos de estado (enviado, entregado, leido), que llegan
    al mismo webhook pero no son mensajes.
    """
    mensajes = []
    if not isinstance(payload, dict):
        return mensajes
    for entrada in payload.get("entry") or []:
        for cambio in entrada.get("changes") or []:
            if cambio.get("field", "messages") != "messages":
                continue
            valor = cambio.get("value") or {}
            for m in valor.get("messages") or []:
                if not m.get("id") or not m.get("from"):
                    continue
                tipo = m.get("type", "")
                texto = ""
                if tipo == "text":
                    texto = ((m.get("text") or {}).get("body") or "").strip()
                mensajes.append(MensajeEntrante(m["id"], m["from"], tipo, texto))
    return mensajes


def firma_valida(cuerpo: bytes, cabecera: str | None, secreto: str) -> bool:
    """Comprueba que la peticion viene de Meta (cabecera X-Hub-Signature-256)."""
    if not secreto or not cabecera or not cabecera.startswith("sha256="):
        return False
    esperada = hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, cabecera[len("sha256="):])


def recortar_historial(historial: list[dict], limite: int) -> list[dict]:
    """Deja los ultimos `limite` mensajes y hace que empiece por el cliente."""
    recorte = [dict(m) for m in historial[-limite:]] if limite > 0 else []
    while recorte and recorte[0]["role"] != "user":
        recorte.pop(0)
    return recorte


def separar_marca(respuesta: str) -> tuple[str, bool]:
    """Quita la marca de derivacion del texto y dice si estaba."""
    pide_humano = MARCA_HUMANO in respuesta
    return respuesta.replace(MARCA_HUMANO, "").strip(), pide_humano


def esta_pausado(pausado_hasta: datetime | None, ahora: datetime) -> bool:
    return pausado_hasta is not None and ahora < pausado_hasta


def fin_de_pausa(ahora: datetime, horas: float) -> datetime:
    return ahora + timedelta(hours=horas)


def ocultar_numero(numero: str) -> str:
    """Para los registros (logs): solo los ultimos 4 digitos del cliente."""
    return "..." + numero[-4:] if len(numero) > 4 else "..."
