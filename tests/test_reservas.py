"""Reservas por WhatsApp (etapa 2, v3.1). Requisitos BOT-RF-26 a 30.

El reloj de las pruebas es el sábado 07/11/2026, 16:00 en Bolivia. El horario de
prueba atiende los lunes en INCOR de 10:30 a 12:00, en turnos de 30 minutos."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace as N

import pytest

from bot import reservas as R
from bot import servicios as s
from bot.asistente import Asistente
from bot.reglas import extraer_mensajes
from conftest import CLIENTE, DUENO, csrf_de
from test_negocio import _sesion

ASISTENTE = "59177000000"
HORARIO = {"duracion": 30, "turnos": [{"dia": 0, "sede": "INCOR", "desde": "10:30", "hasta": "12:00"}]}
COBRO = {"activo": True, "porcentaje": 50, "plazo_horas": 2, "valoracion": {"INCOR": 250},
         "instrucciones": "Banco Ejemplo, cuenta 123", "aviso_numero": ASISTENTE,
         "ubicaciones": {"INCOR": "Segundo anillo"}}
LUNES_1030 = "2026-11-09T10:30|INCOR"
LUNES_1100 = "2026-11-09T11:00|INCOR"


@pytest.fixture
def negocio(almacen, empresa, ahora):
    """La empresa activa, con horario y cobros: el bot agenda."""
    return almacen.actualizar_empresa(empresa["id"], {"agenda": HORARIO, "cobro": dict(COBRO)}, ahora)


def _reservar(almacen, negocio, ahora, turno=LUNES_1030, numero=CLIENTE):
    return R.reservar(almacen, negocio, numero, turno, "Ana Pérez", "escapes de orina", ahora, "America/La_Paz")


# ------------------------------------------------------------------ BOT-RF-26 turnos libres
def test_RF26_ofrece_solo_turnos_reales_del_horario_y_libres(almacen, negocio, ahora):
    # Dado un turno ya ocupado el lunes a las 10:30
    _reservar(almacen, negocio, ahora, numero="59170000222")
    # Cuando el bot pide turnos libres
    turnos = R.turnos_libres(almacen, negocio, ahora, "America/La_Paz")
    # Entonces ofrece los del lunes que quedan, con su sede, y nunca el ocupado
    assert [t["turno"] for t in turnos[:2]] == [LUNES_1100, "2026-11-09T11:30|INCOR"]
    assert turnos[0]["dia"] == "lunes 9 de noviembre" and turnos[0]["sede"] == "INCOR"
    # Y un día bloqueado no ofrece nada
    almacen.crear_bloqueo(negocio["id"], date(2026, 11, 9), date(2026, 11, 9), "Feriado")
    assert all(not t["turno"].startswith("2026-11-09") for t in R.turnos_libres(almacen, negocio, ahora, "America/La_Paz"))


def test_RF26_sin_activar_o_sin_horario_el_bot_no_agenda(almacen, empresa, ahora):
    assert not R.activo(empresa)
    sin_horario = almacen.actualizar_empresa(empresa["id"], {"cobro": dict(COBRO)}, ahora)
    assert not R.activo(sin_horario)


# ------------------------------------------------------------------ BOT-RF-27 reservar con adelanto
def test_RF27_un_paciente_nuevo_reserva_y_debe_el_50_de_la_valoracion_de_su_sede(almacen, negocio, ahora):
    r = _reservar(almacen, negocio, ahora)
    assert r["ok"] and (r["adelanto"], r["plazo_horas"], r["hora"], r["sede"]) == (125.0, 2.0, "10:30", "INCOR")
    cita = almacen.cita(negocio["id"], r["cita_id"])
    assert (cita["estado"], cita["origen"], cita["adelanto_pedido"]) == ("pendiente_pago", "bot", 125.0)
    assert cita["reserva_vence"] == ahora + timedelta(hours=2) and cita["servicio"] == "Valoración: escapes de orina"
    assert cita["paciente_nombre"] == "Ana Pérez" and cita["paciente_telefono"] == CLIENTE
    # Y no puede tener dos reservas a la vez, ni otro puede tomar ese turno
    assert _reservar(almacen, negocio, ahora, LUNES_1100)["motivo"] == "ya_tiene_reserva"
    assert _reservar(almacen, negocio, ahora, numero="59170000333")["motivo"] == "ocupado"


def test_RF27_los_casos_que_no_se_agendan_solos_piden_derivar(almacen, negocio, ahora):
    # Un turno que no está en el horario, o demasiado pronto
    assert _reservar(almacen, negocio, ahora, "2026-11-09T15:00|INCOR")["motivo"] == "turno_invalido"
    # Una sede sin precio de valoración
    sin_precio = almacen.actualizar_empresa(negocio["id"], {"cobro": {**COBRO, "valoracion": {}}}, ahora)
    assert _reservar(almacen, sin_precio, ahora)["motivo"] == "sin_precio_de_valoracion"
    # Un paciente que ya se atendió (las sesiones de tratamiento las agenda una persona)
    p = almacen.crear_paciente(negocio["id"], "Ana Pérez", CLIENTE, ahora)
    almacen.crear_cita(negocio["id"], {"paciente_id": p["id"], "inicio": ahora - timedelta(days=30), "fin": ahora - timedelta(days=30, minutes=-30),
                                       "estado": "atendida"}, ahora)
    assert _reservar(almacen, negocio, ahora)["motivo"] == "paciente_con_historial"


# ------------------------------------------------------------------ BOT-RF-29 reprogramar, cancelar y vencer
def test_RF29_reprograma_si_faltan_mas_de_24_horas_y_no_si_faltan_menos(almacen, negocio, ahora):
    r = _reservar(almacen, negocio, ahora)
    almacen.actualizar_cita(negocio["id"], r["cita_id"], {"estado": "confirmada", "adelanto": 125}, ahora)
    movida = R.reprogramar(almacen, negocio, CLIENTE, LUNES_1100, ahora, "America/La_Paz")
    assert movida["ok"] and movida["hora"] == "11:00" and movida["adelanto_pagado"] == 125
    # El domingo a las 12:00 (menos de 24 h antes del lunes 11:00) ya no se puede
    domingo = datetime(2026, 11, 8, 16, 0, tzinfo=timezone.utc)
    assert R.reprogramar(almacen, negocio, CLIENTE, LUNES_1030, domingo, "America/La_Paz")["motivo"] == "menos_de_24_horas"


def test_RF29_sin_comprobante_a_tiempo_el_horario_se_libera_y_se_avisa(servicios, almacen, negocio, whatsapp, ahora):
    r = _reservar(almacen, negocio, ahora)
    # Antes del plazo no pasa nada
    assert servicios.vencer_reservas(negocio, ahora + timedelta(hours=1)) == 0
    # Pasado el plazo, la cita se cancela, el turno vuelve a estar libre y el paciente recibe el aviso
    assert servicios.vencer_reservas(negocio, ahora + timedelta(hours=2, minutes=1)) == 1
    assert almacen.cita(negocio["id"], r["cita_id"])["estado"] == "cancelada"
    assert whatsapp.enviados[-1][0] == CLIENTE and "Se liberó tu horario" in whatsapp.enviados[-1][1]
    assert R.turnos_libres(almacen, negocio, ahora + timedelta(hours=3), "America/La_Paz")[0]["turno"] == LUNES_1030


def test_RF29_cancelar_avisa_que_el_adelanto_no_se_devuelve(almacen, negocio, ahora):
    r = _reservar(almacen, negocio, ahora)
    almacen.actualizar_cita(negocio["id"], r["cita_id"], {"estado": "confirmada", "adelanto": 125}, ahora)
    c = R.cancelar(almacen, negocio, CLIENTE, ahora, "America/La_Paz")
    assert c["ok"] and c["nota"] == "El adelanto no se devuelve."
    assert almacen.cita(negocio["id"], r["cita_id"])["estado"] == "cancelada"


# ------------------------------------------------------------------ BOT-RF-26/27 en la conversación
def test_RF27_en_el_chat_claude_usa_las_herramientas_y_el_bot_manda_el_qr(servicios, almacen, negocio, asistente, whatsapp, mensaje, ahora):
    # Dado un negocio con QR de cobro cargado, y Claude que primero mira turnos y después reserva el primero
    servicios._url_base = "https://bot.test"
    qr = almacen.guardar_archivo(negocio["id"], "qr", "image/png", b"QR", ahora)
    negocio = almacen.actualizar_empresa(negocio["id"], {"cobro": {**COBRO, "qr_id": qr}}, ahora)
    asistente.herramientas_a_usar = [("ver_turnos_libres", {"sede": "incor"}),
                                     ("reservar_turno", lambda res: {"turno": res[0]["turnos"][0]["turno"], "nombre": "Ana Pérez", "motivo": "control"})]
    asistente.respuestas = ["Listo, Ana: te aparté el lunes a las 10:30. El adelanto es de Bs 125."]
    # Cuando el paciente pide una cita
    assert servicios.atender(negocio, mensaje("Quiero una cita para el lunes"), ahora) == s.RESPONDIDO
    # Entonces Claude recibió la hora de Bolivia y las reglas, la reserva quedó por pagar y llegó el QR
    assert "sábado 7 de noviembre de 2026, 16:00" in asistente.extra_sistema
    assert asistente.resultados[1]["ok"] and asistente.resultados[1]["adelanto"] == 125.0
    assert whatsapp.imagenes == [(CLIENTE, f"https://bot.test/pago/{negocio['slug']}/qr?v={qr}", "QR para pagar el adelanto")]


# ------------------------------------------------------------------ BOT-RF-28 comprobante
def test_RF28_la_foto_del_comprobante_pasa_la_cita_a_por_revisar_y_avisa_a_la_asistente(servicios, almacen, negocio, whatsapp, mensaje, ahora):
    r = _reservar(almacen, negocio, ahora)
    foto = mensaje(tipo="image")
    foto = foto.__class__(foto.id, foto.numero, "image", "", "MEDIA-123")
    assert servicios.atender(negocio, foto, ahora + timedelta(minutes=30)) == s.COMPROBANTE
    cita = almacen.cita(negocio["id"], r["cita_id"])
    assert cita["estado"] == "por_revisar" and almacen.archivo(negocio["id"], cita["comprobante_id"])["datos"] == b"\x89PNG-comprobante"
    assert whatsapp.descargados == ["MEDIA-123"]
    assert whatsapp.enviados[0][0] == CLIENTE and "Recibimos tu comprobante" in whatsapp.enviados[0][1]
    assert whatsapp.enviados[1][0] == ASISTENTE and "Bs 125" in whatsapp.enviados[1][1] and f"/negocio/citas/{cita['id']}" in whatsapp.enviados[1][1]
    # Y una reserva por revisar ya no se libera sola
    assert servicios.vencer_reservas(negocio, ahora + timedelta(hours=5)) == 0


def test_RF28_una_foto_sin_reserva_recibe_la_respuesta_de_siempre(servicios, negocio, whatsapp, mensaje, ahora):
    foto = mensaje(tipo="image")
    foto = foto.__class__(foto.id, foto.numero, "image", "", "MEDIA-9")
    assert servicios.atender(negocio, foto, ahora) == s.NO_TEXTO
    assert not getattr(whatsapp, "descargados", [])


def test_RF28_meta_avisa_el_id_de_la_foto_y_su_texto(payload):
    datos = payload({"id": "wamid.1", "from": CLIENTE, "type": "image", "image": {"id": "MEDIA-1", "caption": " pago "}})
    m = extraer_mensajes(datos)[0]
    assert (m.tipo, m.media_id, m.texto) == ("image", "MEDIA-1", "pago")


# ------------------------------------------------------------------ BOT-RF-30 aprobar o rechazar en el panel
def _con_comprobante(servicios, almacen, negocio, mensaje, ahora):
    r = _reservar(almacen, negocio, ahora)
    foto = mensaje(tipo="image")
    servicios.atender(negocio, foto.__class__(foto.id, foto.numero, "image", "", "M1"), ahora)
    return almacen.cita(negocio["id"], r["cita_id"])


def test_RF30_aprobar_confirma_la_cita_anota_el_adelanto_y_le_avisa_al_paciente(web, servicios, almacen, negocio, whatsapp, mensaje, ahora):
    cita = _con_comprobante(servicios, almacen, negocio, mensaje, ahora)
    csrf = _sesion(web, almacen, negocio, ahora)
    html = web.get(f"/negocio/citas/{cita['id']}").get_data(as_text=True)
    assert "Aprobar pago" in html and f"/negocio/archivos/{cita['comprobante_id']}" in html
    assert web.get(f"/negocio/archivos/{cita['comprobante_id']}").data == b"\x89PNG-comprobante"
    web.post(f"/negocio/citas/{cita['id']}/aprobar", data={"csrf": csrf, "monto": "125"})
    cita = almacen.cita(negocio["id"], cita["id"])
    assert (cita["estado"], cita["adelanto"], cita["reserva_vence"]) == ("confirmada", 125.0, None)
    assert whatsapp.enviados[-1][0] == CLIENTE and "confirmada" in whatsapp.enviados[-1][1] and "Segundo anillo" in whatsapp.enviados[-1][1]


def test_RF30_rechazar_vuelve_a_pedir_el_comprobante_con_un_plazo_nuevo(web, servicios, almacen, negocio, whatsapp, mensaje, ahora):
    cita = _con_comprobante(servicios, almacen, negocio, mensaje, ahora)
    csrf = _sesion(web, almacen, negocio, ahora)
    web.post(f"/negocio/citas/{cita['id']}/rechazar", data={"csrf": csrf, "motivo": "el monto no coincide"})
    cita = almacen.cita(negocio["id"], cita["id"])
    assert cita["estado"] == "pendiente_pago" and cita["reserva_vence"] == ahora + timedelta(hours=2)
    assert "el monto no coincide" in whatsapp.enviados[-1][1]


def test_RF30_la_pestana_pagos_cuenta_los_comprobantes_y_otra_empresa_no_ve_los_archivos(web, servicios, almacen, negocio, mensaje, ahora):
    cita = _con_comprobante(servicios, almacen, negocio, mensaje, ahora)
    _sesion(web, almacen, negocio, ahora)
    html = web.get("/negocio/pagos").get_data(as_text=True)
    assert 'class="contador"' in html and "Ana Pérez" in html
    # La hora es la de Bolivia (la reserva es el lunes a las 10:30), no la universal
    assert "9 nov a las 10:30 en INCOR" in html and "Configurar cobros" in html
    # Un usuario de otra empresa no puede ver el comprobante
    from bot.empresas import crear_empresa
    otra = crear_empresa(almacen, "Otra Tienda", ahora)
    web.post("/negocio/salir", data={"csrf": csrf_de(web.get("/negocio/semana"))})
    _sesion(web, almacen, otra, ahora, usuario="otra")
    assert web.get(f"/negocio/archivos/{cita['comprobante_id']}").status_code == 404


def test_RF30_la_duena_configura_los_cobros_y_la_asistente_no(web, almacen, empresa, ahora):
    negocio = almacen.actualizar_empresa(empresa["id"], {"agenda": HORARIO}, ahora)
    csrf = _sesion(web, almacen, negocio, ahora)
    r = web.post("/negocio/cobros", data={"csrf": csrf, "activo": "1", "porcentaje": "50", "plazo_horas": "2",
                                          "valoracion_0": "250", "ubicacion_0": "Segundo anillo", "instrucciones": "Banco X",
                                          "aviso_numero": "+591 7700 0000"}, follow_redirects=True)
    assert "El bot ya agenda" in r.get_data(as_text=True)
    cobro = almacen.empresa(empresa["id"])["cobro"]
    assert cobro["valoracion"] == {"INCOR": 250.0} and cobro["aviso_numero"] == ASISTENTE and R.activo(almacen.empresa(empresa["id"]))
    # Activar sin ningún precio se explica
    r = web.post("/negocio/cobros", data={"csrf": csrf, "activo": "1", "porcentaje": "50", "plazo_horas": "2"})
    assert "carga el precio de la valoración" in r.get_data(as_text=True)


def test_RF30_el_qr_de_cobro_es_publico_y_solo_si_es_un_qr(web, almacen, negocio, ahora):
    qr = almacen.guardar_archivo(negocio["id"], "qr", "image/png", b"QR", ahora)
    almacen.actualizar_empresa(negocio["id"], {"cobro": {**COBRO, "qr_id": qr}}, ahora)
    assert web.get(f"/pago/{negocio['slug']}/qr").data == b"QR"
    comprobante = almacen.guardar_archivo(negocio["id"], "comprobante", "image/png", b"PRIVADO", ahora)
    almacen.actualizar_empresa(negocio["id"], {"cobro": {**COBRO, "qr_id": comprobante}}, ahora)
    assert web.get(f"/pago/{negocio['slug']}/qr").status_code == 404


# ------------------------------------------------------------------ Claude con herramientas
def test_RF27_el_asistente_ejecuta_las_herramientas_que_pide_claude_y_suma_los_tokens():
    class Cliente:
        def __init__(self):
            self.messages, self.pedidos = self, []

        def create(self, **kw):
            self.pedidos.append(kw)
            if len(self.pedidos) == 1:
                return N(content=[N(type="tool_use", id="t1", name="ver_turnos_libres", input={"sede": "INCOR"})],
                         usage=N(input_tokens=100, output_tokens=10))
            return N(content=[N(type="text", text="Tengo el lunes a las 10:30.")], usage=N(input_tokens=150, output_tokens=12))

    cliente, llamadas = Cliente(), []
    r = Asistente("k", "claude-haiku-5-5", "manual", cliente=cliente).responder(
        [{"role": "user", "content": "¿Turnos?"}], extra_sistema="\n# Hoy", herramientas=R.HERRAMIENTAS,
        ejecutar=lambda n, e: llamadas.append((n, e)) or {"turnos": [{"turno": LUNES_1030}]})
    assert (r.texto, r.entrada, r.salida) == ("Tengo el lunes a las 10:30.", 250, 22)
    assert llamadas == [("ver_turnos_libres", {"sede": "INCOR"})]
    segundo = cliente.pedidos[1]
    assert segundo["system"] == "manual\n# Hoy" and segundo["tools"] == R.HERRAMIENTAS
    assert segundo["messages"][-1]["content"][0]["tool_use_id"] == "t1" and LUNES_1030 in segundo["messages"][-1]["content"][0]["content"]
