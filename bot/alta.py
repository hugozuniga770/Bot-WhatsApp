"""Enlace de alta (/alta/<token>): la persona del negocio carga sus datos y llaves.

El enlace es de un solo uso y vence en 7 dias (BOT-RF-15). Al enviarlo, la
empresa queda en revision: el bot solo le responde al dueño hasta que el
administrador la active desde el panel.
"""
from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from . import empresas as E
from . import reglas
from .app import ctx
from .manual import CAMPOS_NEGOCIO
from .panel import estado_del_webhook, probar_desde_formulario, url_base
from .seguridad import exigir_csrf

alta = Blueprint("alta", __name__, url_prefix="/alta")

OBLIGATORIOS = {
    "nombre": "Escribe el nombre del negocio.",
    "dueno_nombre": "Escribe el nombre de quien atiende el negocio.",
    "dueno_numero": "Escribe el número personal del dueño, con código de país.",
    "meta_app_id": "Falta el App ID de Meta.",
    "phone_number_id": "Falta el Phone number ID.",
}
SECRETOS_OBLIGATORIOS = {
    "anthropic_key": "Falta la llave de Claude.",
    "meta_app_secret": "Falta el App Secret.",
    "whatsapp_token": "Falta el token de WhatsApp.",
}


def _no_sirve(motivo: str):
    return render_template("aviso.html", titulo="Este enlace no sirve", texto=motivo), 404


@alta.route("/<token>", methods=["GET", "POST"])
def formulario(token):
    c = ctx()
    empresa, motivo = E.buscar_enlace(c.almacen, token, c.ahora())
    if not empresa:
        return _no_sirve(motivo)
    errores, valores = {}, None
    if request.method == "POST":
        exigir_csrf()
        cambios, secretos, errores = E.leer_formulario(request.form, es_admin=False)
        for campo, texto in OBLIGATORIOS.items():
            if not cambios.get(campo):
                errores.setdefault(campo, texto)
        for campo, texto in SECRETOS_OBLIGATORIOS.items():
            if campo not in secretos and not empresa.get(f"{campo}_cif"):
                errores.setdefault(campo, texto)
        if not errores:
            hoy = reglas.dia_local(c.ahora(), c.config.zona_horaria)
            empresa = E.guardar(c.almacen, c.cifrador, empresa, cambios, secretos, hoy, c.ahora())
            c.almacen.actualizar_empresa(empresa["id"], {"estado": "revision"}, c.ahora())
            c.almacen.usar_invitacion(E.hash_token(token), c.ahora())
            c.almacen.registrar_evento(empresa["id"], "alta", f"{cambios.get('dueno_nombre')} envió el formulario de alta.", c.ahora())
            return redirect(url_for(".gracias"))
        valores = request.form
    return render_template(
        "formulario.html", modo="alta", empresa=empresa, errores=errores, valores=valores,
        mascaras=E.mascaras(empresa, c.cifrador), campos_negocio=CAMPOS_NEGOCIO,
        webhook_url=f"{url_base()}/webhook/{empresa['slug']}",
        privacidad_url=f"{url_base()}/privacidad/{empresa['slug']}",
        eliminar_url=f"{url_base()}/eliminar-datos/{empresa['slug']}",
        url_accion=url_for(".formulario", token=token),
        url_probar=url_for(".probar", token=token, que="QUE"),
        url_webhook=url_for(".webhook", token=token),
    )


@alta.get("/gracias")
def gracias():
    return render_template(
        "aviso.html", titulo="¡Listo! Recibimos tus datos",
        texto="Ahora se revisa que todo esté bien. Mientras tanto, el bot ya te responde a ti: "
              "escríbele al número del negocio desde tu celular personal para probarlo. "
              "Te avisaremos cuando quede activo para todos tus clientes.",
    )


@alta.post("/<token>/probar/<que>")
def probar(token, que):
    c = ctx()
    exigir_csrf()
    empresa, motivo = E.buscar_enlace(c.almacen, token, c.ahora())
    if not empresa:
        return jsonify({"error": motivo}), 404
    return jsonify(probar_desde_formulario(empresa, que, request.get_json(silent=True) or {}))


@alta.get("/<token>/webhook")
def webhook(token):
    c = ctx()
    empresa, motivo = E.buscar_enlace(c.almacen, token, c.ahora())
    if not empresa:
        return jsonify({"error": motivo}), 404
    return jsonify(estado_del_webhook(empresa))
