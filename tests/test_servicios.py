"""Atencion de mensajes (bot/servicios.py)."""
from datetime import date, timedelta

from bot import servicios as s
from bot.empresas import crear_empresa
from conftest import CLIENTE, DUENO


def test_RF01_responde_un_texto_con_el_asistente_y_guarda_ambos_mensajes(servicios, almacen, empresa, whatsapp, mensaje, ahora):
    # Dado un cliente que escribe por primera vez
    # Cuando el bot atiende su mensaje
    resultado = servicios.atender(empresa, mensaje("¿Cuánto cuesta?"), ahora)
    # Entonces le envía la respuesta del asistente y guarda las dos partes de la conversación
    assert resultado == s.RESPONDIDO
    assert whatsapp.enviados == [(CLIENTE, "Hola, ¿en qué le puedo ayudar?")]
    assert almacen.historial(empresa["id"], CLIENTE) == [
        {"role": "user", "content": "¿Cuánto cuesta?"},
        {"role": "assistant", "content": "Hola, ¿en qué le puedo ayudar?"},
    ]


def test_RF02_el_asistente_recibe_la_conversacion_anterior(servicios, empresa, asistente, mensaje, ahora):
    # Dado un cliente que ya escribió una vez
    servicios.atender(empresa, mensaje("Hola"), ahora)
    # Cuando escribe otra vez
    servicios.atender(empresa, mensaje("¿Y el precio?"), ahora)
    # Entonces el asistente recibe toda la conversación, en orden
    assert [m["content"] for m in asistente.historiales[-1]] == ["Hola", "Hola, ¿en qué le puedo ayudar?", "¿Y el precio?"]


def test_RF03_audio_recibe_aviso_de_solo_texto_sin_llamar_al_asistente(servicios, empresa, asistente, whatsapp, mensaje, ahora):
    # Dado un cliente que manda un audio
    resultado = servicios.atender(empresa, mensaje(tipo="audio"), ahora)
    # Entonces le pide que escriba, y no gasta una llamada a Claude
    assert resultado == s.NO_TEXTO
    assert whatsapp.enviados == [(CLIENTE, s.RESPUESTA_NO_TEXTO)] and asistente.historiales == []


def test_RF04_la_marca_deriva_al_dueno_pausa_el_chat_y_no_se_envia_la_marca(servicios, almacen, empresa, asistente, whatsapp, mensaje, ahora):
    # Dado que el asistente decide pasarle el chat al dueño
    asistente.respuestas = ["Le paso con Rosa, enseguida le escribe. [PASAR_A_HUMANO]"]
    # Cuando el bot atiende el mensaje
    resultado = servicios.atender(empresa, mensaje("Quiero comprar"), ahora)
    # Entonces el cliente recibe el texto sin la marca, el chat queda en pausa 12 h y el dueño recibe el aviso
    assert resultado == s.DERIVADO
    assert whatsapp.enviados[0] == (CLIENTE, "Le paso con Rosa, enseguida le escribe.")
    assert almacen.pausado_hasta(empresa["id"], CLIENTE) == ahora + timedelta(hours=12)
    assert whatsapp.enviados[1][0] == DUENO and CLIENTE in whatsapp.enviados[1][1]


def test_RF04_chat_en_pausa_no_recibe_respuesta_hasta_que_vence(servicios, almacen, empresa, whatsapp, mensaje, ahora):
    # Dado un chat en pausa hasta dentro de una hora
    almacen.pausar(empresa["id"], CLIENTE, ahora + timedelta(hours=1))
    # Cuando el cliente escribe ahora y después de que vence la pausa
    durante = servicios.atender(empresa, mensaje("¿Sigue ahí?"), ahora)
    despues = servicios.atender(empresa, mensaje("Hola de nuevo"), ahora + timedelta(hours=2))
    # Entonces primero no responde y después sí
    assert (durante, despues) == (s.PAUSADO, s.RESPONDIDO)
    assert len(whatsapp.enviados) == 1


