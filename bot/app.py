"""Recepcion: las rutas web que llama Meta.

Solo recibe, comprueba la firma y le pasa cada mensaje a `servicios`.
Responde 200 a Meta al instante y atiende el mensaje en un hilo aparte,
para que Meta no reenvie el mensaje mientras Claude piensa.
"""
import logging
import threading
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, abort, request

from . import reglas
from .config import cargar


def _en_hilo(funcion, *args):
    threading.Thread(target=funcion, args=args, daemon=True).start()


def crear_app(config=None, servicios=None, ejecutar=None, reloj=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("bot")

    if config is None:
        load_dotenv()
        config = cargar()

    if servicios is None:
        from .almacen import crear_almacen
        from .asistente import Asistente
        from .servicios import Servicios
        from .whatsapp import WhatsApp

        servicios = Servicios(
            almacen=crear_almacen(config),
            whatsapp=WhatsApp(config.whatsapp_token, config.phone_number_id, config.graph_version),
            asistente=Asistente(config.modelo, config.instrucciones, config.max_tokens),
            limite_historial=config.limite_historial,
            pausa_horas=config.pausa_horas,
            duena_numero=config.duena_numero,
        )

    ejecutar = ejecutar or _en_hilo
    reloj = reloj or (lambda: datetime.now(timezone.utc))

    def atender_seguro(msg):
        try:
            resultado = servicios.atender(msg, reloj())
            log.info("Mensaje %s de %s: %s", msg.tipo, reglas.ocultar_numero(msg.numero), resultado)
        except Exception:
            log.exception("Error inesperado atendiendo a %s", reglas.ocultar_numero(msg.numero))

    app = Flask(__name__)

    @app.get("/")
    def salud():
        return "ok", 200

    @app.get("/webhook")
    def verificar():
        if (
            request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == config.verify_token
        ):
            log.info("Webhook verificado por Meta")
            return request.args.get("hub.challenge", ""), 200
        log.warning("Verificacion del webhook con token incorrecto")
        return "Token incorrecto", 403

    @app.post("/webhook")
    def recibir():
        cuerpo = request.get_data()
        if not reglas.firma_valida(cuerpo, request.headers.get("X-Hub-Signature-256"), config.app_secret):
            log.warning("Peticion con firma invalida; se ignora")
            abort(403)
        for msg in reglas.extraer_mensajes(request.get_json(silent=True)):
            ejecutar(atender_seguro, msg)
        return "ok", 200

    return app
