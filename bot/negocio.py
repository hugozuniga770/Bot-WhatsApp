"""Panel de cada negocio (/negocio): la agenda que usan la dueña y su asistente (v3.0).

Cada usuario entra con su usuario y contraseña y ve SOLO su empresa: todas las
consultas usan g.empresa["id"]. No ve llaves, créditos ni otras empresas (eso es
del panel de administración).
"""
from datetime import date, timedelta
from functools import wraps

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request, session,
                   url_for)

from . import agenda as A
from . import reglas
from .app import ctx
from .seguridad import Limitador, exigir_csrf, ip_cliente, token_csrf

negocio = Blueprint("negocio", __name__, url_prefix="/negocio")


def limitador() -> Limitador:
    return current_app.extensions.setdefault("limitador_negocio", Limitador())


def requiere_usuario(vista):
    """Exige un usuario activo de una empresa. Si tiene una contraseña temporal, lo manda a cambiarla."""
    @wraps(vista)
    def envoltura(*args, **kwargs):
        c = ctx()
        usuario = c.almacen.usuario(session["usuario_id"]) if session.get("usuario_id") else None
        if not usuario or not usuario["activo"]:
            session.pop("usuario_id", None)
            return redirect(url_for("negocio.entrar", siguiente=request.path))
        if request.method == "POST":
            exigir_csrf()
        g.usuario = usuario
        g.empresa = c.almacen.empresa(usuario["empresa_id"])
        if usuario["debe_cambiar"] and request.endpoint != "negocio.clave":
            return redirect(url_for("negocio.clave"))
        return vista(*args, **kwargs)
    return envoltura


def _zona() -> str:
    return ctx().config.zona_horaria


def _hoy() -> date:
    return reglas.dia_local(ctx().ahora(), _zona())


def _fecha(texto: str, por_defecto: date) -> date:
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        return por_defecto


def _cita_o_404(cid: int) -> dict:
    return ctx().almacen.cita(g.empresa["id"], cid) or abort(404)


def _paciente_o_404(pid: int) -> dict:
    return ctx().almacen.paciente(g.empresa["id"], pid) or abort(404)


# ------------------------------------------------------------------ acceso
@negocio.route("/entrar", methods=["GET", "POST"])
def entrar():
    error = None
    if request.method == "POST":
        exigir_csrf()
        ip = ip_cliente()
        c = ctx()
        if limitador().bloqueado(ip):
            error = "Demasiados intentos. Espera 15 minutos y vuelve a probar."
        else:
            usuario = A.autenticar(c.almacen, request.form.get("usuario", ""), request.form.get("clave", ""), c.ahora())
            if usuario:
                limitador().limpiar(ip)
                session.clear()
                session["usuario_id"] = usuario["id"]
                session.permanent = True
                token_csrf()
                if usuario["debe_cambiar"]:
                    return redirect(url_for(".clave"))
                siguiente = request.args.get("siguiente", "")
                return redirect(siguiente if siguiente.startswith("/negocio") else url_for(".semana"))
            limitador().fallo(ip)
            error = "Usuario o contraseña incorrectos."
    return render_template("negocio/acceso.html", modo="entrar", error=error, errores={}), (401 if error else 200)


@negocio.post("/salir")
@requiere_usuario
def salir():
    session.clear()
    return redirect(url_for(".entrar"))


@negocio.route("/clave", methods=["GET", "POST"])
@requiere_usuario
def clave():
    errores = {}
    if request.method == "POST":
        errores = A.cambiar_clave(ctx().almacen, g.usuario, request.form.get("actual", ""),
                                  request.form.get("nueva", ""), request.form.get("repetida", ""))
        if not errores:
            flash("Listo, tu contraseña quedó cambiada.", "ok")
            return redirect(url_for(".semana"))
    return render_template("negocio/acceso.html", modo="clave", errores=errores, error=None)


# ------------------------------------------------------------------ agenda
@negocio.get("/")
@requiere_usuario
def inicio():
    return redirect(url_for(".semana"))


@negocio.get("/semana")
@requiere_usuario
def semana():
    dia = _fecha(request.args.get("d", ""), _hoy())
    dias = reglas.semana_de(dia)
    return render_template("negocio/agenda.html", vista="semana", dias=A.dias_con_agenda(ctx().almacen, g.empresa, dias, _zona()),
                           hoy=_hoy(), anterior=dias[0] - timedelta(days=7), siguiente=dias[0] + timedelta(days=7))


@negocio.get("/dia")
@requiere_usuario
def dia():
    d = _fecha(request.args.get("d", ""), _hoy())
    return render_template("negocio/agenda.html", vista="dia", dias=A.dias_con_agenda(ctx().almacen, g.empresa, [d], _zona()),
                           hoy=_hoy(), anterior=d - timedelta(days=1), siguiente=d + timedelta(days=1))


@negocio.get("/mes")
@requiere_usuario
def mes():
    hoy = _hoy()
    try:
        anio, m = (int(x) for x in request.args.get("m", "").split("-"))
        date(anio, m, 1)
    except ValueError:
        anio, m = hoy.year, hoy.month
    semanas = reglas.cuadricula_mes(anio, m)
    todos = [d for s in semanas for d in s]
    por_dia = {a["dia"]: a for a in A.dias_con_agenda(ctx().almacen, g.empresa, todos, _zona())}
    anterior = date(anio - (m == 1), (m - 2) % 12 + 1, 1)
    siguiente = date(anio + (m == 12), m % 12 + 1, 1)
    return render_template("negocio/mes.html", semanas=semanas, por_dia=por_dia, anio=anio, mes=m, hoy=hoy,
                           anterior=anterior, siguiente=siguiente)


