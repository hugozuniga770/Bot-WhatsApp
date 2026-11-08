"""Atencion de un mensaje, de principio a fin, para una empresa.

Lee y guarda con el almacen, decide con `reglas` y habla con WhatsApp y con
el asistente de esa empresa. No decide reglas por su cuenta.
"""
import logging
import threading
from datetime import datetime

from . import reglas
from .reglas import MensajeEntrante, ocultar_numero

log = logging.getLogger(__name__)

RESPUESTA_NO_TEXTO = "Por ahora solo puedo leer mensajes de texto. ¿Me lo podría escribir, por favor? 🙏"
RESPUESTA_ERROR = "Disculpe, tuve un problema para responder. En un momento le contestamos."
AVISO_DUENO = "🔔 El cliente +{numero} necesita atención personal. El bot no le va a responder durante {horas:g} horas."

# Resultados posibles de atender(); sirven para los logs y para los tests.
DUPLICADO = "duplicado"
INACTIVA = "inactiva"
IGNORADO = "ignorado"
EN_REVISION = "en_revision"
PAUSADO = "pausado"
NO_TEXTO = "no_texto"
RESPONDIDO = "respondido"
DERIVADO = "derivado"
ERROR = "error"
VACIO = "vacio"


class Servicios:
    """`fabrica_whatsapp(empresa)` y `fabrica_asistente(empresa)` devuelven los clientes
    de esa empresa (con sus llaves ya descifradas). En los tests son dobles."""

    def __init__(self, almacen, fabrica_whatsapp, fabrica_asistente, zona_horaria="America/La_Paz"):
        self._almacen = almacen
        self._whatsapp = fabrica_whatsapp
        self._asistente = fabrica_asistente
        self._zona = zona_horaria
        self._locks: dict[tuple, threading.Lock] = {}
        self._guardia = threading.Lock()

    def _lock_de(self, empresa_id: int, numero: str) -> threading.Lock:
        with self._guardia:
            return self._locks.setdefault((empresa_id, numero), threading.Lock())

    def atender(self, empresa: dict, msg: MensajeEntrante, ahora: datetime) -> str:
        eid = empresa["id"]
        if empresa.get("estado") not in ("activa", "revision"):
            return INACTIVA
        if not self._almacen.es_nuevo(eid, msg.id, ahora):
            return DUPLICADO
        self._almacen.marcar_actividad(eid, "mensaje", ahora)
        if msg.numero in reglas.lista_de_numeros(empresa.get("numeros_ignorados", "")):
            return IGNORADO
        # En revision el bot ya funciona, pero solo le responde al dueño (para probar).
        if empresa["estado"] == "revision" and msg.numero != empresa.get("dueno_numero"):
            return EN_REVISION

        with self._lock_de(eid, msg.numero):
            if reglas.esta_pausado(self._almacen.pausado_hasta(eid, msg.numero), ahora):
                return PAUSADO

            whatsapp = self._whatsapp(empresa)
            if msg.tipo != "text" or not msg.texto:
                whatsapp.enviar_texto(msg.numero, RESPUESTA_NO_TEXTO)
                return NO_TEXTO

            self._almacen.agregar(eid, msg.numero, "user", msg.texto, ahora)
            limite = int(empresa.get("historial_limite") or 20)
            historial = reglas.recortar_historial(self._almacen.historial(eid, msg.numero), limite)

            try:
                respuesta = self._asistente(empresa).responder(historial)
            except Exception as e:
                log.exception("Fallo el asistente de %s para %s", empresa.get("slug"), ocultar_numero(msg.numero))
                self._almacen.registrar_evento(eid, "error", f"Claude no respondió: {e.__class__.__name__}", ahora)
                whatsapp.enviar_texto(msg.numero, RESPUESTA_ERROR)
                return ERROR

            self._almacen.sumar_uso(eid, reglas.dia_local(ahora, self._zona), respuesta.entrada, respuesta.salida)
            texto, pide_humano = reglas.separar_marca(respuesta.texto)
            if texto:
                envio = whatsapp.enviar_texto(msg.numero, texto)
                if envio:
                    self._almacen.agregar(eid, msg.numero, "assistant", texto, ahora)
                    self._almacen.marcar_actividad(eid, "respuesta", ahora)
                else:
                    self._almacen.registrar_evento(eid, "error", f"Meta no aceptó la respuesta (código {envio.codigo}).", ahora)

            if pide_humano:
                horas = float(empresa.get("pausa_horas") or 12)
                self._almacen.pausar(eid, msg.numero, reglas.fin_de_pausa(ahora, horas))
                self._almacen.registrar_evento(eid, "derivado", f"Chat ...{msg.numero[-4:]} pasado a {empresa.get('dueno_nombre') or 'la dueña'}.", ahora)
                dueno = empresa.get("dueno_numero")
                if dueno and dueno != msg.numero:
                    whatsapp.enviar_texto(dueno, AVISO_DUENO.format(numero=msg.numero, horas=horas))
                return DERIVADO

            return RESPONDIDO if texto else VACIO

