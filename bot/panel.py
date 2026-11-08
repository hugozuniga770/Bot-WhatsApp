"""Panel del administrador (/panel): empresas, salud, creditos y acciones."""
from datetime import datetime

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from . import empresas as E
from . import reglas, tablero
from .app import ctx
from .manual import CAMPOS_NEGOCIO, componer
from .seguridad import Limitador, exigir_csrf, ip_cliente, password_correcta, requiere_admin, token_csrf

panel = Blueprint("panel", __name__, url_prefix="/panel")


def limitador() -> Limitador:
    # Uno por aplicacion (no global), para que cada app y cada test tenga el suyo.
    return current_app.extensions.setdefault("limitador", Limitador())

MENSAJE_PRUEBA = "✅ Prueba de {nombre}: el bot de WhatsApp está conectado y puede enviar mensajes."
EXPLICACION_ENVIO = {
    131047: "WhatsApp solo deja escribirle a un número que le escribió al negocio en las últimas 24 horas. Desde ese celular, mándale un mensaje al número del negocio y vuelve a probar.",
    131030: "Ese número no está en la lista de destinatarios de prueba de Meta. Agrégalo en Meta → WhatsApp → Configuración de la API.",
    190: "El token de Meta no es válido o venció. Cárgalo de nuevo en Editar.",
}


def url_base() -> str:
    return ctx().config.url_publica or request.url_root.rstrip("/")


def _empresa_o_404(eid: int) -> dict:
    empresa = ctx().almacen.empresa(eid)
    if not empresa:
        from flask import abort
        abort(404)
    return empresa


# ------------------------------------------------------------------ sesion
@panel.route("/entrar", methods=["GET", "POST"])
def entrar():
    error = None
    if request.method == "POST":
        exigir_csrf()
        ip = ip_cliente()
        if limitador().bloqueado(ip):
            error = "Demasiados intentos. Espera 15 minutos y vuelve a probar."
        elif password_correcta(request.form.get("password", ""), ctx().config.admin_password):
            limitador().limpiar(ip)
            session.clear()
            session["admin"] = True
            session.permanent = True
            token_csrf()
            siguiente = request.args.get("siguiente", "")
            return redirect(siguiente if siguiente.startswith("/panel") else url_for(".inicio"))
        else:
            limitador().fallo(ip)
            error = "Contraseña incorrecta."
    return render_template("entrar.html", error=error), (401 if error else 200)


@panel.post("/salir")
@requiere_admin
def salir():
    session.clear()
    return redirect(url_for(".entrar"))


# ------------------------------------------------------------------ inicio y empresas
@panel.get("/")
@requiere_admin
def inicio():
    c = ctx()
    resumenes = [tablero.resumen(e, c.almacen, c.ahora(), c.config.zona_horaria) for e in c.almacen.empresas()]
    return render_template("panel.html", resumenes=resumenes)


@panel.post("/empresas")
@requiere_admin
def nueva():
    c = ctx()
    nombre = request.form.get("nombre", "").strip()
    if not nombre:
        flash("Escribe el nombre de la empresa.", "error")
        return redirect(url_for(".inicio"))
    empresa = E.crear_empresa(c.almacen, nombre, c.ahora())
    token = E.crear_enlace(c.almacen, empresa["id"], c.ahora())
    c.almacen.registrar_evento(empresa["id"], "creada", "Empresa creada y enlace de alta generado.", c.ahora())
    session["enlace_nuevo"] = {"empresa_id": empresa["id"], "url": f"{url_base()}/alta/{token}"}
    return redirect(url_for(".detalle", eid=empresa["id"]))


@panel.get("/empresas/<int:eid>")
@requiere_admin
def detalle(eid):
    c = ctx()
    empresa = _empresa_o_404(eid)
    enlace = session.get("enlace_nuevo")
    if enlace and enlace.get("empresa_id") == eid:
        session.pop("enlace_nuevo")
    else:
        enlace = None
    return render_template(
        "empresa.html",
        r=tablero.resumen(empresa, c.almacen, c.ahora(), c.config.zona_horaria),
        eventos=c.almacen.eventos(eid, 15),
        mascaras=E.mascaras(empresa, c.cifrador),
        enlace=enlace,
        webhook_url=f"{url_base()}/webhook/{empresa['slug']}",
        privacidad_url=f"{url_base()}/privacidad/{empresa['slug']}",
        eliminar_url=f"{url_base()}/eliminar-datos/{empresa['slug']}",
        manual=componer(c.config.plantilla_manual, empresa),
    )


@panel.post("/empresas/<int:eid>/enlace")
@requiere_admin
def nuevo_enlace(eid):
    c = ctx()
    _empresa_o_404(eid)
    token = E.crear_enlace(c.almacen, eid, c.ahora())
    c.almacen.registrar_evento(eid, "enlace", "Nuevo enlace de alta generado.", c.ahora())
    session["enlace_nuevo"] = {"empresa_id": eid, "url": f"{url_base()}/alta/{token}"}
    return redirect(url_for(".detalle", eid=eid) + "#enlace")


