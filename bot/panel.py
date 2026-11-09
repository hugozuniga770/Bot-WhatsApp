"""Panel del administrador (/panel): empresas, salud, creditos y acciones."""
from datetime import datetime

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from . import agenda as A
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
    return _detalle(eid)


def _detalle(eid: int, acceso_nuevo: dict | None = None):
    """El detalle de una empresa. `acceso_nuevo` lleva una contraseña temporal recién creada:
    se muestra en esta respuesta y en ninguna otra (no pasa por la sesión ni por una redirección)."""
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
        usuarios=c.almacen.usuarios_de(eid),
        roles=reglas.ROLES,
        agenda_url=f"{url_base()}/negocio/entrar",
        acceso_nuevo=acceso_nuevo,
    )


def _usuario_de(eid: int, uid: int) -> dict:
    usuario = ctx().almacen.usuario(uid)
    if not usuario or usuario["empresa_id"] != eid:
        from flask import abort
        abort(404)
    return usuario


@panel.post("/empresas/<int:eid>/usuarios")
@requiere_admin
def nuevo_usuario(eid):
    c = ctx()
    _empresa_o_404(eid)
    usuario, clave, errores = A.crear_usuario(c.almacen, eid, request.form.get("nombre", ""), request.form.get("usuario", ""),
                                              request.form.get("rol", ""), c.ahora())
    if errores:
        flash(" ".join(errores.values()), "error")
        return redirect(url_for(".detalle", eid=eid) + "#accesos")
    c.almacen.registrar_evento(eid, "acceso", f"Acceso a la agenda creado para {usuario['nombre']} ({reglas.ROLES[usuario['rol']]}).", c.ahora())
    return _detalle(eid, acceso_nuevo={"usuario": usuario, "clave": clave})


@panel.post("/empresas/<int:eid>/usuarios/<int:uid>/clave")
@requiere_admin
def nueva_clave_usuario(eid, uid):
    c = ctx()
    usuario = _usuario_de(eid, uid)
    clave = A.restablecer_clave(c.almacen, uid)
    c.almacen.registrar_evento(eid, "acceso", f"Contraseña temporal nueva para {usuario['nombre']}.", c.ahora())
    return _detalle(eid, acceso_nuevo={"usuario": usuario, "clave": clave})


@panel.post("/empresas/<int:eid>/usuarios/<int:uid>/activo")
@requiere_admin
def activar_usuario(eid, uid):
    c = ctx()
    usuario = _usuario_de(eid, uid)
    activo = not usuario["activo"]
    c.almacen.actualizar_usuario(uid, {"activo": activo})
    texto = f"Acceso de {usuario['nombre']} {'activado' if activo else 'desactivado: ya no puede entrar'}."
    c.almacen.registrar_evento(eid, "acceso", texto, c.ahora())
    flash(texto, "ok")
    return redirect(url_for(".detalle", eid=eid) + "#accesos")


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
                                datos.get("meta_app_id", ""), s["meta_app_secret"], c.ahora()),
            *(chequeo_canales(empresa) if nuevos is None else [])]


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
    crudo = "".join(request.form.get("numero", "").split()).lower()
    # Un chat de Messenger o Instagram se guarda como fb:<PSID> o ig:<IGSID> (D-36): también se borra (C-20)
    numero = crudo if ID_SOCIAL.fullmatch(crudo) else reglas.normalizar_numero(crudo)
    if not (ID_SOCIAL.fullmatch(numero) or 8 <= len(numero) <= 15):
        flash("Escribe el número del cliente con código de país, por ejemplo 591 70000000, o su cuenta de Messenger o Instagram (fb:… o ig:…).", "error")
    else:
        n = c.almacen.borrar_cliente(eid, numero)
        c.almacen.registrar_evento(eid, "borrado", f"Datos del cliente ...{numero[-4:]} borrados ({n} mensajes).", c.ahora())
        flash(f"Listo: se borraron {n} mensajes y la pausa de ese cliente." if n else "Ese cliente no tenía mensajes guardados.", "ok")
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
        privacidad_url=f"{url_base()}/privacidad/{empresa['slug']}",
        eliminar_url=f"{url_base()}/eliminar-datos/{empresa['slug']}",
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


