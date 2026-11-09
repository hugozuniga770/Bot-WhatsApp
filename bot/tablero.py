"""Arma el resumen de una empresa para el panel: salud, creditos, uso y actividad."""
from datetime import date, datetime, timedelta

from . import reglas
from .manual import CAMPOS_NEGOCIO
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
        **puesta_en_marcha(empresa, almacen, actividad, chequeos),
    }


def puesta_en_marcha(empresa: dict, almacen, actividad: dict, chequeos: list[dict]) -> dict:
    """Qué le falta a una empresa para estar funcionando del todo (v3.2).

    Los pasos "opcionales" son los de la agenda: no todos los negocios la usan.
    """
    from .reservas import activo as agenda_activa

    verificada = bool((empresa.get("ultima_verificacion") or {}).get("chequeos")) and \
        not any(c["estado"] == "falla" for c in chequeos if c["clave"] != "webhook")
    llenos = sum(1 for campo, _, _ in CAMPOS_NEGOCIO if ((empresa.get("info") or {}).get(campo) or "").strip())
    usuarios = [u for u in almacen.usuarios_de(empresa["id"]) if u.get("activo")]
    turnos = (empresa.get("agenda") or {}).get("turnos") or []
    pasos = [
        {"titulo": "Llaves y número verificados", "ok": verificada, "opcional": False,
         "detalle": "Todo en verde en la última verificación." if verificada else "Toca «Verificar todo» y resuelve lo que salga en rojo."},
        {"titulo": "Webhook conectado", "ok": "webhook" in actividad, "opcional": False,
         "detalle": "Meta ya le habla al bot." if "webhook" in actividad else "Falta el paso 5 del alta (dirección y token en Meta)."},
        {"titulo": "Lo que el bot sabe del negocio", "ok": llenos >= 4, "opcional": False,
         "detalle": f"{llenos} de {len(CAMPOS_NEGOCIO)} temas cargados." + ("" if llenos >= 4 else " Completa el paso 2 en «Editar datos y llaves».")},
        {"titulo": "Accesos al panel del negocio", "ok": bool(usuarios), "opcional": False,
         "detalle": f"{len(usuarios)} acceso(s) activo(s)." if usuarios else "Crea al menos uno en «Agenda del negocio»."},
        {"titulo": "Bot activo para todos", "ok": empresa.get("estado") == "activa", "opcional": False,
         "detalle": "Responde a todos los clientes." if empresa.get("estado") == "activa" else "Cuando lo demás esté listo, toca «Activar para todos»."},
        {"titulo": "Horario cargado (agenda)", "ok": bool(turnos), "opcional": True,
         "detalle": f"{len(turnos)} turno(s) por semana." if turnos else "Lo carga la dueña en su panel, pestaña Horario."},
        {"titulo": "Reservas y adelantos por WhatsApp", "ok": agenda_activa(empresa), "opcional": True,
         "detalle": "El bot agenda y cobra." if agenda_activa(empresa) else "Se activa en Pagos → Configurar cobros (necesita horario y precios)."},
    ]
    obligatorios = [p for p in pasos if not p["opcional"]]
    return {"pasos": pasos, "listos": sum(p["ok"] for p in obligatorios), "total_pasos": len(obligatorios)}
