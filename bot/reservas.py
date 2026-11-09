"""Reservas por WhatsApp (etapa 2): el bot ofrece turnos, aparta el horario y cobra el adelanto.

Reglas acordadas con el negocio (docs/decisiones.md, D-24 y D-25):
- Paciente nuevo: paga el 50 % de la valoración de su sede para reservar.
- Paciente que ya se atendió y quiere sesiones de tratamiento: por ahora lo agenda una
  persona (el bot lo deriva). El cobro del 50 % del tratamiento queda para la etapa 2b.
- Tiene `plazo_horas` (2 por defecto) para mandar la foto del comprobante; si no, el
  horario se libera y el bot le avisa.
- La asistente o la dueña revisan el banco y aprueban o rechazan desde el panel.
- Reprogramar sin perder el adelanto: hasta 24 h antes. El adelanto no se devuelve.

Las funciones reciben el almacén y la hora (`ahora`): no leen el reloj ni la red.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import reglas
from .agenda import candado

DIAS_A_MIRAR = 14
MAX_TURNOS = 6
ANTICIPACION_MINIMA = timedelta(hours=2)
HORAS_PARA_REPROGRAMAR = 24
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre")
ACTIVAS = ("pendiente_pago", "por_revisar", "confirmada")

COBRO_POR_DEFECTO = {
    "activo": False,
    "porcentaje": 50,
    "plazo_horas": 2,
    "valoracion": {},       # sede -> precio de la valoración en Bs
    "instrucciones": "",    # banco, cuenta, titular, cómo pagar
    "qr_id": None,          # imagen del QR de cobro (tabla archivos)
    "aviso_numero": "",     # a quién avisar de un comprobante (la asistente)
    "ubicaciones": {},      # sede -> dirección o enlace de Maps, para la confirmación
}


# ------------------------------------------------------------------ configuración
def cobro(empresa: dict) -> dict:
    datos = dict(COBRO_POR_DEFECTO)
    datos.update(empresa.get("cobro") or {})
    return datos


def activo(empresa: dict) -> bool:
    """El bot agenda solo si el negocio lo activó y cargó su horario."""
    return bool(cobro(empresa)["activo"] and (empresa.get("agenda") or {}).get("turnos"))


def precio_valoracion(empresa: dict, sede: str):
    precios = cobro(empresa)["valoracion"]
    for nombre, precio in precios.items():
        if nombre.strip().lower() == (sede or "").strip().lower() and precio not in (None, ""):
            return float(precio)
    return None


def adelanto_de(empresa: dict, precio: float) -> float:
    return round(precio * float(cobro(empresa)["porcentaje"]) / 100, 2)


# ------------------------------------------------------------------ textos
def texto_dia(momento: datetime, zona: str) -> str:
    local = momento.astimezone(ZoneInfo(zona))
    return f"{reglas.DIAS[local.weekday()]} {local.day} de {MESES[local.month - 1]}"


def resumen(cita: dict, zona: str) -> dict:
    local = cita["inicio"].astimezone(ZoneInfo(zona))
    return {"cita_id": cita["id"], "dia": texto_dia(cita["inicio"], zona), "hora": f"{local:%H:%M}",
            "sede": cita["sede"], "servicio": cita["servicio"], "estado": reglas.ESTADOS_CITA.get(cita["estado"], cita["estado"]),
            "adelanto_pedido": cita.get("adelanto_pedido") or 0, "adelanto_pagado": cita.get("adelanto") or 0}


def turno_id(inicio: datetime, sede: str, zona: str) -> str:
    return f"{inicio.astimezone(ZoneInfo(zona)):%Y-%m-%dT%H:%M}|{sede}"


def leer_turno_id(texto: str, zona: str):
    try:
        momento, sede = (texto or "").split("|", 1)
        dia, hora = momento.split("T")
        return reglas.momento_local(date.fromisoformat(dia), hora, zona), sede
    except ValueError:
        return None, None


# ------------------------------------------------------------------ consultas
def turnos_libres(almacen, empresa: dict, ahora: datetime, zona: str, sede: str = "", maximo: int = MAX_TURNOS) -> list[dict]:
    """Los próximos turnos libres (desde 2 h después de ahora, dentro de 14 días)."""
    agenda = empresa.get("agenda") or {}
    hoy = reglas.dia_local(ahora, zona)
    desde_dia, _ = reglas.rango_del_dia(hoy, zona)
    citas = almacen.citas(empresa["id"], desde_dia, desde_dia + timedelta(days=DIAS_A_MIRAR + 1))
    bloqueos = almacen.bloqueos(empresa["id"], hoy, hoy + timedelta(days=DIAS_A_MIRAR))
    filtro = (sede or "").strip().lower()
    libres = []
    for n in range(DIAS_A_MIRAR):
        dia = hoy + timedelta(days=n)
        for item in reglas.agenda_del_dia(dia, agenda, citas, bloqueos, zona)["items"]:
            if item["tipo"] != "libre":
                continue
            t = item["turno"]
            if t["inicio"] < ahora + ANTICIPACION_MINIMA or (filtro and filtro not in t["sede"].lower()):
                continue
            libres.append({"turno": turno_id(t["inicio"], t["sede"], zona), "dia": texto_dia(t["inicio"], zona),
                           "hora": f"{t['inicio'].astimezone(ZoneInfo(zona)):%H:%M}", "sede": t["sede"]})
            if len(libres) >= maximo:
                return libres
    return libres


def reserva_activa(almacen, empresa_id: int, numero: str, ahora: datetime):
    """La próxima cita que este número tiene en curso (por pagar, por revisar o confirmada)."""
    paciente = almacen.paciente_por_telefono(empresa_id, numero)
    if not paciente:
        return None
    futuras = [c for c in almacen.citas_de_paciente(empresa_id, paciente["id"])
               if c["estado"] in ACTIVAS and c["fin"] > ahora]
    return min(futuras, key=lambda c: c["inicio"]) if futuras else None


def es_paciente_nuevo(almacen, empresa_id: int, paciente) -> bool:
    if not paciente:
        return True
    return not any(c["estado"] == "atendida" for c in almacen.citas_de_paciente(empresa_id, paciente["id"]))


def _turno_valido(almacen, empresa: dict, inicio: datetime, sede: str, ahora: datetime, zona: str, salvo_id=None) -> str:
    """'' si el turno existe en el horario y está libre; si no, el motivo."""
    if not inicio:
        return "turno_invalido"
    if inicio < ahora + ANTICIPACION_MINIMA:
        return "muy_pronto"
    dia = inicio.astimezone(ZoneInfo(zona)).date()
    if reglas.esta_bloqueado(dia, almacen.bloqueos(empresa["id"], dia, dia)):
        return "dia_bloqueado"
    turno = next((t for t in reglas.turnos_del_horario(dia, empresa.get("agenda") or {}, zona)
                  if t["inicio"] == inicio and t["sede"].lower() == (sede or "").lower()), None)
    if not turno:
        return "turno_invalido"
    if reglas.choques(turno["inicio"], turno["fin"], almacen.citas(empresa["id"], turno["inicio"], turno["fin"]), salvo_id=salvo_id):
        return "ocupado"
    return ""


# ------------------------------------------------------------------ acciones
def reservar(almacen, empresa: dict, numero: str, turno: str, nombre: str, motivo: str, ahora: datetime, zona: str) -> dict:
    with candado(empresa["id"]):
        return _reservar(almacen, empresa, numero, turno, nombre, motivo, ahora, zona)


def _reservar(almacen, empresa: dict, numero: str, turno: str, nombre: str, motivo: str, ahora: datetime, zona: str) -> dict:
    eid = empresa["id"]
    actual = reserva_activa(almacen, eid, numero, ahora)
    if actual:
        return {"ok": False, "motivo": "ya_tiene_reserva", "reserva": resumen(actual, zona)}
    inicio, sede = leer_turno_id(turno, zona)
    problema = _turno_valido(almacen, empresa, inicio, sede, ahora, zona)
    if problema:
        return {"ok": False, "motivo": problema}
    paciente = almacen.paciente_por_telefono(eid, numero)
    if not es_paciente_nuevo(almacen, eid, paciente):
        return {"ok": False, "motivo": "paciente_con_historial",
                "explicacion": "Las sesiones de tratamiento las agenda una persona: deriva la conversación."}
    precio = precio_valoracion(empresa, sede)
    if precio is None:
        return {"ok": False, "motivo": "sin_precio_de_valoracion",
                "explicacion": "Falta el precio de la valoración de esa sede: deriva la conversación."}
    nombre = " ".join((nombre or "").split())[:80]
    if len(nombre) < 3:
        return {"ok": False, "motivo": "falta_nombre", "explicacion": "Pide el nombre completo del paciente."}
    if not paciente:
        paciente = almacen.crear_paciente(eid, nombre, numero, ahora)
    duracion = timedelta(minutes=int((empresa.get("agenda") or {}).get("duracion") or reglas.DURACION_POR_DEFECTO))
    plazo = float(cobro(empresa)["plazo_horas"])
    monto = adelanto_de(empresa, precio)
    servicio = "Valoración" + (f": {' '.join(motivo.split())[:90]}" if motivo and motivo.strip() else "")
    cita = almacen.crear_cita(eid, {"paciente_id": paciente["id"], "inicio": inicio, "fin": inicio + duracion,
                                    "sede": sede, "servicio": servicio, "estado": "pendiente_pago", "origen": "bot",
                                    "adelanto_pedido": monto, "reserva_vence": ahora + timedelta(hours=plazo)}, ahora)
    almacen.registrar_evento(eid, "reserva", f"Reserva por WhatsApp: {texto_dia(inicio, zona)} {resumen(cita, zona)['hora']} en {sede}, adelanto Bs {monto:g}.", ahora)
    datos = cobro(empresa)
    return {"ok": True, **resumen(cita, zona), "adelanto": monto, "precio_valoracion": precio,
            "plazo_horas": plazo, "como_pagar": datos["instrucciones"] or "Pide los datos de pago a la asistente.",
            "se_envia_qr": bool(datos["qr_id"])}


def reprogramar(almacen, empresa: dict, numero: str, turno: str, ahora: datetime, zona: str) -> dict:
    with candado(empresa["id"]):
        return _reprogramar(almacen, empresa, numero, turno, ahora, zona)


def _reprogramar(almacen, empresa: dict, numero: str, turno: str, ahora: datetime, zona: str) -> dict:
    actual = reserva_activa(almacen, empresa["id"], numero, ahora)
    if not actual:
        return {"ok": False, "motivo": "sin_reserva"}
    if actual["estado"] == "confirmada" and actual["inicio"] - ahora < timedelta(hours=HORAS_PARA_REPROGRAMAR):
        return {"ok": False, "motivo": "menos_de_24_horas",
                "explicacion": "Faltan menos de 24 h: ya no se puede reprogramar sin perder el adelanto. Deriva la conversación."}
    inicio, sede = leer_turno_id(turno, zona)
    problema = _turno_valido(almacen, empresa, inicio, sede, ahora, zona, salvo_id=actual["id"])
    if problema:
        return {"ok": False, "motivo": problema}
    duracion = actual["fin"] - actual["inicio"]
    cambiada = almacen.actualizar_cita(empresa["id"], actual["id"], {"inicio": inicio, "fin": inicio + duracion, "sede": sede}, ahora)
    almacen.registrar_evento(empresa["id"], "reserva", f"Reprogramada por WhatsApp: {texto_dia(inicio, zona)} {resumen(cambiada, zona)['hora']} en {sede}.", ahora)
    return {"ok": True, **resumen(cambiada, zona)}


def cancelar(almacen, empresa: dict, numero: str, ahora: datetime, zona: str) -> dict:
    actual = reserva_activa(almacen, empresa["id"], numero, ahora)
    if not actual:
        return {"ok": False, "motivo": "sin_reserva"}
    almacen.actualizar_cita(empresa["id"], actual["id"], {"estado": "cancelada"}, ahora)
    almacen.registrar_evento(empresa["id"], "reserva", f"Cancelada por WhatsApp: {texto_dia(actual['inicio'], zona)} en {actual['sede']}.", ahora)
    pagado = actual.get("adelanto") or 0
    return {"ok": True, **resumen(actual, zona), "adelanto_pagado": pagado,
            "nota": "El adelanto no se devuelve." if pagado else "No había pagado adelanto."}


def vencer(almacen, empresa: dict, ahora: datetime) -> list[dict]:
    """Libera las reservas sin comprobante cuyo plazo pasó. Devuelve las que liberó."""
    hoy = ahora - timedelta(days=1)
    pendientes = [c for c in almacen.citas(empresa["id"], hoy, ahora + timedelta(days=DIAS_A_MIRAR + 2))
                  if c["estado"] == "pendiente_pago" and c.get("reserva_vence") and c["reserva_vence"] <= ahora]
    liberadas = []
    for c in pendientes:
        liberadas.append(almacen.actualizar_cita(empresa["id"], c["id"], {"estado": "cancelada"}, ahora))
        almacen.registrar_evento(empresa["id"], "reserva", f"Horario liberado: {c['paciente_nombre']} no mandó el comprobante a tiempo.", ahora)
    return liberadas


# ------------------------------------------------------------------ herramientas para Claude
HERRAMIENTAS = [
    {"name": "ver_turnos_libres",
     "description": "Lista los próximos turnos libres de la agenda (desde 2 horas después de ahora, hasta 14 días). Úsala antes de ofrecer horarios; nunca inventes horarios.",
     "input_schema": {"type": "object", "properties": {
         "sede": {"type": "string", "description": "Sede que prefiere el paciente. Vacío para ver todas."}}}},
    {"name": "reservar_turno",
     "description": "Aparta un turno para el paciente que escribe, como valoración, en estado pendiente de pago. Devuelve el adelanto a pagar y cómo pagarlo.",
     "input_schema": {"type": "object", "required": ["turno", "nombre"], "properties": {
         "turno": {"type": "string", "description": "El campo 'turno' exacto que devolvió ver_turnos_libres."},
         "nombre": {"type": "string", "description": "Nombre y apellido del paciente."},
         "motivo": {"type": "string", "description": "Motivo de consulta, en pocas palabras."}}}},
    {"name": "mi_reserva",
     "description": "Muestra la reserva en curso del paciente que escribe (estado, día, hora, sede, adelanto).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "reprogramar_reserva",
     "description": "Mueve la reserva del paciente a otro turno libre, sin perder el adelanto, si faltan más de 24 h.",
     "input_schema": {"type": "object", "required": ["turno"], "properties": {
         "turno": {"type": "string", "description": "El campo 'turno' exacto que devolvió ver_turnos_libres."}}}},
    {"name": "cancelar_reserva",
     "description": "Cancela la reserva del paciente. El adelanto pagado no se devuelve. Úsala solo si el paciente lo pide claramente.",
     "input_schema": {"type": "object", "properties": {}}},
]


def ejecutar_herramienta(nombre: str, entrada: dict, almacen, empresa: dict, numero: str, ahora: datetime, zona: str) -> dict:
    entrada = entrada or {}
    if nombre == "ver_turnos_libres":
        turnos = turnos_libres(almacen, empresa, ahora, zona, entrada.get("sede", ""))
        return {"turnos": turnos} if turnos else {"turnos": [], "nota": "No hay turnos libres en los próximos 14 días para eso."}
    if nombre == "reservar_turno":
        return reservar(almacen, empresa, numero, entrada.get("turno", ""), entrada.get("nombre", ""), entrada.get("motivo", ""), ahora, zona)
    if nombre == "mi_reserva":
        actual = reserva_activa(almacen, empresa["id"], numero, ahora)
        return {"reserva": resumen(actual, zona)} if actual else {"reserva": None}
    if nombre == "reprogramar_reserva":
        return reprogramar(almacen, empresa, numero, entrada.get("turno", ""), ahora, zona)
    if nombre == "cancelar_reserva":
        return cancelar(almacen, empresa, numero, ahora, zona)
    return {"ok": False, "motivo": "herramienta_desconocida"}


def instrucciones(empresa: dict, ahora: datetime, zona: str) -> str:
    """Lo que se agrega al manual cuando el bot agenda: la hora actual y las reglas de la reserva."""
    datos = cobro(empresa)
    precios = ", ".join(f"{s}: Bs {float(p):g}" for s, p in datos["valoracion"].items() if p not in (None, "")) or "sin cargar"
    local = ahora.astimezone(ZoneInfo(zona))
    return f"""
# Agenda y reservas
Ahora es {texto_dia(ahora, zona)} de {local.year}, {local:%H:%M} (hora de Bolivia).
Puedes agendar valoraciones con las herramientas. Cómo hacerlo:
1. Pregunta el motivo de consulta y la sede que prefiere, si no lo dijo.
2. Usa ver_turnos_libres y ofrece como mucho 2 o 3 opciones. Nunca inventes horarios.
3. Cuando elija, pide su nombre y apellido y usa reservar_turno con el campo "turno" exacto.
4. Explica el adelanto que devuelve la herramienta ({float(datos['porcentaje']):g} % de la valoración; precios por sede: {precios}), cómo pagarlo y que tiene {float(datos['plazo_horas']):g} horas para mandar la FOTO del comprobante por este chat; si no, el horario se libera.
5. Cuando mande el comprobante, el sistema le responde solo; tú no confirmes pagos.
Reglas: el adelanto no se devuelve; se puede reprogramar sin perderlo hasta 24 h antes (reprogramar_reserva). Si alguien ya se atendió y quiere sesiones de tratamiento, o una herramienta dice que derives, pásale la conversación a la persona a cargo.
"""
