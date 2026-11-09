"""Atencion de un mensaje, de principio a fin, para una empresa.

Lee y guarda con el almacen, decide con `reglas` y habla con WhatsApp y con
el asistente de esa empresa. No decide reglas por su cuenta.
"""
import logging
import threading
from datetime import datetime

from . import reglas, reservas
from .reglas import FallaDeEntrega, MensajeEntrante, ocultar_numero

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
FALLA_REGISTRADA = "falla_registrada"
COMPROBANTE = "comprobante"
COMPROBANTE_FALLIDO = "comprobante_fallido"

# Mensajes automáticos a pacientes, según el trato que eligió el negocio (usted o tú)
RESPUESTA_COMPROBANTE = {
    "usted": "¡Gracias, {nombre}! Recibimos su comprobante. Lo revisamos y le confirmamos la cita del {dia} a las {hora} en {sede} por este chat.",
    "tu": "¡Gracias, {nombre}! Recibimos tu comprobante. Lo revisamos y te confirmamos la cita del {dia} a las {hora} en {sede} por este chat.",
}
RESPUESTA_COMPROBANTE_ERROR = {
    "usted": "No pude abrir el archivo 😕 ¿Me lo reenvía como foto, por favor?",
    "tu": "No pude abrir el archivo 😕 ¿Me lo reenvías como foto, por favor?",
}
RESPUESTA_COMPROBANTE_TIPO = {
    "usted": "Ese archivo no lo puedo recibir como comprobante. ¿Me manda una foto o captura del comprobante, o el PDF del banco, por favor?",
    "tu": "Ese archivo no lo puedo recibir como comprobante. ¿Me mandas una foto o captura del comprobante, o el PDF del banco, por favor?",
}
AVISO_COMPROBANTE = ("🧾 Comprobante por revisar: {nombre} ({telefono}) mandó el adelanto de Bs {monto:g} para la "
                     "valoración del {dia} a las {hora} en {sede}. Revísalo y apruébalo en el panel: {enlace}")
AVISO_VENCIDA = {
    "usted": "Se liberó su horario del {dia} a las {hora} en {sede}, porque no recibimos el comprobante a tiempo. Si quiere, escríbame y le busco otro turno.",
    "tu": "Se liberó tu horario del {dia} a las {hora} en {sede}, porque no recibimos el comprobante a tiempo. Si quieres, escríbeme y te busco otro turno.",
}