def test_RF05_mensaje_repetido_se_atiende_una_sola_vez(servicios, empresa, whatsapp, mensaje, ahora):
    # Dado que Meta reenvía el mismo mensaje (mismo id)
    repetido = mensaje("Hola", id="wamid.repetido")
    # Cuando llega dos veces
    # Entonces se responde una sola vez
    assert (servicios.atender(empresa, repetido, ahora), servicios.atender(empresa, repetido, ahora)) == (s.RESPONDIDO, s.DUPLICADO)
    assert len(whatsapp.enviados) == 1


def test_RF06_si_falla_el_asistente_el_cliente_recibe_una_disculpa_y_queda_registrado(servicios, almacen, empresa, asistente, whatsapp, mensaje, ahora):
    # Dado que la API de Claude falla (sin créditos, caída, etc.)
    asistente.error = RuntimeError("API caída")
    # Cuando el bot atiende un mensaje
    resultado = servicios.atender(empresa, mensaje("Hola"), ahora)
    # Entonces el cliente recibe la disculpa y el panel ve el error
    assert resultado == s.ERROR
    assert whatsapp.enviados == [(CLIENTE, s.RESPUESTA_ERROR)]
    assert almacen.contar_eventos(empresa["id"], "error", ahora - timedelta(hours=1)) == 1


def test_RF12_las_conversaciones_de_dos_empresas_no_se_mezclan(servicios, almacen, empresa, asistente, mensaje, ahora):
    # Dadas dos empresas activas y un mismo cliente que les escribe a las dos
    otra = crear_empresa(almacen, "Otra Tienda", ahora)
    otra = almacen.actualizar_empresa(otra["id"], {"estado": "activa"}, ahora)
    servicios.atender(empresa, mensaje("Hola tienda 1"), ahora)
    # Cuando le escribe a la segunda
    servicios.atender(otra, mensaje("Hola tienda 2"), ahora)
    # Entonces el asistente de la segunda solo ve su propia conversación
    assert [m["content"] for m in asistente.historiales[-1]] == ["Hola tienda 2"]


def test_RF17_cada_respuesta_suma_sus_tokens_al_dia_de_bolivia(servicios, almacen, empresa, mensaje, ahora):
    # Dadas dos respuestas (el doble cuenta 1000 tokens de entrada y 50 de salida)
    servicios.atender(empresa, mensaje("Hola"), ahora)
    servicios.atender(empresa, mensaje("Gracias"), ahora)
    # Entonces el uso del 7 de noviembre suma ambas
    assert almacen.uso(empresa["id"], date(2026, 11, 1)) == [
        {"dia": date(2026, 11, 7), "llamadas": 2, "entrada": 2000, "salida": 100}]


def test_RF18_en_prueba_solo_le_responde_al_dueno(servicios, almacen, empresa, whatsapp, mensaje, ahora):
    # Dada una empresa en prueba (revisión)
    empresa = almacen.actualizar_empresa(empresa["id"], {"estado": "revision"}, ahora)
    # Cuando le escriben un cliente y el dueño
    cliente = servicios.atender(empresa, mensaje("Hola", numero=CLIENTE), ahora)
    dueno = servicios.atender(empresa, mensaje("Hola, soy yo", numero=DUENO), ahora)
    # Entonces solo el dueño recibe respuesta
    assert (cliente, dueno) == (s.EN_REVISION, s.RESPONDIDO)
    assert [n for n, _ in whatsapp.enviados] == [DUENO]


def test_RF18_pausada_o_en_borrador_no_responde_a_nadie(servicios, almacen, empresa, whatsapp, mensaje, ahora):
    for estado in ("pausada", "borrador"):
        e = almacen.actualizar_empresa(empresa["id"], {"estado": estado}, ahora)
        assert servicios.atender(e, mensaje("Hola", numero=DUENO), ahora) == s.INACTIVA
    assert whatsapp.enviados == []


def test_RF19_los_numeros_ignorados_no_reciben_respuesta(servicios, almacen, empresa, whatsapp, mensaje, ahora):
    # Dado que el número del cliente está en la lista de ignorados (escrito con + y espacios)
    empresa = almacen.actualizar_empresa(empresa["id"], {"numeros_ignorados": "+591 7000 0001, 59170000555"}, ahora)
    # Entonces no se le responde
    assert servicios.atender(empresa, mensaje("Hola mamá"), ahora) == s.IGNORADO
    assert whatsapp.enviados == []
