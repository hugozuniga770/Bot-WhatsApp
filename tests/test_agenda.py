"""Reglas de la agenda (bot/reglas.py y bot/agenda.py). Requisitos BOT-RF-22 a 25."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from werkzeug.datastructures import MultiDict

from bot import agenda as A
from bot import reglas

ZONA = "America/La_Paz"
LUNES = date(2026, 11, 9)
HORARIO = {"duracion": 30, "turnos": [{"dia": 0, "sede": "INCOR", "desde": "10:30", "hasta": "12:00"},
                                      {"dia": 0, "sede": "Top Center", "desde": "18:30", "hasta": "19:30"}]}


def _cita(id_, hora, minutos=30, estado="confirmada", dia=LUNES):
    inicio = reglas.momento_local(dia, hora, ZONA)
    return {"id": id_, "inicio": inicio, "fin": inicio + timedelta(minutes=minutos), "estado": estado, "paciente_nombre": f"P{id_}"}


def test_RF22_los_turnos_libres_salen_del_horario_y_las_citas_los_ocupan():
    # Dado el horario del lunes (INCOR 10:30-12:00 y Top Center 18:30-19:30, turnos de 30 min)
    # y una cita a las 11:00 y otra cancelada a las 11:30
    citas = [_cita(1, "11:00"), _cita(2, "11:30", estado="cancelada")]
    # Cuando se arma la agenda del lunes
    d = reglas.agenda_del_dia(LUNES, HORARIO, citas, [], ZONA)
    # Entonces la cita ocupa su turno, la cancelada no, y los libres llevan su sede
    resumen = [(i["inicio"].strftime("%H:%M"), i["tipo"], i.get("turno", {}).get("sede")) for i in d["items"]]
    assert resumen == [("10:30", "libre", "INCOR"), ("11:00", "cita", None), ("11:30", "libre", "INCOR"),
                       ("18:30", "libre", "Top Center"), ("19:00", "libre", "Top Center")]
    assert (d["citas"], d["libres"]) == (1, 4)
    # Y el martes, sin horario, no hay turnos
    assert reglas.agenda_del_dia(LUNES + timedelta(days=1), HORARIO, [], [], ZONA)["items"] == []


def test_RF22_una_cita_larga_ocupa_varios_turnos_y_una_fuera_de_horario_igual_aparece():
    citas = [_cita(1, "10:30", minutos=60), _cita(2, "15:00")]
    d = reglas.agenda_del_dia(LUNES, HORARIO, citas, [], ZONA)
    assert [(i["inicio"].strftime("%H:%M"), i["tipo"]) for i in d["items"]][:4] == [
        ("10:30", "cita"), ("11:30", "libre"), ("15:00", "cita"), ("18:30", "libre")]


def test_RF25_un_dia_bloqueado_no_ofrece_turnos_pero_muestra_sus_citas():
    bloqueo = {"id": 1, "desde": LUNES, "hasta": LUNES, "motivo": "Feriado"}
    d = reglas.agenda_del_dia(LUNES, HORARIO, [_cita(1, "11:00")], [bloqueo], ZONA)
    assert (d["libres"], d["citas"], d["bloqueo"]["motivo"]) == (0, 1, "Feriado")


def test_RF23_choques_detecta_superposicion_salvo_canceladas_y_la_misma_cita():
    citas = [_cita(1, "11:00"), _cita(2, "12:00", estado="cancelada")]
    inicio = reglas.momento_local(LUNES, "11:15", ZONA)
    assert [c["id"] for c in reglas.choques(inicio, inicio + timedelta(minutes=30), citas)] == [1]
    assert reglas.choques(inicio, inicio + timedelta(minutes=30), citas, salvo_id=1) == []
    # Pegadas (una termina 11:30 y la otra empieza 11:30) no chocan
    pegada = reglas.momento_local(LUNES, "11:30", ZONA)
    assert reglas.choques(pegada, pegada + timedelta(minutes=30), citas) == []


def test_RF22_la_semana_empieza_el_lunes_y_el_mes_se_completa_con_dias_vecinos():
    assert reglas.semana_de(date(2026, 11, 12))[0] == LUNES
    semanas = reglas.cuadricula_mes(2026, 11)
    assert (semanas[0][0], semanas[-1][-1], len(semanas)) == (date(2026, 10, 26), date(2026, 12, 6), 6)
    assert reglas.cuadricula_mes(2026, 12)[-1][-1] >= date(2026, 12, 31)


def test_RF25_el_horario_se_lee_del_formulario_y_explica_cada_fila_mal_escrita():
    form = MultiDict({"duracion": "20", "dia_0": "2", "sede_0": "SIES", "desde_0": "08:00", "hasta_0": "10:00",
                      "dia_1": "0", "sede_1": "", "desde_1": "", "hasta_1": "",  # fila vacía: se ignora
                      "dia_2": "0", "sede_2": "INCOR", "desde_2": "10:30", "hasta_2": "12:00"})
    agenda, errores = A.leer_horario(form)
    assert errores == {}
    assert [(t["dia"], t["sede"]) for t in agenda["turnos"]] == [(0, "INCOR"), (2, "SIES")] and agenda["duracion"] == 20
    malo, errores = A.leer_horario(MultiDict({"dia_0": "0", "sede_0": "X", "desde_0": "12:00", "hasta_0": "10:00",
                                              "dia_1": "1", "sede_1": "Y", "desde_1": "9", "hasta_1": "10:00"}))
    assert errores == {"fila_0": "La hora de salida tiene que ser después de la de entrada.",
                       "fila_1": "Escribe las horas así: 10:30."}


def test_RF21_usuarios_y_contrasenas_con_reglas_simples():
    assert reglas.normalizar_usuario(" Giovanna Daza ") == "giovanna.daza"
    assert reglas.normalizar_usuario("Asistente_Única!") == "asistente_unica"
    assert reglas.errores_de_clave("corta", "corta") == {"nueva": "La contraseña tiene que tener al menos 8 caracteres."}
    assert reglas.errores_de_clave("larga-123", "otra-1234") == {"repetida": "Las dos contraseñas no son iguales."}
    clave = A.clave_temporal()
    assert len(clave) == 14 and clave.count("-") == 2 and not set(clave) & set("01lo")


def test_RF23_montos_en_bolivianos():
    assert (reglas.bolivianos(2100), reglas.bolivianos(125), reglas.bolivianos(62.5), reglas.bolivianos(None)) == (
        "Bs 2.100", "Bs 125", "Bs 62,50", "—")


def test_RF24_lo_pagado_suma_adelantos_aunque_se_cancele_y_lo_cobrado_solo_si_se_atendio():
    citas = [{"estado": "atendida", "adelanto": 125.0, "cobrado": 125.0},
             {"estado": "cancelada", "adelanto": 90.0, "cobrado": None},
             {"estado": "confirmada", "adelanto": 125.0, "cobrado": None}]
    assert A.resumen_paciente(citas) == {"citas": 2, "pagado": 465.0}