# ------------------------------------------------------------------ canales (v3.3)
# Messenger e Instagram se conectan desde una sola pantalla: se elige qué conectar, el bot
# busca solo la página, su cuenta de Instagram y los tokens, y dice qué falta en Meta.
import re as _re

from . import canales as K

CANALES_SOCIALES = ("messenger", "instagram")
ID_SOCIAL = _re.compile(r"(fb|ig):\d{5,40}")


def _token_para_canales(empresa: dict) -> str:
    """El token guardado para buscar páginas; si no hay, el de WhatsApp (suele ser el mismo usuario del sistema)."""
    c = ctx()
    return c.cifrador.descifrar(empresa.get("canal_token_cif", "")) or E.secretos_de(empresa, c.cifrador)["whatsapp_token"]


def _vista_canales(empresa: dict, busqueda: dict | None = None):
    c = ctx()
    actividad = c.almacen.actividad(empresa["id"])
    return render_template(
        "canales.html", e=empresa, k=K.config_de(empresa), busqueda=busqueda,
        whatsapp_listo=bool(empresa.get("phone_number_id") and empresa.get("whatsapp_token_cif")),
        token_guardado=reglas.enmascarar(_token_para_canales(empresa)),
        ultimo={canal: actividad.get(f"webhook_{canal}") for canal in CANALES_SOCIALES},
        ahora=c.ahora(), permisos=K.PERMISOS, nombres=reglas.NOMBRES_CANAL,
        webhook_url=f"{url_base()}/webhook/{empresa['slug']}",
    )


@panel.get("/empresas/<int:eid>/canales")
@requiere_admin
def canales(eid):
    return _vista_canales(_empresa_o_404(eid))


@panel.post("/empresas/<int:eid>/canales/buscar")
@requiere_admin
def canales_buscar(eid):
    """Paso 1: revisar el token y traer las páginas (con su Instagram) a las que llega."""
    c = ctx()
    empresa = _empresa_o_404(eid)
    nuevo = "".join(request.form.get("token", "").split())
    if nuevo and len(nuevo) < 50:
        flash("El token es un texto largo, sin espacios (suele empezar con EAA). Revisa que lo copiaste completo.", "error")
        return redirect(url_for(".canales", eid=eid))
    token = nuevo or _token_para_canales(empresa)
    if not token:
        flash("Pega un token de Meta con los permisos de páginas, o carga primero el de WhatsApp en Editar.", "error")
        return redirect(url_for(".canales", eid=eid))
    secretos = E.secretos_de(empresa, c.cifrador)
    ok, revision = c.conector.revisar_token(token, empresa.get("meta_app_id", ""), secretos["meta_app_secret"])
    if not ok:
        flash(revision, "error")
        return redirect(url_for(".canales", eid=eid))
    ok, paginas = c.conector.paginas(token)
    if not ok:
        flash(paginas, "error")
        return redirect(url_for(".canales", eid=eid))
    if nuevo:
        empresa = c.almacen.actualizar_empresa(eid, {"canal_token_cif": c.cifrador.cifrar(nuevo)}, c.ahora())
    # Los tokens de las páginas no van a la pantalla: se vuelven a pedir al conectar.
    sin_tokens = [{k: v for k, v in p.items() if k != "token"} for p in paginas]
    return _vista_canales(empresa, busqueda={**revision, "paginas": sin_tokens})


