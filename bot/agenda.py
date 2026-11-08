"""Agenda de cada negocio (v3.0): accesos, citas, pacientes y horario.

Lee y guarda con el almacén y decide con `reglas`. Las rutas (negocio.py y panel.py)
solo reciben el formulario y llaman a estas funciones.

Todo lo de un negocio se busca SIEMPRE con su `empresa_id`: un usuario de una empresa
no puede ver ni tocar lo de otra (BOT-RF-21).
"""
import secrets
from datetime import date, datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from . import reglas

# Hash de una contraseña cualquiera: se compara cuando el usuario no existe, para que
# la respuesta tarde lo mismo y no delate qué usuarios existen.
_HASH_DE_RELLENO = generate_password_hash("relleno-que-nunca-coincide")
_LETRAS_CLAVE = "abcdefghjkmnpqrstuvwxyz23456789"  # sin 0/o ni 1/l, que se confunden


# ------------------------------------------------------------------ accesos
def clave_temporal() -> str:
    """Una contraseña fácil de dictar por WhatsApp, por ejemplo 'kp4m-7xrt-q9ad'."""
    return "-".join("".join(secrets.choice(_LETRAS_CLAVE) for _ in range(4)) for _ in range(3))


def crear_usuario(almacen, empresa_id: int, nombre: str, usuario: str, rol: str, ahora: datetime):
    """(usuario, clave temporal, errores). La clave se muestra una sola vez; se guarda su hash."""
    usuario = reglas.normalizar_usuario(usuario)
    errores = reglas.errores_de_usuario(usuario, nombre)
    if rol not in reglas.ROLES:
        errores["rol"] = "Elige el rol."
    if not errores and almacen.usuario_por_login(usuario):
        errores["usuario"] = "Ese usuario ya existe. Prueba con otro, por ejemplo agregando el nombre del negocio."
    if errores:
        return None, None, errores
    clave = clave_temporal()
    try:
        nuevo = almacen.crear_usuario(empresa_id, usuario, nombre.strip(), rol, generate_password_hash(clave), ahora)
    except ValueError:
        return None, None, {"usuario": "Ese usuario ya existe. Prueba con otro."}
    return nuevo, clave, {}


def restablecer_clave(almacen, usuario_id: int) -> str:
    clave = clave_temporal()
    almacen.actualizar_usuario(usuario_id, {"clave_hash": generate_password_hash(clave), "debe_cambiar": True})
    return clave


def autenticar(almacen, usuario: str, clave: str, ahora: datetime) -> dict | None:
    encontrado = almacen.usuario_por_login(reglas.normalizar_usuario(usuario))
    valido = check_password_hash(encontrado["clave_hash"] if encontrado else _HASH_DE_RELLENO, clave or "")
    if not encontrado or not valido or not encontrado["activo"]:
        return None
    return almacen.actualizar_usuario(encontrado["id"], {"ultimo_ingreso": ahora})


def cambiar_clave(almacen, usuario: dict, actual: str, nueva: str, repetida: str) -> dict:
    if not check_password_hash(usuario["clave_hash"], actual or ""):
        return {"actual": "La contraseña actual no es correcta."}
    errores = reglas.errores_de_clave(nueva, repetida)
    if not errores and nueva == actual:
        errores = {"nueva": "Elige una contraseña distinta de la temporal."}
    if not errores:
        almacen.actualizar_usuario(usuario["id"], {"clave_hash": generate_password_hash(nueva), "debe_cambiar": False})
    return errores


# ------------------------------------------------------------------ pacientes
def leer_paciente(form) -> tuple[dict, dict]:
    datos = {"nombre": " ".join(form.get("nombre", "").split()),
             "telefono": reglas.normalizar_numero(form.get("telefono", ""))}
    errores = {}
    if not datos["nombre"]:
        errores["nombre"] = "Escribe el nombre del paciente."
    if datos["telefono"] and not 8 <= len(datos["telefono"]) <= 15:
        errores["telefono"] = "Escribe el número con código de país, por ejemplo 591 70000000."
    return datos, errores


def guardar_paciente(almacen, empresa_id: int, form, ahora: datetime, paciente_id: int | None = None):
    """(paciente, errores). Un teléfono no se puede repetir dentro del mismo negocio."""
    datos, errores = leer_paciente(form)
    if not errores and datos["telefono"]:
        otro = almacen.paciente_por_telefono(empresa_id, datos["telefono"])
        if otro and otro["id"] != paciente_id:
            errores["telefono"] = f"Ese número ya es de {otro['nombre']}."
    if errores:
        return None, errores
    if paciente_id:
        return almacen.actualizar_paciente(empresa_id, paciente_id, datos), {}
    return almacen.crear_paciente(empresa_id, datos["nombre"], datos["telefono"], ahora), {}


# ------------------------------------------------------------------ citas
def _numero(texto: str, campo: str, errores: dict, nombre: str):
    texto = (texto or "").strip().replace(",", ".")
    if not texto:
        return None
    try:
        valor = float(texto)
        if valor < 0:
            raise ValueError
        return valor
    except ValueError:
        errores[campo] = f"{nombre}: escribe solo el monto, por ejemplo 125."
        return None


