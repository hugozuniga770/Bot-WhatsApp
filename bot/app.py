"""Arma la aplicacion: webhook de cada empresa, panel y enlaces de alta.

Las dependencias externas (almacen, Meta, Claude, verificaciones, reloj) se
pueden reemplazar al crear la app: asi los tests no tocan la red.
"""
import hmac
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
    conector: object = None  # v3.3: conexión guiada de Messenger e Instagram
    registro: object = None  # v3.4: coexistencia del número del WhatsApp Business


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


def _registrar_falla_segura(contexto: Contexto, empresa_id: int, falla):
    try:
        empresa = contexto.almacen.empresa(empresa_id)
        resultado = contexto.servicios.registrar_falla(empresa, falla, contexto.ahora())
        log.warning("[%s] Meta no pudo entregar un mensaje a %s (código %s): %s",
                    empresa["slug"], reglas.ocultar_numero(falla.numero), falla.codigo, resultado)
    except Exception:
        log.exception("Error inesperado registrando un mensaje no entregado de la empresa %s", empresa_id)


def _token_correcto(recibido: str | None, esperado: str | None) -> bool:
    """Compara sin filtrar por el tiempo de respuesta cuántas letras coinciden."""
    return bool(recibido and esperado) and hmac.compare_digest(recibido.encode(), esperado.encode())


@webhook.get("/webhook/<slug>")
def verificar(slug):
    # Meta manda el token en la dirección (?hub.verify_token=...), y Render anota las
    # direcciones en sus registros. Por eso el panel deja cambiarlo (D-24).
    c = ctx()
    empresa = c.almacen.empresa_por_slug(slug) or abort(404)
    if request.args.get("hub.mode") == "subscribe" and _token_correcto(request.args.get("hub.verify_token"),
                                                                      empresa.get("verify_token")):
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
    datos = request.get_json(silent=True)
    if isinstance(datos, dict) and datos.get("object") in reglas.OBJETOS_SOCIALES:
        # Para que la pantalla Canales muestre si llegan avisos de Messenger o Instagram
        c.almacen.marcar_actividad(empresa["id"], f"webhook_{reglas.OBJETOS_SOCIALES[datos['object']]}", c.ahora())
    # Solo los avisos de las cuentas de esta empresa: si la app de Meta tiene otro número,
    # otra página u otro Instagram, sus mensajes también llegan aquí (BOT-RF-12, C-20).
    from .canales import cuentas_de
    cuentas = cuentas_de(empresa)
    mensajes, fallas = reglas.extraer_mensajes(datos, cuentas), reglas.extraer_fallas(datos, cuentas)
    ajenos = len(reglas.extraer_mensajes(datos)) - len(mensajes) + len(reglas.extraer_fallas(datos)) - len(fallas)
    if ajenos:
        log.warning("[%s] %s aviso(s) de otra cuenta de Meta ignorado(s)", slug, ajenos)
    for msg in mensajes:
        c.ejecutar(_atender_seguro, c, empresa["id"], msg)
    for falla in fallas:
        c.ejecutar(_registrar_falla_segura, c, empresa["id"], falla)
    # v3.4, coexistencia: lo que la dueña escribe desde el celular, el historial, los contactos y los avisos
    for eco in reglas.extraer_ecos(datos, cuentas):
        c.ejecutar(_registrar_eco_seguro, c, empresa["id"], eco)
    for aviso in reglas.extraer_avisos_coexistencia(datos, cuentas):
        c.ejecutar(_registrar_aviso_seguro, c, empresa["id"], aviso)
    return "ok", 200


def _registrar_eco_seguro(contexto: Contexto, empresa_id: int, eco):
    try:
        empresa = contexto.almacen.empresa(empresa_id)
        resultado = contexto.servicios.registrar_eco(empresa, eco, contexto.ahora())
        log.info("[%s] respuesta a mano desde el celular a %s: %s", empresa["slug"], reglas.ocultar_numero(eco.cliente), resultado)
    except Exception:
        log.exception("Error inesperado registrando una respuesta a mano de la empresa %s", empresa_id)


def _registrar_aviso_seguro(contexto: Contexto, empresa_id: int, aviso: dict):
    try:
        empresa = contexto.almacen.empresa(empresa_id)
        contexto.servicios.registrar_aviso_coexistencia(empresa, aviso, contexto.ahora())
    except Exception:
        log.exception("Error inesperado registrando un aviso de coexistencia de la empresa %s", empresa_id)


@webhook.get("/salud")
def salud():
    return "ok", 200


@webhook.get("/pago/<slug>/qr")
def qr_de_pago(slug):
    """El QR de cobro del negocio. Es público a propósito: WhatsApp lo baja para mandárselo al paciente."""
    from flask import Response

    from . import reservas
    c = ctx()
    empresa = c.almacen.empresa_por_slug(slug) or abort(404)
    qr_id = reservas.cobro(empresa)["qr_id"]
    archivo = c.almacen.archivo(empresa["id"], int(qr_id)) if qr_id else None
    if not archivo or archivo["tipo"] != "qr":
        abort(404)
    respuesta = respuesta_de_archivo(archivo["datos"], f"qr-{slug}")
    respuesta.headers["Cache-Control"] = "public, max-age=300"
    return respuesta