@panel.post("/empresas/<int:eid>/canales/conectar")
@requiere_admin
def canales_conectar(eid):
    """Paso 2: con la página elegida, suscribirla a la app, registrar el webhook y guardar."""
    c = ctx()
    empresa = _empresa_o_404(eid)
    elegidos = [canal for canal in CANALES_SOCIALES if request.form.get(canal)]
    pagina_id = request.form.get("pagina_id", "").strip()
    if not pagina_id or not elegidos:
        flash("Elige una página y al menos un canal (Messenger o Instagram).", "error")
        return redirect(url_for(".canales", eid=eid))
    token = _token_para_canales(empresa)
    secretos = E.secretos_de(empresa, c.cifrador)
    app_id, app_secret = empresa.get("meta_app_id", ""), secretos["meta_app_secret"]
    ok, paginas = c.conector.paginas(token)
    pagina = next((p for p in paginas if p["id"] == pagina_id), None) if ok else None
    if not pagina or not pagina.get("token"):
        flash(paginas if not ok else "Esa página ya no aparece con este token. Vuelve a buscar.", "error")
        return redirect(url_for(".canales", eid=eid))

    pasos = []

    def paso(clave, titulo, ok_, detalle):
        pasos.append({"clave": clave, "titulo": titulo, "estado": "ok" if ok_ else "falla", "detalle": detalle})

    ok_rev, revision = c.conector.revisar_token(token, app_id, app_secret)
    if ok_rev:
        faltan = sorted({p for canal in elegidos for p in revision["faltan"][canal]})
        if faltan:
            pasos.append({"clave": "permisos", "titulo": "Permisos del token", "estado": "atencion",
                          "detalle": "Al token le faltan: " + ", ".join(faltan) + ". Genera uno nuevo del usuario del sistema con esos permisos y vuelve a buscar."})
        else:
            paso("permisos", "Permisos del token", True, "El token tiene todos los permisos para lo que elegiste.")
    paso("pagina", f"Página «{pagina['nombre']}»", *c.conector.suscribir_pagina(pagina["id"], pagina["token"]))
    callback = f"{url_base()}/webhook/{empresa['slug']}"
    if "messenger" in elegidos:
        paso("webhook_messenger", "Webhook de Messenger",
             *c.conector.suscribir_app(app_id, app_secret, "page", K.CAMPOS_PAGINA, callback, empresa.get("verify_token", "")))
    if "instagram" in elegidos:
        if not pagina["ig_id"]:
            paso("webhook_instagram", "Instagram", False, "Esta página no tiene una cuenta profesional de Instagram unida. Únela en Meta Business Suite → Configuración → Cuentas de Instagram, y vuelve a buscar.")
        else:
            paso("webhook_instagram", f"Webhook de Instagram (@{pagina['ig_usuario']})",
                 *c.conector.suscribir_app(app_id, app_secret, "instagram", K.CAMPOS_INSTAGRAM, callback, empresa.get("verify_token", "")))

    config = K.config_de(empresa)
    config.update(pagina_id=pagina["id"], pagina_nombre=pagina["nombre"], ig_id=pagina["ig_id"], ig_usuario=pagina["ig_usuario"],
                  messenger="messenger" in elegidos, instagram="instagram" in elegidos and bool(pagina["ig_id"]),
                  pasos=pasos, conectado=c.ahora().isoformat())
    c.almacen.actualizar_empresa(eid, {"canales": config, "pagina_token_cif": c.cifrador.cifrar(pagina["token"])}, c.ahora())
    malos = [p for p in pasos if p["estado"] != "ok"]
    nombres = " e ".join(reglas.NOMBRES_CANAL[canal] for canal in elegidos)
    c.almacen.registrar_evento(eid, "canales", f"Página «{pagina['nombre']}» conectada para {nombres}"
                               + (f" ({len(malos)} cosa(s) por revisar)." if malos else "."), c.ahora())
    flash(f"Listo: {nombres} conectado." if not malos else f"Se guardó la página, pero hay {len(malos)} cosa(s) por revisar abajo.",
          "ok" if not malos else "error")
    return redirect(url_for(".canales", eid=eid))


