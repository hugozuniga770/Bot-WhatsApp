"""Contrato del almacen (bot/almacen.py). Requisitos BOT-RF-11 y 12.

Cada test corre dos veces: con AlmacenMemoria y con AlmacenPostgres.
El de Postgres se salta si no hay TEST_DATABASE_URL (en el CI siempre hay)."""
from datetime import date, timedelta

import pytest

from bot.almacen import AlmacenPostgres
from conftest import CLIENTE, DUENO


@pytest.fixture
def dos(almacen_contrato, ahora):
    a = almacen_contrato.crear_empresa("Tienda A", "tienda-a", ahora, {"verify_token": "va", "info": {}})
    b = almacen_contrato.crear_empresa("Tienda B", "tienda-b", ahora, {"verify_token": "vb"})
    return a, b


def test_RF12_una_empresa_se_crea_en_borrador_y_se_actualiza_por_partes(almacen_contrato, dos, ahora):
    a, _ = dos
    # Dada una empresa nueva
    assert (a["estado"], a["slug"], a["verify_token"]) == ("borrador", "tienda-a", "va")
    # Cuando se cambian su estado y algunos datos
    almacen_contrato.actualizar_empresa(a["id"], {"estado": "activa", "dueno_numero": DUENO}, ahora)
    almacen_contrato.actualizar_empresa(a["id"], {"info": {"horario": "9 a 19"}}, ahora)
    # Entonces conserva lo anterior y suma lo nuevo
    e = almacen_contrato.empresa_por_slug("tienda-a")
    assert (e["estado"], e["dueno_numero"], e["verify_token"], e["info"]) == ("activa", DUENO, "va", {"horario": "9 a 19"})
    assert [x["slug"] for x in almacen_contrato.empresas()] == ["tienda-a", "tienda-b"]


def test_RF12_no_puede_haber_dos_empresas_con_el_mismo_slug(almacen_contrato, dos, ahora):
    with pytest.raises(ValueError):
        almacen_contrato.crear_empresa("Otra A", "tienda-a", ahora)


def test_RF12_las_conversaciones_y_pausas_de_cada_empresa_estan_separadas(almacen_contrato, dos, ahora):
    a, b = dos
    # Dado el mismo cliente escribiendo a dos empresas
    almacen_contrato.agregar(a["id"], CLIENTE, "user", "para A", ahora)
    almacen_contrato.agregar(b["id"], CLIENTE, "user", "para B", ahora)
    almacen_contrato.pausar(a["id"], CLIENTE, ahora + timedelta(hours=1))
    # Entonces cada empresa ve solo lo suyo
    assert [m["content"] for m in almacen_contrato.historial(b["id"], CLIENTE)] == ["para B"]
    assert almacen_contrato.pausado_hasta(b["id"], CLIENTE) is None
    # Y el mismo id de mensaje es nuevo para cada empresa
    assert almacen_contrato.es_nuevo(a["id"], "wamid.1", ahora) and almacen_contrato.es_nuevo(b["id"], "wamid.1", ahora)
    assert almacen_contrato.es_nuevo(a["id"], "wamid.1", ahora) is False


def test_RF11_el_historial_devuelve_los_ultimos_en_orden(almacen_contrato, dos, ahora):
    a, _ = dos
    # Dado un cliente con 5 mensajes y un almacén que lee como máximo 3
    for i in range(5):
        almacen_contrato.agregar(a["id"], CLIENTE, "user" if i % 2 == 0 else "assistant", f"m{i}", ahora)
    # Entonces vienen los 3 últimos, del más viejo al más nuevo
    assert [m["content"] for m in almacen_contrato.historial(a["id"], CLIENTE)] == ["m2", "m3", "m4"]


def test_RF11_la_pausa_se_guarda_y_se_puede_extender(almacen_contrato, dos, ahora):
    a, _ = dos
    almacen_contrato.pausar(a["id"], CLIENTE, ahora + timedelta(hours=1))
    almacen_contrato.pausar(a["id"], CLIENTE, ahora + timedelta(hours=12))
    assert almacen_contrato.pausado_hasta(a["id"], CLIENTE) == ahora + timedelta(hours=12)


