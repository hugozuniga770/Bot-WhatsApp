"""Atencion de un mensaje, de principio a fin.

Lee y guarda con el almacen, decide con `reglas` y habla con WhatsApp y con
el asistente. No decide reglas por su cuenta: eso vive en reglas.py.
"""
import logging
import threading
from datetime import datetime

from . import reglas
from .reglas import MensajeEntrante, ocultar_numero

log = logging.getLogger(__name__)

RESPUESTA_NO_TEXTO = "Por ahora solo puedo leer mensajes de texto. ¿Me lo podría escribir, por favor? 🙏"
RESPUESTA_ERROR = "Disculpe, tuve un problema para responder. En un momento le contestamos."
AVISO_DUENA = "🔔 El cliente +{numero} necesita atención personal. El bot no le va a responder durante {horas:g} horas."

# Resultados posibles de atender(); sirven para los logs y para los tests.
DUPLICADO = "duplicado"
PAUSADO = "pausado"
NO_TEXTO = "no_texto"
RESPONDIDO = "respondido"
DERIVADO = "derivado"
ERROR = "error"
VACIO = "vacio"


class Servicios:
    def __init__(self, almacen, whatsapp, asistente, limite_historial=20, pausa_horas=12.0, duena_numero=""):
        self._almacen = almacen
        self._whatsapp = whatsapp
        self._asistente = asistente
        self._limite = limite_historial
        self._pausa_horas = pausa_horas
        self._duena = duena_numero
        self._locks: dict[str, threading.Lock] = {}
        self._guardia = threading.Lock()

    def _lock_de(self, numero: str) -> threading.Lock:
        with self._guardia:
            return self._locks.setdefault(numero, threading.Lock())

    def atender(self, msg: MensajeEntrante, ahora: datetime) -> str:
        if not self._almacen.es_nuevo(msg.id, ahora):
            return DUPLICADO

        with self._lock_de(msg.numero):
            if reglas.esta_pausado(self._almacen.pausado_hasta(msg.numero), ahora):
                return PAUSADO

            if msg.tipo != "text" or not msg.texto:
                self._whatsapp.enviar_texto(msg.numero, RESPUESTA_NO_TEXTO)
                return NO_TEXTO

            self._almacen.agregar(msg.numero, "user", msg.texto, ahora)
            historial = reglas.recortar_historial(self._almacen.historial(msg.numero), self._limite)

            try:
                respuesta = self._asistente.responder(historial)
            except Exception:
                log.exception("Fallo la llamada al asistente para %s", ocultar_numero(msg.numero))
                self._whatsapp.enviar_texto(msg.numero, RESPUESTA_ERROR)
                return ERROR

            texto, pide_humano = reglas.separar_marca(respuesta)
            if texto and self._whatsapp.enviar_texto(msg.numero, texto):
                self._almacen.agregar(msg.numero, "assistant", texto, ahora)

            if pide_humano:
                self._almacen.pausar(msg.numero, reglas.fin_de_pausa(ahora, self._pausa_horas))
                if self._duena:
                    self._whatsapp.enviar_texto(
                        self._duena, AVISO_DUENA.format(numero=msg.numero, horas=self._pausa_horas)
                    )
                return DERIVADO

            return RESPONDIDO if texto else VACIO