def guardar_cita(almacen, empresa: dict, form, ahora: datetime, zona: str, cita: dict | None = None):
    """Crea o cambia (reprograma) una cita. (cita, errores).

    El paciente puede ser uno que ya existe (paciente_id) o uno nuevo (nombre y teléfono):
    si el teléfono ya está, se usa ese paciente. No deja guardar si el horario
    choca con otra cita que lo ocupa.
    """
    eid = empresa["id"]
    errores = {}

    paciente = None
    if form.get("paciente_id", "").isdigit():
        paciente = almacen.paciente(eid, int(form["paciente_id"]))
        if not paciente:
            errores["paciente"] = "Ese paciente no existe."
    elif not cita:
        datos, errores_p = leer_paciente(form)
        errores.update(errores_p)
        if not errores_p:
            paciente = almacen.paciente_por_telefono(eid, datos["telefono"]) if datos["telefono"] else None
    else:
        paciente = almacen.paciente(eid, cita["paciente_id"])

    try:
        dia = date.fromisoformat(form.get("fecha", ""))
    except ValueError:
        dia, errores["fecha"] = None, "Elige la fecha."
    inicio = reglas.momento_local(dia, form.get("hora", ""), zona) if dia else None
    if dia and not inicio:
        errores["hora"] = "Escribe la hora así: 10:30."
    duracion = int(_numero(form.get("duracion", ""), "duracion", errores, "Duración")
                   or (empresa.get("agenda") or {}).get("duracion") or reglas.DURACION_POR_DEFECTO)
    if not 5 <= duracion <= 480:
        errores["duracion"] = "La duración va de 5 a 480 minutos."
    adelanto = _numero(form.get("adelanto", ""), "adelanto", errores, "Adelanto") or 0.0

    if inicio and "duracion" not in errores:
        fin = inicio + timedelta(minutes=duracion)
        ocupadas = reglas.choques(inicio, fin, almacen.citas(eid, inicio, fin), salvo_id=cita["id"] if cita else None)
        if ocupadas:
            o = ocupadas[0]
            errores["hora"] = (f"Ese horario ya está ocupado por {o['paciente_nombre']} "
                               f"({o['inicio'].astimezone(inicio.tzinfo):%H:%M} a {o['fin'].astimezone(inicio.tzinfo):%H:%M}).")
    if errores:
        return None, errores

    if not paciente:  # paciente nuevo: se crea recién cuando todo lo demás está bien
        paciente = almacen.crear_paciente(eid, datos["nombre"], datos["telefono"], ahora)
    valores = {"paciente_id": paciente["id"], "inicio": inicio, "fin": inicio + timedelta(minutes=duracion),
               "sede": form.get("sede", "").strip()[:60], "servicio": " ".join(form.get("servicio", "").split())[:120],
               "adelanto": adelanto}
    if cita:
        return almacen.actualizar_cita(eid, cita["id"], valores, ahora), {}
    return almacen.crear_cita(eid, {**valores, "estado": "confirmada", "origen": "panel"}, ahora), {}


def cambiar_estado(almacen, empresa_id: int, cita: dict, estado: str, form, ahora: datetime):
    """(cita, errores). Al marcar 'Atendida' se anota cuánto se cobró y cómo (para las cuentas)."""
    if estado not in reglas.ESTADOS_CITA:
        return None, {"estado": "Estado desconocido."}
    cambios, errores = {"estado": estado}, {}
    if estado == "atendida":
        cobrado = _numero(form.get("cobrado", ""), "cobrado", errores, "Cobrado")
        metodo = form.get("metodo_pago", "")
        if cobrado is None and "cobrado" not in errores:
            errores["cobrado"] = "Escribe cuánto se cobró en la cita (0 si no se cobró nada)."
        if metodo not in reglas.METODOS_PAGO:
            errores["metodo_pago"] = "Elige cómo pagó."
        cambios.update(cobrado=cobrado, metodo_pago=metodo)
    elif estado == "confirmada":
        ocupadas = reglas.choques(cita["inicio"], cita["fin"], almacen.citas(empresa_id, cita["inicio"], cita["fin"]), salvo_id=cita["id"])
        if ocupadas:
            errores["estado"] = f"No se puede volver a confirmar: ese horario ya lo tiene {ocupadas[0]['paciente_nombre']}."
    if errores:
        return None, errores
    return almacen.actualizar_cita(empresa_id, cita["id"], cambios, ahora), {}


