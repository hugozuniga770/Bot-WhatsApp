"""Atencion de mensajes (bot/servicios.py). Requisitos BOT-RF-01 a 06."""
from datetime import timedelta

from bot import servicios as s
from conftest import CLIENTE, DUENA


def test_RF01_responde_un_texto_con_el_asistente_y_guarda_ambos_mensajes(servicios, almacen, whatsapp, mensaje, ahora):
    # Dado un cliente que escribe por primera vez
    # Cuando el bot atiende su mensaje
    resultado = servicios.atender(mensaje("¿Cuánto cuesta?"), ahora)
    # Entonces le envía la respuesta del asistente y guarda las dos partes de la conversación
    assert resultado == s.RESPONDIDO
    assert whatsapp.enviados == [(CLIENTE, "Hola, ¿en qué le puedo ayudar?")]
    assert almacen.historial(CLIENTE) == [
        {"role": "user", "content": "¿Cuánto cuesta?"},
        {"role": "assistant", "content": "Hola, ¿en qué le puedo ayudar?"},
    ]


def test_RF02_el_asistente_recibe_la_conversacion_anterior(servicios, asistente, mensaje, ahora):
    # Dado un cliente que ya escribió una vez
    servicios.atender(mensaje("Hola"), ahora)
    # Cuando escribe otra vez
    servicios.atender(mensaje("¿Y el precio?"), ahora)
    # Entonces el asistente recibe toda la conversación, en orden
    assert [m["content"] for m in asistente.historiales[-1]] == [
        "Hola", "Hola, ¿en qué le puedo ayudar?", "¿Y el precio?",
    ]


def test_RF03_audio_recibe_aviso_de_solo_texto_sin_llamar_al_asistente(servicios, asistente, whatsapp, mensaje, ahora):
    # Dado un cliente que manda un audio
    # Cuando el bot lo atiende
    resultado = servicios.atender(mensaje(tipo="audio"), ahora)
    # Entonces le pide que escriba, y no gasta una llamada a Claude
    assert resultado == s.NO_TEXTO
    assert whatsapp.enviados == [(CLIENTE, s.RESPUESTA_NO_TEXTO)]
    assert asistente.historiales == []


def test_RF04_la_marca_deriva_a_la_duena_pausa_el_chat_y_no_se_envia_la_marca(servicios, almacen, asistente, whatsapp, mensaje, ahora):
    # Dado que el asistente decide pasarle el chat a la dueña
    asistente.respuestas = ["Le paso con la dueña, enseguida le escribe. [PASAR_A_HUMANO]"]
    # Cuando el bot atiende el mensaje
    resultado = servicios.atender(mensaje("Quiero comprar"), ahora)
    # Entonces el cliente recibe el texto sin la marca, el chat queda en pausa 12 h y la dueña recibe el aviso
    assert resultado == s.DERIVADO
    assert whatsapp.enviados[0] == (CLIENTE, "Le paso con la dueña, enseguida le escribe.")
    assert almacen.pausado_hasta(CLIENTE) == ahora + timedelta(hours=12)
    assert whatsapp.enviados[1][0] == DUENA and CLIENTE in whatsapp.enviados[1][1]


def test_RF04_chat_en_pausa_no_recibe_respuesta(servicios, almacen, asistente, whatsapp, mensaje, ahora):
    # Dado un chat en pausa hasta dentro de una hora
    almacen.pausar(CLIENTE, ahora + timedelta(hours=1))
    # Cuando el cliente escribe
    resultado = servicios.atender(mensaje("¿Sigue ahí?"), ahora)
    # Entonces el bot no responde ni llama al asistente: la conversación es de la dueña
    assert resultado == s.PAUSADO
    assert whatsapp.enviados == [] and asistente.historiales == []


def test_RF04_al_vencer_la_pausa_el_bot_vuelve_a_responder(servicios, almacen, whatsapp, mensaje, ahora):
    # Dado un chat cuya pausa venció hace un minuto
    almacen.pausar(CLIENTE, ahora - timedelta(minutes=1))
    # Cuando el cliente escribe
    resultado = servicios.atender(mensaje("Hola de nuevo"), ahora)
    # Entonces el bot vuelve a responder
    assert resultado == s.RESPONDIDO
    assert len(whatsapp.enviados) == 1


def test_RF05_mensaje_repetido_se_atiende_una_sola_vez(servicios, whatsapp, mensaje, ahora):
    # Dado que Meta reenvía el mismo mensaje (mismo id)
    repetido = mensaje("Hola", id="wamid.repetido")
    # Cuando llega dos veces
    primero = servicios.atender(repetido, ahora)
    segundo = servicios.atender(repetido, ahora)
    # Entonces se responde una sola vez
    assert (primero, segundo) == (s.RESPONDIDO, s.DUPLICADO)
    assert len(whatsapp.enviados) == 1


def test_RF06_si_falla_el_asistente_el_cliente_recibe_una_disculpa(servicios, asistente, whatsapp, mensaje, ahora):
    # Dado que la API de Claude falla (sin créditos, caída, etc.)
    asistente.error = RuntimeError("API caída")
    # Cuando el bot atiende un mensaje
    resultado = servicios.atender(mensaje("Hola"), ahora)
    # Entonces el cliente recibe la disculpa en vez de quedar sin respuesta
    assert resultado == s.ERROR
    assert whatsapp.enviados == [(CLIENTE, s.RESPUESTA_ERROR)]