@panel.post("/empresas/<int:eid>/verificar")
@requiere_admin
def verificar(eid):
    c = ctx()
    empresa = _empresa_o_404(eid)
    chequeos = verificar_empresa(empresa)
    c.almacen.actualizar_empresa(eid, {"ultima_verificacion": {
        "fecha": c.ahora().isoformat(), "chequeos": [ch.a_dict() for ch in chequeos]}}, c.ahora())
    malos = [ch for ch in chequeos if ch.estado in ("falla", "atencion")]
    c.almacen.registrar_evento(eid, "verificacion", "Verificación: todo bien." if not malos
                               else f"Verificación: {len(malos)} cosa(s) por revisar.", c.ahora())
    flash("Todo funciona." if not malos else f"Hay {len(malos)} cosa(s) por revisar.", "ok" if not malos else "error")
    return redirect(url_for(".detalle", eid=eid))


def verificar_empresa(empresa: dict, nuevos: dict | None = None) -> list:
    """Prueba las llaves guardadas, o las `nuevas` que se estan escribiendo en el formulario."""
    c = ctx()
    s = E.secretos_de(empresa, c.cifrador)
    s.update({k: v for k, v in (nuevos or {}).items() if v})
    datos = {**empresa, **{k: v for k, v in (nuevos or {}).items() if v}}
    return [c.verificador.claude(s["anthropic_key"], datos.get("modelo") or reglas.MODELO_POR_DEFECTO),
            *c.verificador.meta(s["whatsapp_token"], datos.get("phone_number_id", ""),
                                datos.get("meta_app_id", ""), s["meta_app_secret"], c.ahora())]


@panel.post("/empresas/<int:eid>/prueba")
@requiere_admin
def prueba(eid):
    c = ctx()
    empresa = _empresa_o_404(eid)
    if not empresa.get("dueno_numero"):
        flash("Falta el número del dueño para mandarle la prueba.", "error")
        return redirect(url_for(".detalle", eid=eid))
    s = E.secretos_de(empresa, c.cifrador)
    envio = c.verificador.enviar_prueba(s["whatsapp_token"], empresa.get("phone_number_id", ""),
                                        empresa["dueno_numero"], MENSAJE_PRUEBA.format(nombre=empresa["nombre"]))
    if envio.ok:
        # Que Meta lo acepte no garantiza que llegue: si no lo entrega, avisa después por el
        # webhook y el motivo queda en la Actividad (por ejemplo, la regla de las 24 horas).
        c.almacen.registrar_evento(eid, "prueba", "Meta aceptó el mensaje de prueba para el dueño.", c.ahora())
        flash("Meta aceptó el mensaje de prueba. Si en un minuto no llega al WhatsApp del dueño, "
              "recarga esta página: en Actividad aparece el motivo.", "ok")
    else:
        explicacion = EXPLICACION_ENVIO.get(envio.codigo, f"Meta respondió: {envio.detalle or envio.codigo}")
        c.almacen.registrar_evento(eid, "error", f"No se pudo enviar la prueba (código {envio.codigo}).", c.ahora())
        flash(explicacion, "error")
    return redirect(url_for(".detalle", eid=eid))


@panel.post("/empresas/<int:eid>/estado")
@requiere_admin
def cambiar_estado(eid):
    c = ctx()
    empresa = _empresa_o_404(eid)
    nuevo = request.form.get("estado", "")
    textos = {"activa": "Bot activado: ya responde a todos los clientes.",
              "pausada": "Bot pausado: no responde a nadie.",
              "revision": "Bot en prueba: solo le responde al dueño."}
    if nuevo not in textos:
        flash("Estado desconocido.", "error")
        return redirect(url_for(".detalle", eid=eid))
    if nuevo == "activa":
        chequeos = (empresa.get("ultima_verificacion") or {}).get("chequeos", [])
        fallas = [ch for ch in chequeos if ch["estado"] == "falla"]
        if not chequeos or fallas:
            flash("Antes de activar, verifica la empresa y resuelve lo que falle.", "error")
            return redirect(url_for(".detalle", eid=eid))
    c.almacen.actualizar_empresa(eid, {"estado": nuevo}, c.ahora())
    c.almacen.registrar_evento(eid, "estado", textos[nuevo], c.ahora())
    flash(textos[nuevo], "ok")
    return redirect(url_for(".detalle", eid=eid))


@panel.post("/empresas/<int:eid>/token-verificacion")
@requiere_admin
def cambiar_token_verificacion(eid):
    """Cambia el token de verificación del webhook (D-24). No corta nada: Meta sigue
    mandando los mensajes, porque esos se firman con el App Secret y no con este token."""
    c = ctx()
    _empresa_o_404(eid)
    c.almacen.actualizar_empresa(eid, {"verify_token": E.nuevo_token_verificacion()}, c.ahora())
    c.almacen.registrar_evento(eid, "webhook", "Token de verificación cambiado.", c.ahora())
    flash("Token cambiado. El bot sigue recibiendo mensajes igual. Si algún día vuelves a tocar "
          "«Verificar y guardar» en Meta, pega antes este token nuevo.", "ok")
    return redirect(url_for(".detalle", eid=eid) + "#conexion")