@panel.post("/empresas/<int:eid>/canales/interruptor")
@requiere_admin
def canales_interruptor(eid):
    c = ctx()
    empresa = _empresa_o_404(eid)
    canal = request.form.get("canal", "")
    if canal not in CANALES_SOCIALES:
        flash("Canal desconocido.", "error")
        return redirect(url_for(".canales", eid=eid))
    config = K.config_de(empresa)
    if not config["pagina_id"] or (canal == "instagram" and not config["ig_id"]):
        flash(f"Primero conecta {reglas.NOMBRES_CANAL[canal]}.", "error")
        return redirect(url_for(".canales", eid=eid))
    config[canal] = request.form.get("activo") == "1"
    c.almacen.actualizar_empresa(eid, {"canales": config}, c.ahora())
    texto = f"{reglas.NOMBRES_CANAL[canal]} {'encendido' if config[canal] else 'apagado'}: el bot {'responde' if config[canal] else 'ya no responde'} ahí."
    c.almacen.registrar_evento(eid, "canales", texto, c.ahora())
    flash(texto, "ok")
    return redirect(url_for(".canales", eid=eid))


@panel.post("/empresas/<int:eid>/canales/probador")
@requiere_admin
def canales_probador(eid):
    """En prueba, en Messenger e Instagram el bot solo responde a las cuentas marcadas aquí."""
    c = ctx()
    empresa = _empresa_o_404(eid)
    destino = request.form.get("id", "").strip()
    if not ID_SOCIAL.fullmatch(destino):
        flash("Esa cuenta no es válida.", "error")
        return redirect(url_for(".canales", eid=eid))
    config = K.config_de(empresa)
    if request.form.get("accion") == "quitar":
        config["probadores"] = [x for x in config["probadores"] if x != destino]
        texto = f"La cuenta ...{destino[-4:]} ya no es de prueba."
    else:
        if destino not in config["probadores"]:
            config["probadores"] = config["probadores"] + [destino]
        config["candidatos"] = [x for x in config["candidatos"] if x.get("id") != destino]
        texto = f"La cuenta ...{destino[-4:]} queda para probar: el bot le responde aunque esté en prueba."
    c.almacen.actualizar_empresa(eid, {"canales": config}, c.ahora())
    c.almacen.registrar_evento(eid, "canales", texto, c.ahora())
    flash(texto, "ok")
    return redirect(url_for(".canales", eid=eid))


def chequeo_canales(empresa: dict) -> list:
    """Para Verificar todo: si hay una página conectada, que siga suscrita y su token sirva."""
    from .verificaciones import Chequeo
    c = ctx()
    config = K.config_de(empresa)
    if not config["pagina_id"] or not (config["messenger"] or config["instagram"]):
        return []
    token = c.cifrador.descifrar(empresa.get("pagina_token_cif", ""))
    ok, detalle = c.conector.pagina_suscrita(config["pagina_id"], token, empresa.get("meta_app_id", ""))
    return [Chequeo("canales", f"Messenger e Instagram ({config['pagina_nombre'] or 'página'})", "ok" if ok else "atencion", detalle)]


# ------------------------------------------------------------------ coexistencia (v3.4)
# El bot responde en el número del WhatsApp Business del negocio sin sacarlo de la app del
# celular. La conexión la hace Meta (Embedded Signup) desde esta pantalla; el panel cambia el
# código por el token del negocio, suscribe la app y pide las dos sincronizaciones (D-41 a D-44).
from . import coexistencia as X

NUMERO_ID = _re.compile(r"\d{6,25}")
# La pantalla de coexistencia carga el SDK de Meta: solo ella permite connect.facebook.net y facebook.com.
CSP_COEXISTENCIA = (
    "default-src 'self'; script-src 'self' https://connect.facebook.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
    "img-src 'self' data: https://*.facebook.com https://*.fbcdn.net; "
    "frame-src https://*.facebook.com; connect-src 'self' https://*.facebook.com https://*.facebook.net; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
)


