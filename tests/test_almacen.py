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


def test_RF11_si_la_base_no_responde_se_avisa_claro_y_un_corte_se_reintenta():
    from contextlib import contextmanager

    from psycopg import OperationalError
    from psycopg_pool import PoolTimeout

    from bot.almacen import BaseDeDatosNoDisponible

    class PoolFalso:
        def __init__(self, fallas):
            self.fallas, self.usos = list(fallas), 0

        @contextmanager
        def connection(self):
            self.usos += 1
            falla = self.fallas.pop(0) if self.fallas else None
            if falla is PoolTimeout:
                raise PoolTimeout("sin conexiones")
            yield self

        def execute(self, sql, params=()):
            if self.fallas and self.fallas[0] is OperationalError:
                self.fallas.pop(0)
                raise OperationalError("server closed the connection unexpectedly")
            return self

        def fetchone(self):
            return ("ok",)

    def almacen_con(pool):
        a = object.__new__(AlmacenPostgres)  # sin conectarse a nada
        a._pool, a._max = pool, 100
        return a

    # Dado un corte a mitad de una consulta: se reintenta una vez y funciona
    pool = PoolFalso([None, OperationalError])
    assert almacen_con(pool)._uno("SELECT 1") == ("ok",) and pool.usos == 2
    # Dada una base que no entrega conexiones: se avisa con un error propio y claro
    with pytest.raises(BaseDeDatosNoDisponible, match="no respondió a tiempo"):
        almacen_con(PoolFalso([PoolTimeout]))._uno("SELECT 1")