# ------------------------------------------------------------------ horario
def leer_horario(form) -> tuple[dict, dict]:
    """El formulario trae filas dia_N, sede_N, desde_N, hasta_N. Las filas vacías se ignoran."""
    turnos, i = [], 0
    while f"dia_{i}" in form:
        fila = {k: form.get(f"{k}_{i}", "").strip() for k in ("dia", "sede", "desde", "hasta")}
        i += 1
        if not (fila["desde"] or fila["hasta"] or fila["sede"]):
            continue
        fila["dia"] = int(fila["dia"]) if fila["dia"].isdigit() else None
        fila["sede"] = fila["sede"][:60]
        turnos.append(fila)
    errores = {f"fila_{k}": v for k, v in reglas.errores_de_horario(turnos).items()}
    try:
        duracion = int(form.get("duracion", "") or reglas.DURACION_POR_DEFECTO)
        if not 5 <= duracion <= 240:
            raise ValueError
    except ValueError:
        duracion, errores["duracion"] = reglas.DURACION_POR_DEFECTO, "La duración del turno va de 5 a 240 minutos."
    if not errores:  # con errores no se ordena, para que cada error quede en su fila del formulario
        turnos.sort(key=lambda t: (t["dia"], reglas.leer_hora(t["desde"])))
    return {"duracion": duracion, "turnos": turnos}, errores


def sedes(empresa: dict) -> list[str]:
    vistas = []
    for t in (empresa.get("agenda") or {}).get("turnos", []):
        if t.get("sede") and t["sede"] not in vistas:
            vistas.append(t["sede"])
    return vistas


def leer_bloqueo(form) -> tuple[dict, dict]:
    try:
        desde = date.fromisoformat(form.get("desde", ""))
        hasta = date.fromisoformat(form.get("hasta", "") or form.get("desde", ""))
    except ValueError:
        return {}, {"bloqueo": "Elige las fechas."}
    if hasta < desde:
        return {}, {"bloqueo": "La fecha final tiene que ser igual o posterior a la inicial."}
    return {"desde": desde, "hasta": hasta, "motivo": " ".join(form.get("motivo", "").split())[:80]}, {}


# ------------------------------------------------------------------ vistas
def dias_con_agenda(almacen, empresa: dict, dias: list[date], zona: str) -> list[dict]:
    """La agenda de cada día de la lista (una semana o un día), con una sola consulta a la base."""
    desde, _ = reglas.rango_del_dia(dias[0], zona)
    _, hasta = reglas.rango_del_dia(dias[-1], zona)
    citas = almacen.citas(empresa["id"], desde, hasta)
    bloqueos = almacen.bloqueos(empresa["id"], dias[0], dias[-1])
    return [reglas.agenda_del_dia(d, empresa.get("agenda") or {}, citas, bloqueos, zona) for d in dias]


def resumen_paciente(citas: list[dict]) -> dict:
    """Cuántas citas tuvo (sin las canceladas) y cuánto pagó en total.

    Los adelantos cuentan siempre, también los de citas canceladas, porque no se devuelven.
    Lo cobrado en la cita se suma solo en las atendidas.
    """
    return {
        "citas": sum(1 for c in citas if c["estado"] != "cancelada"),
        "pagado": sum(c["adelanto"] or 0 for c in citas) + sum(c["cobrado"] or 0 for c in citas if c["estado"] == "atendida"),
    }


# ------------------------------------------------------------------ cobros y adelantos (v3.1)
def leer_cobro(form, sedes: list[str], actual: dict) -> tuple[dict, dict]:
    """El formulario de Cobros: (configuración, errores). El QR se maneja aparte (es un archivo)."""
    errores = {}
    nuevo = {"activo": form.get("activo") == "1", "qr_id": actual.get("qr_id"),
             "instrucciones": form.get("instrucciones", "").strip()[:800],
             "aviso_numero": reglas.normalizar_numero(form.get("aviso_numero", ""))}
    for campo, nombre, minimo, maximo in (("porcentaje", "El porcentaje", 1, 100), ("plazo_horas", "El plazo", 0.5, 48)):
        try:
            valor = float((form.get(campo) or "").replace(",", "."))
            if not minimo <= valor <= maximo:
                raise ValueError
            nuevo[campo] = valor
        except ValueError:
            errores[campo] = f"{nombre} va de {minimo:g} a {maximo:g}."
    if nuevo["aviso_numero"] and not 8 <= len(nuevo["aviso_numero"]) <= 15:
        errores["aviso_numero"] = "Escribe el número con código de país, por ejemplo 591 70000000."
    nuevo["valoracion"], nuevo["ubicaciones"] = {}, {}
    for i, sede in enumerate(sedes):
        texto = (form.get(f"valoracion_{i}") or "").replace(",", ".").strip()
        if texto:
            try:
                precio = float(texto)
                if precio < 0:
                    raise ValueError
                nuevo["valoracion"][sede] = precio
            except ValueError:
                errores[f"valoracion_{i}"] = "Escribe solo el precio en bolivianos, por ejemplo 250."
        ubicacion = " ".join((form.get(f"ubicacion_{i}") or "").split())[:300]
        if ubicacion:
            nuevo["ubicaciones"][sede] = ubicacion
    if nuevo["activo"] and not nuevo["valoracion"]:
        errores["activo"] = "Para que el bot agende, carga el precio de la valoración de al menos una sede."
    return nuevo, errores