def _vista_coexistencia(empresa: dict, resultado: dict | None = None):
    c = ctx()
    config = X.config_de(empresa)
    pendientes = [t for t in X.SINCRONIZACIONES if not (config["sincronizacion"].get(t) or {}).get("request_id")]
    puede, motivo = X.puede_sincronizar(config, pendientes[0], c.ahora()) if pendientes else (False, "")
    respuesta = current_app.make_response(render_template(
        "coexistencia.html", e=empresa, x=config, resultado=resultado,
        app_id=empresa.get("meta_app_id", ""), version=c.config.graph_version,
        pendientes=pendientes, puede_sincronizar=puede, motivo_sincronizar=motivo,
        nombres_sync=X.NOMBRES_SINCRONIZACION, prueba=(config.get("prueba") or {}),
        dominio=url_base(), ultimo=c.almacen.actividad(empresa["id"]),
    ))
    respuesta.headers["Content-Security-Policy"] = CSP_COEXISTENCIA
    return respuesta


@panel.get("/empresas/<int:eid>/coexistencia")
@requiere_admin
def coexistencia(eid):
    return _vista_coexistencia(_empresa_o_404(eid))


@panel.post("/empresas/<int:eid>/coexistencia/configuracion")
@requiere_admin
def coexistencia_configuracion(eid):
    """Guarda el ID de la configuración de «Inicio de sesión con Facebook para empresas»."""
    c = ctx()
    empresa = _empresa_o_404(eid)
    config_id = "".join(request.form.get("config_id", "").split())
    if not NUMERO_ID.fullmatch(config_id):
        flash("El ID de la configuración son solo números (lo da Meta al crear la configuración).", "error")
    else:
        config = X.config_de(empresa)
        config["config_id"] = config_id
        c.almacen.actualizar_empresa(eid, {"coexistencia": config}, c.ahora())
        c.almacen.registrar_evento(eid, "coexistencia", "Coexistencia: ID de la configuración de Meta guardado.", c.ahora())
        flash("Listo: ya se puede conectar el WhatsApp Business.", "ok")
    return redirect(url_for(".coexistencia", eid=eid))


def _sincronizar(empresa: dict, config: dict, token: str, pasos: list) -> dict:
    """Asegura los campos del webhook y pide las sincronizaciones que falten, en orden."""
    c = ctx()
    secretos = E.secretos_de(empresa, c.cifrador)
    callback = f"{url_base()}/webhook/{empresa['slug']}"
    ok, detalle = c.conector.suscribir_app(empresa.get("meta_app_id", ""), secretos["meta_app_secret"], "whatsapp_business_account",
                                           X.CAMPOS_WABA, callback, empresa.get("verify_token", ""))
    pasos.append({"clave": "campos", "titulo": "Avisos del celular, historial y contactos", "estado": "ok" if ok else "falla",
                  "detalle": "El webhook recibe lo que se escribe desde el celular, el historial y los contactos." if ok else detalle})
    if not ok:
        return config
    for tipo in X.SINCRONIZACIONES:
        if (config["sincronizacion"].get(tipo) or {}).get("request_id"):
            continue
        puede, motivo = X.puede_sincronizar(config, tipo, c.ahora())
        titulo = f"Sincronizar {X.NOMBRES_SINCRONIZACION[tipo]}"
        if not puede:
            pasos.append({"clave": tipo, "titulo": titulo, "estado": "falla", "detalle": motivo})
            break
        ok, dato = c.registro.sincronizar(config["phone_number_id"], token, tipo)
        if ok:
            config["sincronizacion"] = {**config["sincronizacion"], tipo: {"request_id": dato, "fecha": c.ahora().isoformat()}}
            pasos.append({"clave": tipo, "titulo": titulo, "estado": "ok", "detalle": "Pedida. Meta la manda por partes en los próximos minutos."})
        else:
            pasos.append({"clave": tipo, "titulo": titulo, "estado": "falla", "detalle": dato})
            break
    return config