@panel.post("/empresas/<int:eid>/saldo")
@requiere_admin
def saldo(eid):
    c = ctx()
    _empresa_o_404(eid)
    errores = reglas.errores_de_formato({"saldo_usd": request.form.get("saldo_usd", "").strip()})
    valor = request.form.get("saldo_usd", "").strip()
    if errores or not valor:
        flash(errores.get("saldo_usd", "Escribe el saldo."), "error")
    else:
        hoy = reglas.dia_local(c.ahora(), c.config.zona_horaria)
        c.almacen.actualizar_empresa(eid, {"saldo_usd": float(valor), "saldo_desde": hoy.isoformat()}, c.ahora())
        c.almacen.registrar_evento(eid, "saldo", f"Saldo actualizado a USD {float(valor):.2f}.", c.ahora())
        flash("Saldo actualizado. La estimación cuenta desde hoy.", "ok")
    return redirect(url_for(".detalle", eid=eid) + "#creditos")


@panel.post("/empresas/<int:eid>/borrar-cliente")
@requiere_admin
def borrar_cliente(eid):
    c = ctx()
    _empresa_o_404(eid)
    numero = reglas.normalizar_numero(request.form.get("numero", ""))
    if not 8 <= len(numero) <= 15:
        flash("Escribe el número del cliente con código de país, por ejemplo 591 70000000.", "error")
    else:
        n = c.almacen.borrar_cliente(eid, numero)
        c.almacen.registrar_evento(eid, "borrado", f"Datos del cliente ...{numero[-4:]} borrados ({n} mensajes).", c.ahora())
        flash(f"Listo: se borraron {n} mensajes y la pausa de ese número." if n else "Ese número no tenía mensajes guardados.", "ok")
    return redirect(url_for(".detalle", eid=eid) + "#datos")


@panel.route("/empresas/<int:eid>/editar", methods=["GET", "POST"])
@requiere_admin
def editar(eid):
    c = ctx()
    empresa = _empresa_o_404(eid)
    errores, valores = {}, None
    if request.method == "POST":
        cambios, secretos, errores = E.leer_formulario(request.form, es_admin=True)
        if not errores:
            hoy = reglas.dia_local(c.ahora(), c.config.zona_horaria)
            E.guardar(c.almacen, c.cifrador, empresa, cambios, secretos, hoy, c.ahora())
            c.almacen.registrar_evento(eid, "editada", "Datos de la empresa actualizados.", c.ahora())
            flash("Cambios guardados.", "ok")
            return redirect(url_for(".detalle", eid=eid))
        valores = request.form
    return render_template(
        "formulario.html", modo="admin", empresa=empresa, errores=errores, valores=valores,
        mascaras=E.mascaras(empresa, c.cifrador), campos_negocio=CAMPOS_NEGOCIO,
        webhook_url=f"{url_base()}/webhook/{empresa['slug']}",
        url_accion=url_for(".editar", eid=eid),
        url_probar=url_for(".probar", eid=eid, que="QUE"),
        url_webhook=url_for(".estado_webhook", eid=eid),
    )


@panel.post("/empresas/<int:eid>/probar/<que>")
@requiere_admin
def probar(eid, que):
    return jsonify(probar_desde_formulario(_empresa_o_404(eid), que, request.get_json(silent=True) or {}))


@panel.get("/empresas/<int:eid>/webhook")
@requiere_admin
def estado_webhook(eid):
    return jsonify(estado_del_webhook(_empresa_o_404(eid)))


def probar_desde_formulario(empresa: dict, que: str, datos: dict) -> list[dict]:
    """Prueba en vivo lo que se esta escribiendo (no se guarda nada)."""
    c = ctx()
    nuevos = {k: "".join(str(datos.get(k, "")).split()) for k in
              ("anthropic_key", "whatsapp_token", "meta_app_secret", "meta_app_id", "phone_number_id")}
    s = E.secretos_de(empresa, c.cifrador)
    s.update({k: v for k, v in nuevos.items() if v and k in E.SECRETOS})
    if que == "claude":
        return [c.verificador.claude(s["anthropic_key"], empresa.get("modelo") or reglas.MODELO_POR_DEFECTO).a_dict()]
    if que == "meta":
        return [ch.a_dict() for ch in c.verificador.meta(
            s["whatsapp_token"], nuevos["phone_number_id"] or empresa.get("phone_number_id", ""),
            nuevos["meta_app_id"] or empresa.get("meta_app_id", ""), s["meta_app_secret"], c.ahora())]
    return []


def estado_del_webhook(empresa: dict) -> dict:
    c = ctx()
    ultimo = c.almacen.actividad(empresa["id"]).get("webhook")
    return {"conectado": ultimo is not None,
            "detalle": f"Meta se conectó {reglas.hace(ultimo, c.ahora())}." if ultimo else "Esperando a Meta…"}
