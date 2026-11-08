"""Panel del negocio (/negocio): accesos, agenda, citas, pacientes y horario. Requisitos BOT-RF-21 a 25."""
import re
from datetime import timedelta

from bot import agenda as A
from bot.empresas import crear_empresa
from conftest import csrf_de

LUNES = "2026-11-09"  # la semana del reloj de las pruebas (sábado 07/11/2026)
HORARIO = {"duracion": 30, "turnos": [{"dia": 0, "sede": "INCOR", "desde": "10:30", "hasta": "12:00"}]}


def _acceso(almacen, empresa, ahora, usuario="giovanna", rol="dueno"):
    u, clave, errores = A.crear_usuario(almacen, empresa["id"], "Giovanna Daza", usuario, rol, ahora)
    assert not errores
    return u, clave


def _entrar(web, usuario, clave):
    return web.post("/negocio/entrar", data={"csrf": csrf_de(web.get("/negocio/entrar")), "usuario": usuario, "clave": clave})


def _sesion(web, almacen, empresa, ahora, usuario="giovanna"):
    """Entra con un usuario que ya eligió su contraseña. Devuelve el csrf de la sesión."""
    u, clave = _acceso(almacen, empresa, ahora, usuario)
    almacen.actualizar_usuario(u["id"], {"debe_cambiar": False})
    _entrar(web, usuario, clave)
    return csrf_de(web.get("/negocio/semana"))


# ------------------------------------------------------------------ BOT-RF-21 accesos
def test_RF21_el_admin_crea_el_acceso_y_ve_la_contrasena_temporal_una_sola_vez(admin, empresa, almacen):
    web, csrf = admin
    # Cuando el admin crea un acceso para la asistente
    r = web.post(f"/panel/empresas/{empresa['id']}/usuarios", data={"csrf": csrf, "nombre": "Carla Vaca", "usuario": "Carla", "rol": "asistente"})
    html = r.get_data(as_text=True)
    # Entonces ve la contraseña temporal en esa respuesta, lista para mandar por WhatsApp
    clave = re.search(r"Contraseña temporal: ([a-z0-9-]{14})", html).group(1)
    assert "https://bot.test/negocio/entrar" in html and "Usuario: carla" in html
    # Y en la base solo queda su hash; al recargar el detalle ya no aparece
    u = almacen.usuario_por_login("carla")
    assert clave not in u["clave_hash"] and u["rol"] == "asistente"
    assert clave not in web.get(f"/panel/empresas/{empresa['id']}").get_data(as_text=True)


def test_RF21_con_la_contrasena_temporal_primero_hay_que_elegir_una_propia(web, empresa, almacen, ahora):
    _, clave = _acceso(almacen, empresa, ahora)
    # Cuando entra con la temporal, lo lleva a cambiarla y no lo deja ver la agenda antes
    assert _entrar(web, "Giovanna", clave).headers["Location"].endswith("/negocio/clave")
    assert web.get("/negocio/semana").headers["Location"].endswith("/negocio/clave")
    csrf = csrf_de(web.get("/negocio/clave"))
    corta = web.post("/negocio/clave", data={"csrf": csrf, "actual": clave, "nueva": "corta", "repetida": "corta"})
    assert "al menos 8 caracteres" in corta.get_data(as_text=True)
    ok = web.post("/negocio/clave", data={"csrf": csrf, "actual": clave, "nueva": "mi-clave-propia", "repetida": "mi-clave-propia"})
    # Entonces ya entra a su agenda, y la temporal deja de servir
    assert ok.headers["Location"].endswith("/negocio/semana")
    assert web.get("/negocio/semana").status_code == 200
    web.post("/negocio/salir", data={"csrf": csrf})
    assert _entrar(web, "giovanna", clave).status_code == 401
    assert _entrar(web, "giovanna", "mi-clave-propia").status_code == 302


def test_RF21_sin_sesion_o_con_un_acceso_desactivado_no_se_entra(web, empresa, almacen, ahora):
    assert web.get("/negocio/semana").headers["Location"].startswith("/negocio/entrar")
    u, clave = _acceso(almacen, empresa, ahora)
    almacen.actualizar_usuario(u["id"], {"activo": False})
    assert _entrar(web, "giovanna", clave).status_code == 401


def test_RF21_se_bloquea_tras_5_intentos_fallidos(web, empresa, almacen, ahora):
    _, clave = _acceso(almacen, empresa, ahora)
    for _ in range(5):
        _entrar(web, "giovanna", "equivocada")
    r = _entrar(web, "giovanna", clave)
    assert r.status_code == 401 and "Demasiados intentos" in r.get_data(as_text=True)