def respuesta_de_archivo(datos: bytes, nombre: str):
    """Devuelve un archivo guardado (QR o comprobante) sin dejar que ejecute nada.

    El tipo sale de los bytes (reglas.tipo_de_archivo), nunca del dato guardado: si no es
    una foto o un PDF, 404. Las fotos se muestran con una política que prohíbe scripts
    (sandbox); los PDF se descargan.
    """
    from flask import Response
    tipo = reglas.tipo_de_archivo(datos)
    if not tipo:
        abort(404)
    respuesta = Response(datos, mimetype=tipo)
    forma = "attachment" if tipo == "application/pdf" else "inline"
    respuesta.headers["Content-Disposition"] = f'{forma}; filename="{nombre}.{reglas.EXTENSIONES[tipo]}"'
    respuesta.headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    return respuesta


def _canales_en_texto(empresa: dict) -> dict:
    """Para las páginas legales: 'WhatsApp', 'WhatsApp y Messenger', 'WhatsApp, Messenger e Instagram'."""
    from .canales import canales_conectados
    nombres = [reglas.NOMBRES_CANAL[c] for c in canales_conectados(empresa)]
    if len(nombres) == 1:
        texto = nombres[0]
    else:
        union = "e" if nombres[-1].lower().startswith(("i", "hi")) else "y"  # "e Instagram", no "y Instagram"
        texto = f"{', '.join(nombres[:-1])} {union} {nombres[-1]}"
    return {"canales": nombres, "canales_texto": texto, "con_redes": len(nombres) > 1}


@webhook.get("/privacidad/<slug>")
def privacidad(slug):
    """Política de privacidad de una empresa (Meta la pide para publicar la app y para la revisión
    de los permisos de Messenger e Instagram)."""
    from flask import render_template
    empresa = ctx().almacen.empresa_por_slug(slug) or abort(404)
    return render_template("privacidad.html", empresa=empresa, **_canales_en_texto(empresa))


@webhook.get("/eliminar-datos/<slug>")
def eliminar_datos(slug):
    """Instrucciones para borrar los datos (Meta las pide para publicar la app)."""
    from flask import render_template
    empresa = ctx().almacen.empresa_por_slug(slug) or abort(404)
    return render_template("eliminar_datos.html", empresa=empresa, **_canales_en_texto(empresa))


@webhook.get("/salud/base")
def salud_base():
    """Comprueba (y despierta) la base. El formulario la llama antes de guardar."""
    ctx().almacen.ping()
    return {"ok": True}, 200


@webhook.get("/")
def raiz():
    return redirect(url_for("panel.inicio"))


# ------------------------------------------------------------------ armado
def _vigilar_reservas(contexto, cada_segundos: int = 300):
    """Cada 5 minutos libera las reservas sin comprobante a tiempo (v3.1).

    Corre en un hilo del proceso. Si Render duerme el servicio, se retoma al despertar,
    y además cada mensaje que llega revisa las de su empresa.
    """
    import time

    from . import reservas

    while True:
        time.sleep(cada_segundos)
        try:
            for empresa in contexto.almacen.empresas():
                if empresa.get("estado") in ("activa", "revision") and reservas.activo(empresa):
                    contexto.servicios.vencer_reservas(empresa, contexto.ahora())
        except Exception:
            log.exception("Error al liberar reservas vencidas")


def crear_app(config=None, almacen=None, servicios=None, verificador=None, ejecutar=None, reloj=None, tareas=None,
              conector=None, registro=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config_venia_del_entorno = config is None
    if config is None:
        load_dotenv()
        config = cargar()

    from .almacen import crear_almacen
    from .asistente import Asistente
    from .canales import Conector, Mensajeria, Messenger, config_de
    from .coexistencia import Registro
    from .manual import componer
    from .servicios import Servicios
    from .verificaciones import Verificador
    from .whatsapp import WhatsApp
    from .empresas import secretos_de

    cifrador = Cifrador(config.clave_maestra)
    almacen = almacen or crear_almacen(config)
    if servicios is None:
        def fabrica_whatsapp(empresa):
            # v3.3: devuelve una Mensajeria que manda cada mensaje por su canal (WhatsApp,
            # Messenger o Instagram). Tiene los mismos métodos que WhatsApp.
            s = secretos_de(empresa, cifrador)
            whatsapp = WhatsApp(s["whatsapp_token"], empresa.get("phone_number_id", ""), config.graph_version)
            messenger = None
            pagina = config_de(empresa)["pagina_id"]
            if pagina and empresa.get("pagina_token_cif"):
                messenger = Messenger(pagina, cifrador.descifrar(empresa["pagina_token_cif"]), config.graph_version)
            return Mensajeria(whatsapp, messenger)

        def fabrica_asistente(empresa):
            s = secretos_de(empresa, cifrador)
            return Asistente(s["anthropic_key"], empresa.get("modelo") or reglas.MODELO_POR_DEFECTO,
                             componer(config.plantilla_manual, empresa))

        servicios = Servicios(almacen, fabrica_whatsapp, fabrica_asistente, config.zona_horaria, config.url_publica)

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
        conector=conector or Conector(config.graph_version),
        registro=registro or Registro(config.graph_version),
    )

    from .panel import panel
    from .alta import alta
    from .negocio import negocio
    from .formato import registrar_filtros

    app.register_blueprint(webhook)
    app.register_blueprint(panel)
    app.register_blueprint(alta)
    app.register_blueprint(negocio)
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
        if "Content-Security-Policy" not in respuesta.headers:  # los archivos traen una más estricta
            respuesta.headers["Content-Security-Policy"] = (
                "default-src 'self'; style-src 'self' https://fonts.googleapis.com; "
                "font-src https://fonts.gstatic.com; img-src 'self' data:; script-src 'self'; "
                "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
            )
        if request.path.startswith(("/panel", "/alta", "/negocio")):
            respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    if tareas if tareas is not None else (config_venia_del_entorno):
        threading.Thread(target=_vigilar_reservas, args=(app.extensions["bot"],), daemon=True).start()

    return app
