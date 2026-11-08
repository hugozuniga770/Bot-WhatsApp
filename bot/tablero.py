"""Arma el resumen de una empresa para el panel: salud, creditos, uso y actividad."""
from datetime import date, datetime, timedelta

from . import reglas
from .verificaciones import estado_general, verificar_webhook

DIAS_GRAFICO = 14


def resumen(empresa: dict, almacen, ahora: datetime, zona: str) -> dict:
    hoy = reglas.dia_local(ahora, zona)
    precio_e = float(empresa.get("precio_entrada") or 0)
    precio_s = float(empresa.get("precio_salida") or 0)
    saldo_desde = date.fromisoformat(empresa["saldo_desde"]) if empresa.get("saldo_desde") else None

    desde = min(hoy - timedelta(days=DIAS_GRAFICO), saldo_desde or hoy)
    uso = almacen.uso(empresa["id"], desde)
    actividad = almacen.actividad(empresa["id"])

    verificacion = empresa.get("ultima_verificacion") or {}
    chequeos = [c for c in verificacion.get("chequeos", []) if c["clave"] != "webhook"]
    chequeos.append(verificar_webhook(actividad, ahora).a_dict())  # el webhook siempre en vivo

    serie = reglas.serie_diaria(uso, hoy, DIAS_GRAFICO, precio_e, precio_s)
    return {
        "empresa": empresa,
        "credito": reglas.resumen_credito(empresa.get("saldo_usd"), saldo_desde, uso, hoy, precio_e, precio_s),
        "serie": serie,
        "hoy": serie[-1],
        "actividad": actividad,
        "chequeos": chequeos,
        "saldo_desde": saldo_desde,
        "verificado": datetime.fromisoformat(verificacion["fecha"]) if verificacion.get("fecha") else None,
        "salud": estado_general(chequeos),
        "errores_24h": almacen.contar_eventos(empresa["id"], "error", ahora - timedelta(hours=24)),
    }