def test_RF21_un_usuario_no_ve_ni_toca_lo_de_otra_empresa(web, empresa, almacen, ahora):
    # Dada otra empresa con un paciente y una cita
    otra = crear_empresa(almacen, "Otra Clínica", ahora)
    p = almacen.crear_paciente(otra["id"], "Paciente Ajeno", "59170000055", ahora)
    c = almacen.crear_cita(otra["id"], {"paciente_id": p["id"], "inicio": ahora, "fin": ahora + timedelta(minutes=30), "estado": "confirmada"}, ahora)
    csrf = _sesion(web, almacen, empresa, ahora)
    # Entonces no puede verlos, cambiarlos ni borrarlos, ni usarlos en una cita suya
    assert web.get(f"/negocio/citas/{c['id']}").status_code == 404
    assert web.get(f"/negocio/pacientes/{p['id']}").status_code == 404
    assert web.post(f"/negocio/citas/{c['id']}/estado", data={"csrf": csrf, "estado": "cancelada"}).status_code == 404
    assert web.post(f"/negocio/pacientes/{p['id']}/borrar", data={"csrf": csrf}).status_code == 404
    r = web.post("/negocio/citas/nueva", data={"csrf": csrf, "paciente_id": p["id"], "fecha": LUNES, "hora": "10:30"})
    assert "Ese paciente no existe." in r.get_data(as_text=True)
    assert "Paciente Ajeno" not in web.get("/negocio/pacientes").get_data(as_text=True)
    assert almacen.cita(otra["id"], c["id"])["estado"] == "confirmada"


def test_RF21_el_panel_del_negocio_no_da_acceso_al_de_administracion(web, empresa, almacen, ahora):
    _sesion(web, almacen, empresa, ahora)
    assert web.get("/panel/").headers["Location"].startswith("/panel/entrar")


def test_RF21_sin_csrf_no_se_guarda_nada(web, empresa, almacen, ahora):
    _sesion(web, almacen, empresa, ahora)
    assert web.post("/negocio/pacientes", data={"nombre": "Ana"}).status_code == 400


# ------------------------------------------------------------------ BOT-RF-22 a 25 agenda
def test_RF22_la_agenda_muestra_los_turnos_libres_del_horario(web, empresa, almacen, ahora):
    almacen.actualizar_empresa(empresa["id"], {"agenda": HORARIO}, ahora)
    _sesion(web, almacen, empresa, ahora)
    dia = web.get(f"/negocio/dia?d={LUNES}").get_data(as_text=True)
    assert dia.count("+ Agendar") == 3 and "Libre · INCOR" in dia
    semana = web.get(f"/negocio/semana?d={LUNES}").get_data(as_text=True)
    assert "3 turnos libres" in semana and "Semana del 9 nov" in semana
    mes = web.get("/negocio/mes?m=2026-11").get_data(as_text=True)
    assert "Noviembre 2026" in mes


def test_RF23_crear_una_cita_con_paciente_nuevo_y_no_dejar_otra_en_el_mismo_horario(web, empresa, almacen, ahora):
    almacen.actualizar_empresa(empresa["id"], {"agenda": HORARIO}, ahora)
    csrf = _sesion(web, almacen, empresa, ahora)
    # Cuando agenda a una paciente nueva a las 10:30 con Bs 125 de adelanto
    r = web.post("/negocio/citas/nueva", data={"csrf": csrf, "nombre": "Ana Pérez", "telefono": "+591 7000 0001", "fecha": LUNES,
                                               "hora": "10:30", "sede": "INCOR", "servicio": "Valoración", "adelanto": "125"})
    assert r.status_code == 302
    # Entonces la cita queda confirmada, con 30 minutos (la duración del horario) y la paciente creada
    cita = almacen.citas(empresa["id"], ahora, ahora + timedelta(days=7))[0]
    assert (cita["paciente_nombre"], cita["paciente_telefono"], cita["estado"], cita["adelanto"]) == ("Ana Pérez", "59170000001", "confirmada", 125.0)
    assert cita["fin"] - cita["inicio"] == timedelta(minutes=30)
    # Y otra cita que se superpone no se guarda y explica con quién choca
    choque = web.post("/negocio/citas/nueva", data={"csrf": csrf, "nombre": "Beto", "telefono": "", "fecha": LUNES, "hora": "10:45"})
    assert "Ese horario ya está ocupado por Ana Pérez (10:30 a 11:00)." in choque.get_data(as_text=True)
    assert len(almacen.pacientes(empresa["id"])) == 1  # el paciente del intento fallido no se creó
    # El mismo número se reconoce: no se duplica la paciente
    web.post("/negocio/citas/nueva", data={"csrf": csrf, "nombre": "Ana P.", "telefono": "59170000001", "fecha": LUNES, "hora": "11:00"})
    assert len(almacen.pacientes(empresa["id"])) == 1 and len(almacen.citas_de_paciente(empresa["id"], cita["paciente_id"])) == 2