@panel.post("/empresas/<int:eid>/coexistencia/finalizar")
@requiere_admin
def coexistencia_finalizar(eid):
    """Lo llama la pantalla cuando Meta termina el registro (código + id de la cuenta de WhatsApp)."""
    c = ctx()
    empresa = _empresa_o_404(eid)
    datos = request.get_json(silent=True) or {}
    codigo = str(datos.get("code") or "").strip()
    waba_id = str(datos.get("waba_id") or "").strip()
    pedido_numero = str(datos.get("phone_number_id") or "").strip()
    # v3.4.1: el id de la cuenta de WhatsApp es opcional. Si Meta no mandó su mensaje (pasó el
    # 09/11/2026), se busca con el token: debug_token dice a qué cuentas da acceso (C-22).
    if not codigo or len(codigo) > 2000 or (waba_id and not NUMERO_ID.fullmatch(waba_id)) \
            or (pedido_numero and not NUMERO_ID.fullmatch(pedido_numero)):
        return jsonify({"ok": False, "mensaje": "Meta no devolvió los datos del registro. Vuelve a intentarlo."}), 400
    eventos = [str(e)[:60] for e in (datos.get("eventos") or [])[:10] if isinstance(e, str)]

    pasos = []

    def fallo(clave, titulo, detalle):
        pasos.append({"clave": clave, "titulo": titulo, "estado": "falla", "detalle": detalle})
        meta_dijo = f" Meta avisó: {', '.join(eventos)}." if eventos else " Meta no mandó avisos del registro."
        c.almacen.registrar_evento(eid, "error", f"Coexistencia: no se pudo conectar ({titulo.lower()}: {detalle}).{meta_dijo} "
                                   "No se cambió nada.", c.ahora())
        return jsonify({"ok": False, "mensaje": f"No se pudo conectar: {detalle} No se cambió nada en el bot.", "pasos": pasos})

    secretos = E.secretos_de(empresa, c.cifrador)
    app_id = empresa.get("meta_app_id", "")
    ok, token = c.registro.canjear_codigo(app_id, secretos["meta_app_secret"], codigo)
    if not ok:
        return fallo("codigo", "Código del registro", token)
    pasos.append({"clave": "codigo", "titulo": "Código del registro", "estado": "ok", "detalle": "Meta dio el token del negocio."})

    if not waba_id:
        ok, wabas = c.registro.wabas_del_token(app_id, secretos["meta_app_secret"], token)
        if not ok or not wabas:
            return fallo("waba", "Cuenta de WhatsApp", wabas if not ok else
                         "El registro no dio acceso a ninguna cuenta de WhatsApp. ¿Se terminó el paso del QR?")
        if len(wabas) > 1:
            con_app = []
            for candidata in wabas:
                ok_n, nums = c.registro.numeros_de(candidata, token)
                if ok_n and any(n.get("is_on_biz_app") for n in nums):
                    con_app.append(candidata)
            if len(con_app) != 1:
                return fallo("waba", "Cuenta de WhatsApp", "El registro dio acceso a varias cuentas de WhatsApp y no se sabe cuál es la del celular.")
            wabas = con_app
        waba_id = wabas[0]

    ok, numeros = c.registro.numeros_de(waba_id, token)
    numero = X.elegir_numero(numeros, pedido_numero) if ok else None
    if not numero:
        return fallo("numero", "Número de WhatsApp", numeros if not ok else "No se encontró el número en la cuenta de WhatsApp.")
    ok, info = c.registro.numero(str(numero["id"]), token)
    if not ok:
        return fallo("numero", "Número de WhatsApp", info)
    if not info.get("is_on_biz_app"):
        # Si el número no está en la app del celular, esto no es coexistencia: no se toca nada.
        return fallo("numero", "Número de WhatsApp", "Ese número no está en la app WhatsApp Business del celular.")
    pasos.append({"clave": "numero", "titulo": "Número de WhatsApp", "estado": "ok",
                  "detalle": f"{info.get('display_phone_number') or numero.get('display_phone_number', '')} "
                             f"({info.get('verified_name') or numero.get('verified_name', '')}), sigue en la app del celular."})

    ok, detalle = c.registro.suscribir_waba(waba_id, token)
    if not ok:
        return fallo("waba", "Cuenta de WhatsApp", detalle)
    pasos.append({"clave": "waba", "titulo": "Cuenta de WhatsApp", "estado": "ok", "detalle": detalle})

    # Desde aquí el bot usa el número del negocio. El de prueba queda guardado para volver.
    config = X.config_de(empresa)
    prueba = config.get("prueba") or {}
    if empresa.get("phone_number_id") and str(empresa.get("phone_number_id")) != str(numero["id"]) and not prueba:
        prueba = {"phone_number_id": empresa.get("phone_number_id", ""), "whatsapp_token_cif": empresa.get("whatsapp_token_cif", "")}
    config.update(estado="conectada", waba_id=waba_id, phone_number_id=str(numero["id"]),
                  numero=info.get("display_phone_number") or numero.get("display_phone_number", ""),
                  nombre=info.get("verified_name") or numero.get("verified_name", ""),
                  conectada=c.ahora().isoformat(), sincronizacion={}, prueba=prueba)
    empresa = c.almacen.actualizar_empresa(eid, {"phone_number_id": str(numero["id"]), "whatsapp_token_cif": c.cifrador.cifrar(token),
                                                 "coexistencia": config}, c.ahora())
    config = _sincronizar(empresa, config, token, pasos)
    config["pasos"] = pasos
    c.almacen.actualizar_empresa(eid, {"coexistencia": config}, c.ahora())
    malos = [p for p in pasos if p["estado"] != "ok"]
    c.almacen.registrar_evento(eid, "coexistencia", f"Coexistencia: el bot quedó conectado al número {config['numero']}"
                               + (f" ({len(malos)} cosa(s) por revisar)." if malos else "."), c.ahora())
    return jsonify({"ok": True, "mensaje": "Listo: el bot quedó conectado al WhatsApp Business." if not malos else
                    "El bot quedó conectado, pero hay cosas por revisar abajo.", "pasos": pasos})