def test_RF15_el_enlace_de_alta_se_guarda_y_se_marca_usado(almacen_contrato, dos, ahora):
    a, _ = dos
    almacen_contrato.crear_invitacion("hash1", a["id"], ahora + timedelta(days=7), ahora)
    assert almacen_contrato.invitacion("hash1")["usada"] is None
    almacen_contrato.usar_invitacion("hash1", ahora)
    assert almacen_contrato.invitacion("hash1")["usada"] == ahora
    assert almacen_contrato.invitacion("no-existe") is None


def test_RF17_el_uso_se_suma_por_dia(almacen_contrato, dos, ahora):
    a, b = dos
    hoy = date(2026, 11, 7)
    almacen_contrato.sumar_uso(a["id"], hoy, 1000, 50)
    almacen_contrato.sumar_uso(a["id"], hoy, 500, 10)
    almacen_contrato.sumar_uso(a["id"], hoy - timedelta(days=1), 7, 3)
    almacen_contrato.sumar_uso(b["id"], hoy, 99, 9)
    assert almacen_contrato.uso(a["id"], hoy - timedelta(days=1)) == [
        {"dia": hoy - timedelta(days=1), "llamadas": 1, "entrada": 7, "salida": 3},
        {"dia": hoy, "llamadas": 2, "entrada": 1500, "salida": 60},
    ]


def test_RF16_actividad_y_eventos_quedan_registrados(almacen_contrato, dos, ahora):
    a, _ = dos
    almacen_contrato.marcar_actividad(a["id"], "webhook", ahora - timedelta(minutes=5))
    almacen_contrato.marcar_actividad(a["id"], "webhook", ahora)
    almacen_contrato.registrar_evento(a["id"], "error", "uno", ahora - timedelta(days=2))
    almacen_contrato.registrar_evento(a["id"], "error", "dos", ahora)
    almacen_contrato.registrar_evento(a["id"], "prueba", "tres", ahora)
    assert almacen_contrato.actividad(a["id"]) == {"webhook": ahora}
    assert [e["detalle"] for e in almacen_contrato.eventos(a["id"], 2)] == ["tres", "dos"]
    assert almacen_contrato.contar_eventos(a["id"], "error", ahora - timedelta(hours=24)) == 1


def test_RF11_el_estado_sobrevive_a_un_reinicio(url_postgres, ahora):
    # Dado un almacén Postgres con una empresa, un mensaje y una pausa
    antes = AlmacenPostgres(url_postgres)
    e = antes.crear_empresa("Tienda", "tienda", ahora, {"verify_token": "v"})
    antes.agregar(e["id"], CLIENTE, "user", "Hola", ahora)
    antes.pausar(e["id"], CLIENTE, ahora + timedelta(hours=12))
    antes.es_nuevo(e["id"], "wamid.viejo", ahora)
    antes.cerrar()
    # Cuando el bot "se reinicia" (un almacén nuevo sobre la misma base)
    despues = AlmacenPostgres(url_postgres)
    # Entonces encuentra todo lo de antes
    assert despues.empresa_por_slug("tienda")["verify_token"] == "v"
    assert despues.historial(e["id"], CLIENTE) == [{"role": "user", "content": "Hola"}]
    assert despues.pausado_hasta(e["id"], CLIENTE) == ahora + timedelta(hours=12)
    assert despues.es_nuevo(e["id"], "wamid.viejo", ahora) is False
    despues.cerrar()


def test_RF11_si_la_base_corta_las_conexiones_el_almacen_sigue_funcionando(url_postgres, ahora):
    # Dado un almacén con conexiones abiertas
    almacen = AlmacenPostgres(url_postgres)
    almacen.crear_empresa("Tienda", "tienda", ahora)
    # Cuando la base corta todas sus conexiones (como Neon al dormirse)
    import psycopg
    with psycopg.connect(url_postgres, autocommit=True) as admin:
        admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                      "WHERE datname = current_database() AND pid <> pg_backend_pid()")
    # Entonces la siguiente operación funciona igual, con una conexión nueva
    assert [e["slug"] for e in almacen.empresas()] == ["tienda"]
    almacen.cerrar()