def test_RF23_reprogramar_marcar_atendida_y_cancelar(web, empresa, almacen, ahora):
    csrf = _sesion(web, almacen, empresa, ahora)
    web.post("/negocio/citas/nueva", data={"csrf": csrf, "nombre": "Ana", "fecha": LUNES, "hora": "10:30", "adelanto": "125"})
    cid = almacen.citas(empresa["id"], ahora, ahora + timedelta(days=7))[0]["id"]
    # Reprogramar al martes a las 11:00, con 45 minutos
    web.post(f"/negocio/citas/{cid}", data={"csrf": csrf, "fecha": "2026-11-10", "hora": "11:00", "duracion": "45", "adelanto": "125"})
    cita = almacen.cita(empresa["id"], cid)
    assert cita["inicio"].astimezone(cita["inicio"].tzinfo).isoformat().startswith("2026-11-10") and cita["fin"] - cita["inicio"] == timedelta(minutes=45)
    # Atendida pide cuánto se cobró
    sin_monto = web.post(f"/negocio/citas/{cid}/estado", data={"csrf": csrf, "estado": "atendida", "metodo_pago": "qr"}, follow_redirects=True)
    assert "Escribe cuánto se cobró" in sin_monto.get_data(as_text=True)
    web.post(f"/negocio/citas/{cid}/estado", data={"csrf": csrf, "estado": "atendida", "cobrado": "125", "metodo_pago": "qr"})
    assert (almacen.cita(empresa["id"], cid)["estado"], almacen.cita(empresa["id"], cid)["cobrado"]) == ("atendida", 125.0)
    paciente = web.get(f"/negocio/pacientes/{cita['paciente_id']}").get_data(as_text=True)
    assert "Bs 250" in paciente  # adelanto + lo cobrado
    # Cancelada libera el horario: otra cita puede ocuparlo
    web.post(f"/negocio/citas/{cid}/estado", data={"csrf": csrf, "estado": "cancelada"})
    r = web.post("/negocio/citas/nueva", data={"csrf": csrf, "nombre": "Beto", "fecha": "2026-11-10", "hora": "11:00"})
    assert r.status_code == 302


def test_RF24_pacientes_se_agregan_buscan_y_no_repiten_numero(web, empresa, almacen, ahora):
    csrf = _sesion(web, almacen, empresa, ahora)
    web.post("/negocio/pacientes", data={"csrf": csrf, "nombre": "Ana Rojas", "telefono": "591 70000001"})
    repetido = web.post("/negocio/pacientes", data={"csrf": csrf, "nombre": "Otra", "telefono": "59170000001"})
    assert "Ese número ya es de Ana Rojas." in repetido.get_data(as_text=True)
    assert "Ana Rojas" in web.get("/negocio/pacientes?q=rojas").get_data(as_text=True)
    assert "Nadie coincide" in web.get("/negocio/pacientes?q=zzz").get_data(as_text=True)


def test_RF25_el_horario_y_los_bloqueos_se_guardan_desde_el_panel(web, empresa, almacen, ahora):
    csrf = _sesion(web, almacen, empresa, ahora)
    web.post("/negocio/horario", data={"csrf": csrf, "duracion": "20", "dia_0": "0", "sede_0": "INCOR", "desde_0": "10:30", "hasta_0": "11:30",
                                       "dia_1": "0", "sede_1": "", "desde_1": "", "hasta_1": ""})
    assert almacen.empresa(empresa["id"])["agenda"] == {"duracion": 20, "turnos": [{"dia": 0, "sede": "INCOR", "desde": "10:30", "hasta": "11:30"}]}
    assert web.get(f"/negocio/dia?d={LUNES}").get_data(as_text=True).count("+ Agendar") == 3
    # Al bloquear el lunes, ya no hay turnos libres ese día
    web.post("/negocio/horario/bloqueos", data={"csrf": csrf, "desde": LUNES, "motivo": "Feriado"})
    dia = web.get(f"/negocio/dia?d={LUNES}").get_data(as_text=True)
    assert "+ Agendar" not in dia and "No atiende: Feriado" in dia