# ------------------------------------------------------------------ citas
@negocio.route("/citas/nueva", methods=["GET", "POST"])
@requiere_usuario
def nueva_cita():
    c = ctx()
    errores, valores = {}, request.args
    if request.method == "POST":
        cita, errores = A.guardar_cita(c.almacen, g.empresa, request.form, c.ahora(), _zona())
        if not errores:
            flash(f"Cita guardada: {cita['paciente_nombre']}.", "ok")
            return redirect(url_for(".dia", d=reglas.dia_local(cita["inicio"], _zona()).isoformat()))
        valores = request.form
    paciente = None
    if valores.get("paciente_id", "").isdigit():
        paciente = c.almacen.paciente(g.empresa["id"], int(valores["paciente_id"]))
    return render_template("negocio/cita.html", cita=None, paciente=paciente, valores=valores, errores=errores,
                           sedes=A.sedes(g.empresa), hoy=_hoy())


@negocio.route("/citas/<int:cid>", methods=["GET", "POST"])
@requiere_usuario
def cita(cid):
    c = ctx()
    actual = _cita_o_404(cid)
    errores, valores = {}, None
    if request.method == "POST":
        cambiada, errores = A.guardar_cita(c.almacen, g.empresa, request.form, c.ahora(), _zona(), cita=actual)
        if not errores:
            flash("Cita actualizada.", "ok")
            return redirect(url_for(".cita", cid=cid))
        valores = request.form
    return render_template("negocio/cita.html", cita=actual, paciente=None, valores=valores, errores=errores,
                           sedes=A.sedes(g.empresa), hoy=_hoy())


@negocio.post("/citas/<int:cid>/estado")
@requiere_usuario
def estado_cita(cid):
    c = ctx()
    actual = _cita_o_404(cid)
    estado = request.form.get("estado", "")
    _, errores = A.cambiar_estado(c.almacen, g.empresa["id"], actual, estado, request.form, c.ahora())
    if errores:
        flash(" ".join(errores.values()), "error")
    else:
        flash(f"La cita quedó como «{reglas.ESTADOS_CITA[estado]}».", "ok")
    return redirect(url_for(".cita", cid=cid))


# ------------------------------------------------------------------ pacientes
@negocio.route("/pacientes", methods=["GET", "POST"])
@requiere_usuario
def pacientes():
    c = ctx()
    errores, valores = {}, None
    if request.method == "POST":
        paciente, errores = A.guardar_paciente(c.almacen, g.empresa["id"], request.form, c.ahora())
        if not errores:
            flash(f"Paciente agregado: {paciente['nombre']}.", "ok")
            return redirect(url_for(".paciente", pid=paciente["id"]))
        valores = request.form
    buscar = request.args.get("q", "")
    return render_template("negocio/pacientes.html", pacientes=c.almacen.pacientes(g.empresa["id"], buscar),
                           buscar=buscar, errores=errores, valores=valores)


@negocio.route("/pacientes/<int:pid>", methods=["GET", "POST"])
@requiere_usuario
def paciente(pid):
    c = ctx()
    actual = _paciente_o_404(pid)
    errores, valores = {}, None
    if request.method == "POST":
        actual_nuevo, errores = A.guardar_paciente(c.almacen, g.empresa["id"], request.form, c.ahora(), paciente_id=pid)
        if not errores:
            flash("Datos del paciente guardados.", "ok")
            return redirect(url_for(".paciente", pid=pid))
        valores = request.form
    citas = c.almacen.citas_de_paciente(g.empresa["id"], pid)
    return render_template("negocio/paciente.html", paciente=actual, citas=citas, resumen=A.resumen_paciente(citas),
                           errores=errores, valores=valores)


@negocio.post("/pacientes/<int:pid>/borrar")
@requiere_usuario
def borrar_paciente(pid):
    actual = _paciente_o_404(pid)
    ctx().almacen.borrar_paciente(g.empresa["id"], pid)
    flash(f"Se borró a {actual['nombre']} y sus citas.", "ok")
    return redirect(url_for(".pacientes"))


# ------------------------------------------------------------------ horario y bloqueos
@negocio.route("/horario", methods=["GET", "POST"])
@requiere_usuario
def horario():
    c = ctx()
    errores, propuesta = {}, None
    if request.method == "POST":
        propuesta, errores = A.leer_horario(request.form)
        if not errores:
            c.almacen.actualizar_empresa(g.empresa["id"], {"agenda": propuesta}, c.ahora())
            flash("Horario guardado. Los turnos libres de la agenda ya salen con este horario.", "ok")
            return redirect(url_for(".horario"))
    hoy = _hoy()
    return render_template("negocio/horario.html", agenda=propuesta or g.empresa.get("agenda") or {}, errores=errores,
                           bloqueos=c.almacen.bloqueos(g.empresa["id"], hoy, hoy + timedelta(days=730)), hoy=hoy)


@negocio.post("/horario/bloqueos")
@requiere_usuario
def nuevo_bloqueo():
    datos, errores = A.leer_bloqueo(request.form)
    if errores:
        flash(errores["bloqueo"], "error")
    else:
        ctx().almacen.crear_bloqueo(g.empresa["id"], datos["desde"], datos["hasta"], datos["motivo"])
        flash("Días bloqueados: la agenda ya no ofrece turnos libres en esas fechas.", "ok")
    return redirect(url_for(".horario") + "#bloqueos")


@negocio.post("/horario/bloqueos/<int:bid>/borrar")
@requiere_usuario
def borrar_bloqueo(bid):
    if not ctx().almacen.borrar_bloqueo(g.empresa["id"], bid):
        abort(404)
    flash("Bloqueo quitado.", "ok")
    return redirect(url_for(".horario") + "#bloqueos")