class Servicios:
    """`fabrica_whatsapp(empresa)` y `fabrica_asistente(empresa)` devuelven los clientes
    de esa empresa (con sus llaves ya descifradas). En los tests son dobles."""

    def __init__(self, almacen, fabrica_whatsapp, fabrica_asistente, zona_horaria="America/La_Paz", url_base=""):
        self._almacen = almacen
        self._url_base = (url_base or "").rstrip("/")
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

        if reservas.activo(empresa):
            self.vencer_reservas(empresa, ahora)

        with self._lock_de(eid, msg.numero):
            if reglas.esta_pausado(self._almacen.pausado_hasta(eid, msg.numero), ahora):
                return PAUSADO

            whatsapp = self._whatsapp(empresa)
            if msg.tipo in ("image", "document") and msg.media_id and reservas.activo(empresa):
                resultado = self._recibir_comprobante(empresa, msg, whatsapp, ahora)
                if resultado:
                    return resultado
            if msg.tipo != "text" or not msg.texto:
                whatsapp.enviar_texto(msg.numero, RESPUESTA_NO_TEXTO)
                return NO_TEXTO

            self._almacen.agregar(eid, msg.numero, "user", msg.texto, ahora)
            limite = int(empresa.get("historial_limite") or 20)
            historial = reglas.recortar_historial(self._almacen.historial(eid, msg.numero), limite)

            usa_agenda = reservas.activo(empresa)
            enviar_qr = []

            def ejecutar(nombre, entrada):
                r = reservas.ejecutar_herramienta(nombre, entrada, self._almacen, empresa, msg.numero, ahora, self._zona)
                if nombre == "reservar_turno" and r.get("ok") and r.get("se_envia_qr"):
                    enviar_qr.append(True)
                return r

            try:
                if usa_agenda:
                    respuesta = self._asistente(empresa).responder(
                        historial, extra_sistema=reservas.instrucciones(empresa, ahora, self._zona),
                        herramientas=reservas.HERRAMIENTAS, ejecutar=ejecutar)
                else:
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
            if enviar_qr and self._url_base:
                qr = reservas.cobro(empresa)["qr_id"]
                envio = whatsapp.enviar_imagen(msg.numero, f"{self._url_base}/pago/{empresa['slug']}/qr?v={qr}", "QR para pagar el adelanto")
                if not envio:
                    self._almacen.registrar_evento(eid, "error", f"No se pudo mandar el QR de cobro (código {envio.codigo}).", ahora)

            if pide_humano:
                horas = float(empresa.get("pausa_horas") or 12)
                self._almacen.pausar(eid, msg.numero, reglas.fin_de_pausa(ahora, horas))
                self._almacen.registrar_evento(eid, "derivado", f"Chat ...{msg.numero[-4:]} pasado a {empresa.get('dueno_nombre') or 'la dueña'}.", ahora)
                dueno = empresa.get("dueno_numero")
                if dueno and dueno != msg.numero:
                    whatsapp.enviar_texto(dueno, AVISO_DUENO.format(numero=msg.numero, horas=horas))
                return DERIVADO

            return RESPONDIDO if texto else VACIO

    def _recibir_comprobante(self, empresa: dict, msg: MensajeEntrante, whatsapp, ahora: datetime):
        """Una foto o PDF de alguien con una reserva por pagar: se guarda y pasa a 'por revisar'."""
        eid = empresa["id"]
        cita = reservas.reserva_activa(self._almacen, eid, msg.numero, ahora)
        if not cita or cita["estado"] not in ("pendiente_pago", "por_revisar"):
            return None  # no hay nada que pagar: se responde como siempre
        ok, datos = whatsapp.descargar_media(msg.media_id)
        if not ok:
            self._almacen.registrar_evento(eid, "error", f"No se pudo bajar un comprobante de ...{msg.numero[-4:]}: {datos[1]}", ahora)
            whatsapp.enviar_texto(msg.numero, RESPUESTA_COMPROBANTE_ERROR[reglas.trato(empresa)])
            return COMPROBANTE_FALLIDO
        contenido, _ = datos
        tipo = reglas.tipo_de_archivo(contenido)  # el tipo real, no el que declara el archivo
        if not tipo:
            self._almacen.registrar_evento(eid, "error", f"Se rechazó un archivo de ...{msg.numero[-4:]}: no es una foto ni un PDF.", ahora)
            whatsapp.enviar_texto(msg.numero, RESPUESTA_COMPROBANTE_TIPO[reglas.trato(empresa)])
            return COMPROBANTE_FALLIDO
        archivo_id = self._almacen.guardar_archivo(eid, "comprobante", tipo, contenido, ahora)
        cita = self._almacen.actualizar_cita(eid, cita["id"], {"estado": "por_revisar", "comprobante_id": archivo_id}, ahora)
        r = reservas.resumen(cita, self._zona)
        primer_nombre = (cita["paciente_nombre"] or "").split(" ")[0] or "gracias"
        texto = RESPUESTA_COMPROBANTE[reglas.trato(empresa)].format(nombre=primer_nombre, dia=r["dia"], hora=r["hora"], sede=r["sede"])
        self._almacen.agregar(eid, msg.numero, "user", "[Mandó la foto del comprobante de pago]", ahora)
        if whatsapp.enviar_texto(msg.numero, texto):
            self._almacen.agregar(eid, msg.numero, "assistant", texto, ahora)
        self._almacen.registrar_evento(eid, "comprobante", f"Comprobante de {cita['paciente_nombre']} por revisar ({r['dia']} {r['hora']}).", ahora)
        aviso = reglas.normalizar_numero(reservas.cobro(empresa)["aviso_numero"])
        if aviso and aviso != msg.numero:
            envio = whatsapp.enviar_texto(aviso, AVISO_COMPROBANTE.format(
                nombre=cita["paciente_nombre"], telefono=f"+{msg.numero}", monto=cita.get("adelanto_pedido") or 0,
                dia=r["dia"], hora=r["hora"], sede=r["sede"], enlace=f"{self._url_base}/negocio/citas/{cita['id']}"))
            if not envio:
                self._almacen.registrar_evento(eid, "error", f"No se pudo avisar a la asistente del comprobante (código {envio.codigo}).", ahora)
        return COMPROBANTE

    def avisar(self, empresa: dict, numero: str, texto: str, ahora: datetime):
        """Mensaje del negocio a un paciente (confirmación o rechazo de un pago). Devuelve el Envio."""
        envio = self._whatsapp(empresa).enviar_texto(numero, texto)
        if envio:
            self._almacen.agregar(empresa["id"], numero, "assistant", texto, ahora)
        return envio

    def vencer_reservas(self, empresa: dict, ahora: datetime) -> int:
        """Libera las reservas sin comprobante a tiempo y le avisa a cada paciente."""
        liberadas = reservas.vencer(self._almacen, empresa, ahora)
        if liberadas:
            whatsapp = self._whatsapp(empresa)
            for c in liberadas:
                r = reservas.resumen(c, self._zona)
                whatsapp.enviar_texto(c["paciente_telefono"], AVISO_VENCIDA[reglas.trato(empresa)].format(dia=r["dia"], hora=r["hora"], sede=r["sede"]))
        return len(liberadas)

    def registrar_falla(self, empresa: dict, falla: FallaDeEntrega, ahora: datetime) -> str:
        """Meta avisó que no pudo entregar un mensaje del bot: queda en la Actividad con el motivo.

        Se registra en cualquier estado de la empresa (también en prueba), porque explica
        por qué un mensaje de prueba o un aviso al dueño no llegó.
        """
        eid = empresa["id"]
        if not self._almacen.es_nuevo(eid, f"falla:{falla.id}", ahora):
            return DUPLICADO
        self._almacen.registrar_evento(eid, "error", reglas.texto_de_falla(falla), ahora)
        return FALLA_REGISTRADA
