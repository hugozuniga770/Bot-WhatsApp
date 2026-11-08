"""Arma la aplicacion: webhook de cada empresa, panel y enlaces de alta.

Las dependencias externas (almacen, Meta, Claude, verificaciones, reloj) se
pueden reemplazar al crear la app: asi los tests no tocan la red.
"""
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from flask import Blueprint, Flask, abort, current_app, redirect, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from . import reglas
from .almacen import BaseDeDatosNoDisponible
from .cifrado import Cifrador, ClaveIncorrecta
from .config import cargar

log = logging.getLogger("bot")


def _en_hilo(funcion, *args):
    threading.Thread(target=funcion, args=args, daemon=True).start()


@dataclass
class Contexto:
    config: object
    almacen: object
    cifrador: Cifrador
    servicios: object
    verificador: object
    ejecutar: object
    reloj: object

    def ahora(self) -> datetime:
        return self.reloj()


def ctx() -> Contexto:
    return current_app.extensions["bot"]


# ------------------------------------------------------------------ webhook por empresa
webhook = Blueprint("webhook", __name__)


def _atender_seguro(contexto: Contexto, empresa_id: int, msg):
    try:
        empresa = contexto.almacen.empresa(empresa_id)  # siempre la version mas nueva
        resultado = contexto.servicios.atender(empresa, msg, contexto.ahora())
        log.info("[%s] mensaje %s de %s: %s", empresa["slug"], msg.tipo, reglas.ocultar_numero(msg.numero), resultado)
    except Exception:
        log.exception("Error inesperado atendiendo un mensaje de la empresa %s", empresa_id)


@webhook.get("/webhook/<slug>")
def verificar(slug):
    c = ctx()
    empresa = c.almacen.empresa_por_slug(slug) or abort(404)
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == empresa.get("verify_token"):
        c.almacen.marcar_actividad(empresa["id"], "webhook", c.ahora())
        c.almacen.registrar_evento(empresa["id"], "webhook", "Meta verificó el webhook.", c.ahora())
        return request.args.get("hub.challenge", ""), 200
    log.warning("[%s] verificacion del webhook con token incorrecto", slug)
    return "Token incorrecto", 403


@webhook.post("/webhook/<slug>")
def recibir(slug):
    c = ctx()
    empresa = c.almacen.empresa_por_slug(slug) or abort(404)
    try:
        secreto = c.cifrador.descifrar(empresa.get("meta_app_secret_cif", ""))
    except ClaveIncorrecta:
        log.error("[%s] no se puede leer el App Secret (CLAVE_MAESTRA distinta)", slug)
        abort(403)
    if not reglas.firma_valida(request.get_data(), request.headers.get("X-Hub-Signature-256"), secreto):
        log.warning("[%s] peticion con firma invalida; se ignora", slug)
        abort(403)
    c.almacen.marcar_actividad(empresa["id"], "webhook", c.ahora())
    for msg in reglas.extraer_mensajes(request.get_json(silent=True)):
        c.ejecutar(_atender_seguro, c, empresa["id"], msg)
    return "ok", 200


@webhook.get("/salud")
def salud():
    return "ok", 200


@webhook.get("/salud/base")
def salud_base():
    """Comprueba (y despierta) la base. El formulario la llama antes de guardar."""
    ctx().almacen.ping()
    return {"ok": True}, 200


@webhook.get("/")
def raiz():
    return redirect(url_for("panel.inicio"))


# ------------------------------------------------------------------ armado
def crear_app(config=None, almacen=None, servicios=None, verificador=None, ejecutar=None, reloj=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if config is None:
        load_dotenv()
        config = cargar()

    from .almacen import crear_almacen
    from .asistente import Asistente
    from .manual import componer
    from .servicios import Servicios
    from .verificaciones import Verificador
    from .whatsapp import WhatsApp
    from .empresas import secretos_de

    cifrador = Cifrador(config.clave_maestra)
    almacen = almacen or crear_almacen(config)
    if servicios is None:
        def fabrica_whatsapp(empresa):
            s = secretos_de(empresa, cifrador)
            return WhatsApp(s["whatsapp_token"], empresa.get("phone_number_id", ""), config.graph_version)

        def fabrica_asistente(empresa):
            s = secretos_de(empresa, cifrador)
            return Asistente(s["anthropic_key"], empresa.get("modelo") or reglas.MODELO_POR_DEFECTO,
                             componer(config.plantilla_manual, empresa))

        servicios = Servicios(almacen, fabrica_whatsapp, fabrica_asistente, config.zona_horaria)

    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config.update(
        SECRET_KEY=config.secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.cookie_segura,
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    app.extensions["bot"] = Contexto(
        config=config, almacen=almacen, cifrador=cifrador, servicios=servicios,
        verificador=verificador or Verificador(config.graph_version),
        ejecutar=ejecutar or _en_hilo,
        reloj=reloj or (lambda: datetime.now(timezone.utc)),
    )

    from .panel import panel
    from .alta import alta
    from .formato import registrar_filtros

    app.register_blueprint(webhook)
    app.register_blueprint(panel)
    app.register_blueprint(alta)
    registrar_filtros(app)

    @app.errorhandler(BaseDeDatosNoDisponible)
    def base_no_disponible(error):
        # 503 (y no 500): Meta reintenta los avisos más tarde, y en el panel se explica qué pasó.
        log.error("Base de datos no disponible en %s %s", request.method, request.path)
        if request.path.startswith(("/webhook", "/salud")) or request.is_json or "/probar/" in request.path or request.path.endswith("/webhook"):
            return {"error": "La base de datos no respondió. Vuelve a intentar en un minuto."}, 503
        from flask import render_template
        return render_template("aviso.html", titulo="La base de datos no respondió",
                               texto="Puede pasar si estuvo un rato sin uso y está despertando. Espera un minuto y vuelve a cargar la página. Lo que escribiste en el formulario se guarda en este navegador (sin las llaves)."), 503

    @app.after_request
    def cabeceras(respuesta):
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["X-Frame-Options"] = "DENY"
        respuesta.headers["Referrer-Policy"] = "no-referrer"
        respuesta.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; img-src 'self' data:; script-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        if request.path.startswith(("/panel", "/alta")):
            respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    return app