class ConexionFalsa:
    """Imita una conexión de psycopg: anota consultas y puede fallar."""

    def __init__(self, n, fallas=0):
        self.n, self.closed, self.broken, self.fallas = n, False, False, fallas

    def execute(self, sql, params=()):
        from psycopg import OperationalError
        if self.fallas:
            self.fallas -= 1
            self.closed = True
            raise OperationalError("server closed the connection unexpectedly")
        return self

    def fetchone(self):
        return (1,)

    def close(self):
        self.closed = True


def _pool_falso(fallas_por_conexion=(), conectar_falla=0):
    """PoolSimple con conexiones falsas y un reloj que maneja el test."""
    from psycopg import OperationalError

    from bot.almacen import PoolSimple

    estado = {"abiertas": [], "t": 0.0, "conectar_falla": conectar_falla}
    fallas = list(fallas_por_conexion)

    def conectar(url, **opciones):
        if estado["conectar_falla"]:
            estado["conectar_falla"] -= 1
            raise OperationalError("connection timeout expired")
        con = ConexionFalsa(len(estado["abiertas"]) + 1, fallas.pop(0) if fallas else 0)
        estado["abiertas"].append(con)
        return con

    pool = PoolSimple("postgresql://falsa", conectar=conectar, reloj=lambda: estado["t"], vida_libre=240)
    return pool, estado


def _almacen_con(pool):
    a = object.__new__(AlmacenPostgres)  # sin conectarse a nada
    a._pool, a._max = pool, 100
    return a


def test_RF11_una_conexion_libre_se_reutiliza_y_una_vieja_se_reemplaza():
    pool, estado = _pool_falso()
    almacen = _almacen_con(pool)
    # Dos consultas seguidas usan la misma conexión
    almacen.ping(); almacen.ping()
    assert len(estado["abiertas"]) == 1
    # Después de 5 minutos sin uso (Neon ya la habría cortado) se abre una nueva en el momento
    estado["t"] += 300
    almacen.ping()
    assert len(estado["abiertas"]) == 2 and estado["abiertas"][0].closed


def test_RF11_si_se_corta_una_conexion_se_reintenta_con_otra():
    # Dada una conexión que Neon cortó (falla al usarla)
    pool, estado = _pool_falso(fallas_por_conexion=[1])
    # Entonces la consulta se repite con una conexión nueva y funciona
    assert _almacen_con(pool).ping() is True
    assert len(estado["abiertas"]) == 2 and estado["abiertas"][0].closed


def test_RF11_si_la_base_no_responde_dos_veces_se_avisa_claro():
    from bot.almacen import BaseDeDatosNoDisponible

    # Dada una base que no acepta conexiones (dos intentos fallidos)
    pool, _ = _pool_falso(conectar_falla=2)
    # Entonces se avisa con un error propio, no con un error interno
    with pytest.raises(BaseDeDatosNoDisponible, match="no respondió"):
        _almacen_con(pool).ping()
    # Y si solo falla el primer intento (Neon despertando), el segundo funciona
    pool, _ = _pool_falso(conectar_falla=1)
    assert _almacen_con(pool).ping() is True


def test_RF20_borrar_un_cliente_borra_solo_su_conversacion_en_esa_empresa(almacen_contrato, dos, ahora):
    a, b = dos
    # Dado el mismo cliente en dos empresas, y otro cliente en la primera
    almacen_contrato.agregar(a["id"], CLIENTE, "user", "hola A", ahora)
    almacen_contrato.agregar(a["id"], CLIENTE, "assistant", "respuesta A", ahora)
    almacen_contrato.pausar(a["id"], CLIENTE, ahora + timedelta(hours=1))
    almacen_contrato.agregar(a["id"], DUENO, "user", "otro cliente", ahora)
    almacen_contrato.agregar(b["id"], CLIENTE, "user", "hola B", ahora)
    # Cuando se borran sus datos en la primera
    borrados = almacen_contrato.borrar_cliente(a["id"], CLIENTE)
    # Entonces se borran sus 2 mensajes y su pausa, y nada más
    assert borrados == 2
    assert almacen_contrato.historial(a["id"], CLIENTE) == [] and almacen_contrato.pausado_hasta(a["id"], CLIENTE) is None
    assert len(almacen_contrato.historial(a["id"], DUENO)) == 1 and len(almacen_contrato.historial(b["id"], CLIENTE)) == 1