@panel.post("/empresas/<int:eid>/coexistencia/sincronizar")
@requiere_admin
def coexistencia_sincronizar(eid):
    c = ctx()
    empresa = _empresa_o_404(eid)
    config = X.config_de(empresa)
    pasos = []
    config = _sincronizar(empresa, config, E.secretos_de(empresa, c.cifrador)["whatsapp_token"], pasos)
    config["pasos"] = (config.get("pasos") or []) + pasos
    c.almacen.actualizar_empresa(eid, {"coexistencia": config}, c.ahora())
    malos = [p for p in pasos if p["estado"] != "ok"]
    flash("Sincronización pedida." if not malos else malos[0]["detalle"], "ok" if not malos else "error")
    return redirect(url_for(".coexistencia", eid=eid))


@panel.post("/empresas/<int:eid>/coexistencia/volver")
@requiere_admin
def coexistencia_volver(eid):
    """El bot vuelve a usar el número de prueba. No desconecta nada en Meta ni en el celular."""
    c = ctx()
    empresa = _empresa_o_404(eid)
    config = X.config_de(empresa)
    prueba = config.get("prueba") or {}
    if not prueba.get("phone_number_id"):
        flash("No hay un número de prueba guardado.", "error")
        return redirect(url_for(".coexistencia", eid=eid))
    config["estado"] = "sin_conectar"
    c.almacen.actualizar_empresa(eid, {"phone_number_id": prueba["phone_number_id"], "whatsapp_token_cif": prueba["whatsapp_token_cif"],
                                       "coexistencia": config}, c.ahora())
    texto = (f"El bot volvió al número de prueba ({prueba['phone_number_id']}). El WhatsApp Business del celular sigue igual; "
             "para cortar la coexistencia del todo, se desconecta desde la app del celular.")
    c.almacen.registrar_evento(eid, "coexistencia", texto, c.ahora())
    flash(texto, "ok")
    return redirect(url_for(".coexistencia", eid=eid))
