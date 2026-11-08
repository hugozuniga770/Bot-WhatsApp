"""Donde se guarda todo: empresas, enlaces de alta, conversaciones, uso y eventos.

Hay dos almacenes con los mismos metodos (mismo contrato, mismos tests):
- AlmacenMemoria: para los tests y para probar en tu PC. Se borra al reiniciar.
- AlmacenPostgres: para produccion (PostgreSQL en Neon). Sobrevive a reinicios.

Cada dato de conversacion lleva `empresa_id`: lo de una empresa nunca se
mezcla con lo de otra (BOT-RF-12).
"""
import copy
import logging
import threading
from datetime import date, datetime, timedelta

log = logging.getLogger(__name__)

COLUMNAS_EMPRESA = ("slug", "nombre", "estado")
DIAS_ATENDIDOS = 7
DIAS_EVENTOS = 60

ESQUEMA = """
CREATE TABLE IF NOT EXISTS empresas (
    id          SERIAL PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,
    nombre      TEXT NOT NULL,
    estado      TEXT NOT NULL DEFAULT 'borrador',
    creada      TIMESTAMPTZ NOT NULL,
    actualizada TIMESTAMPTZ NOT NULL,
    datos       JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS invitaciones (
    token_hash  TEXT PRIMARY KEY,
    empresa_id  INT NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    creada      TIMESTAMPTZ NOT NULL,
    vence       TIMESTAMPTZ NOT NULL,
    usada       TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS mensajes (
    id          BIGSERIAL PRIMARY KEY,
    empresa_id  INT NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    numero      TEXT NOT NULL,
    rol         TEXT NOT NULL CHECK (rol IN ('user', 'assistant')),
    texto       TEXT NOT NULL,
    fecha       TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS mensajes_por_chat ON mensajes (empresa_id, numero, id);

CREATE TABLE IF NOT EXISTS pausas (
    empresa_id  INT NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    numero      TEXT NOT NULL,
    hasta       TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (empresa_id, numero)
);

CREATE TABLE IF NOT EXISTS mensajes_atendidos (
    empresa_id  INT NOT NULL,
    id          TEXT NOT NULL,
    creado      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (empresa_id, id)
);

CREATE TABLE IF NOT EXISTS uso (
    empresa_id  INT NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    dia         DATE NOT NULL,
    llamadas    INT NOT NULL DEFAULT 0,
    entrada     BIGINT NOT NULL DEFAULT 0,
    salida      BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (empresa_id, dia)
);

CREATE TABLE IF NOT EXISTS actividad (
    empresa_id  INT NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    tipo        TEXT NOT NULL,
    fecha       TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (empresa_id, tipo)
);

CREATE TABLE IF NOT EXISTS eventos (
    id          BIGSERIAL PRIMARY KEY,
    empresa_id  INT NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    tipo        TEXT NOT NULL,
    detalle     TEXT NOT NULL DEFAULT '',
    fecha       TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS eventos_por_empresa ON eventos (empresa_id, id DESC);
"""


class BaseDeDatosNoDisponible(Exception):
    """La base no respondió (por ejemplo, Neon caído o sin red)."""


# Opciones de cada conexión (D-22):
# - connect_timeout: un intento nunca espera más de 15 s (Neon dormido despierta en pocos segundos).
# - keepalives: detectan rápido una conexión que Neon cortó.
OPCIONES_CONEXION = {
    "autocommit": True,
    "prepare_threshold": None,  # compatible con el pooler de Neon
    "connect_timeout": 15,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
}


class PoolSimple:
    """Guarda unas pocas conexiones libres para reutilizarlas.

    Reemplaza al pool de la libreria psycopg-pool (v2.3, D-22): aquel abria las
    conexiones en hilos de fondo y, cuando Neon dormia la base, se quedaba sin
    reintentar y la base nunca despertaba. Aqui, si no hay una conexion libre y sana,
    se abre una en el momento, en el mismo pedido: ese intento llega a Neon y lo despierta.
    """

    def __init__(self, url: str, opciones: dict | None = None, max_libres: int = 4,
                 vida_libre: float = 240.0, conectar=None, reloj=None):
        import time

        import psycopg

        self._url = url
        self._opciones = dict(OPCIONES_CONEXION if opciones is None else opciones)
        self._max_libres = max_libres
        # Neon duerme la base a los 5 min sin consultas y corta las conexiones:
        # una conexion que estuvo libre mas de 4 min ya no se reutiliza.
        self._vida_libre = vida_libre
        self._conectar = conectar or psycopg.connect
        self._reloj = reloj or time.monotonic
        self._libres: list[tuple] = []
        self._lock = threading.Lock()

    def _tomar(self):
        ahora = self._reloj()
        while True:
            with self._lock:
                if not self._libres:
                    break
                con, desde = self._libres.pop()
            if ahora - desde < self._vida_libre and not con.closed:
                return con
            self._cerrar(con)
        return self._conectar(self._url, **self._opciones)

    def _devolver(self, con) -> None:
        if con.closed or getattr(con, "broken", False):
            return
        with self._lock:
            if len(self._libres) < self._max_libres:
                self._libres.append((con, self._reloj()))
                return
        self._cerrar(con)

    @staticmethod
    def _cerrar(con) -> None:
        try:
            con.close()
        except Exception:
            pass

    def connection(self):
        from contextlib import contextmanager

        @contextmanager
        def usar():
            con = self._tomar()
            try:
                yield con
            except BaseException:
                self._cerrar(con)  # estado desconocido: no se reutiliza
                raise
            self._devolver(con)

        return usar()

    def close(self) -> None:
        with self._lock:
            libres, self._libres = self._libres, []
        for con, _ in libres:
            self._cerrar(con)


def _empresa_de_fila(fila) -> dict:
    id_, slug, nombre, estado, creada, actualizada, datos = fila
    empresa = dict(datos or {})
    empresa.update(id=id_, slug=slug, nombre=nombre, estado=estado, creada=creada, actualizada=actualizada)
    return empresa


class AlmacenMemoria:
    def __init__(self, max_leidos: int = 100):
        self._lock = threading.RLock()
        self._max = max_leidos
        self._empresas: dict[int, dict] = {}
        self._invitaciones: dict[str, dict] = {}
        self._mensajes: dict[tuple, list[dict]] = {}
        self._pausas: dict[tuple, datetime] = {}
        self._atendidos: dict[tuple, datetime] = {}
        self._uso: dict[tuple, dict] = {}
        self._actividad: dict[tuple, datetime] = {}
        self._eventos: list[dict] = []

    # ------------------------------------------------ empresas
    def crear_empresa(self, nombre: str, slug: str, ahora: datetime, datos: dict | None = None) -> dict:
        with self._lock:
            if any(e["slug"] == slug for e in self._empresas.values()):
                raise ValueError(f"Ya existe una empresa con el slug {slug}")
            id_ = max(self._empresas, default=0) + 1
            self._empresas[id_] = {**(datos or {}), "id": id_, "slug": slug, "nombre": nombre,
                                   "estado": "borrador", "creada": ahora, "actualizada": ahora}
            return copy.deepcopy(self._empresas[id_])

    def empresa(self, empresa_id: int) -> dict | None:
        with self._lock:
            e = self._empresas.get(empresa_id)
            return copy.deepcopy(e) if e else None

    def empresa_por_slug(self, slug: str) -> dict | None:
        with self._lock:
            for e in self._empresas.values():
                if e["slug"] == slug:
                    return copy.deepcopy(e)
            return None

    def empresas(self) -> list[dict]:
        with self._lock:
            return [copy.deepcopy(e) for _, e in sorted(self._empresas.items())]

    def actualizar_empresa(self, empresa_id: int, cambios: dict, ahora: datetime) -> dict:
        with self._lock:
            e = self._empresas[empresa_id]
            e.update(copy.deepcopy(cambios))
            e["actualizada"] = ahora
            return copy.deepcopy(e)

    # ------------------------------------------------ enlaces de alta
    def crear_invitacion(self, token_hash: str, empresa_id: int, vence: datetime, ahora: datetime) -> None:
        with self._lock:
            self._invitaciones[token_hash] = {"token_hash": token_hash, "empresa_id": empresa_id,
                                              "creada": ahora, "vence": vence, "usada": None}

    def invitacion(self, token_hash: str) -> dict | None:
        with self._lock:
            i = self._invitaciones.get(token_hash)
            return dict(i) if i else None

    def usar_invitacion(self, token_hash: str, ahora: datetime) -> None:
        with self._lock:
            self._invitaciones[token_hash]["usada"] = ahora

    # ------------------------------------------------ conversacion
    def ping(self) -> bool:
        return True

    def borrar_cliente(self, empresa_id: int, numero: str) -> int:
        """Borra la conversación y la pausa de un cliente. Devuelve cuántos mensajes borró."""
        with self._lock:
            borrados = len(self._mensajes.pop((empresa_id, numero), []))
            self._pausas.pop((empresa_id, numero), None)
            return borrados

    def es_nuevo(self, empresa_id: int, mensaje_id: str, ahora: datetime) -> bool:
        """True la primera vez que se ve un mensaje; False si Meta lo reenvia."""
        with self._lock:
            clave = (empresa_id, mensaje_id)
            if clave in self._atendidos:
                return False
            self._atendidos[clave] = ahora
            return True

    def historial(self, empresa_id: int, numero: str) -> list[dict]:
        with self._lock:
            return [dict(m) for m in self._mensajes.get((empresa_id, numero), [])[-self._max:]]

    def agregar(self, empresa_id: int, numero: str, rol: str, texto: str, ahora: datetime) -> None:
        with self._lock:
            self._mensajes.setdefault((empresa_id, numero), []).append({"role": rol, "content": texto})

    def pausado_hasta(self, empresa_id: int, numero: str) -> datetime | None:
        with self._lock:
            return self._pausas.get((empresa_id, numero))

    def pausar(self, empresa_id: int, numero: str, hasta: datetime) -> None:
        with self._lock:
            self._pausas[(empresa_id, numero)] = hasta

    # ------------------------------------------------ uso, actividad y eventos
    def sumar_uso(self, empresa_id: int, dia: date, entrada: int, salida: int) -> None:
        with self._lock:
            u = self._uso.setdefault((empresa_id, dia), {"dia": dia, "llamadas": 0, "entrada": 0, "salida": 0})
            u["llamadas"] += 1
            u["entrada"] += entrada
            u["salida"] += salida

    def uso(self, empresa_id: int, desde: date) -> list[dict]:
        with self._lock:
            return [dict(u) for (e, d), u in sorted(self._uso.items(), key=lambda x: x[0][1])
                    if e == empresa_id and d >= desde]

    def marcar_actividad(self, empresa_id: int, tipo: str, ahora: datetime) -> None:
        with self._lock:
            self._actividad[(empresa_id, tipo)] = ahora

    def actividad(self, empresa_id: int) -> dict[str, datetime]:
        with self._lock:
            return {t: f for (e, t), f in self._actividad.items() if e == empresa_id}

    def registrar_evento(self, empresa_id: int, tipo: str, detalle: str, ahora: datetime) -> None:
        with self._lock:
            self._eventos.append({"id": len(self._eventos) + 1, "empresa_id": empresa_id,
                                  "tipo": tipo, "detalle": detalle, "fecha": ahora})

    def eventos(self, empresa_id: int, limite: int = 20) -> list[dict]:
        with self._lock:
            propios = [dict(e) for e in self._eventos if e["empresa_id"] == empresa_id]
            return list(reversed(propios))[:limite]

    def contar_eventos(self, empresa_id: int, tipo: str, desde: datetime) -> int:
        with self._lock:
            return sum(1 for e in self._eventos
                       if e["empresa_id"] == empresa_id and e["tipo"] == tipo and e["fecha"] >= desde)


class AlmacenPostgres:
    def __init__(self, url: str, max_leidos: int = 100, pool=None):
        if pool is None:
            pool = PoolSimple(url)
        self._pool = pool
        self._max = max_leidos
        try:
            self._preparar()
        except Exception:
            self._pool.close()
            raise

    def _preparar(self) -> None:
        with self._pool.connection() as con:
            vieja = con.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'mensajes' "
                "AND NOT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'mensajes' AND column_name = 'empresa_id')"
            ).fetchone()
            if vieja:
                raise RuntimeError(
                    "La base tiene tablas de una version anterior (v1.x, sin empresas). "
                    "Usa una base nueva en Neon o borra esas tablas."
                )
            con.execute(ESQUEMA)
            con.execute("DELETE FROM mensajes_atendidos WHERE creado < now() - make_interval(days => %s)", (DIAS_ATENDIDOS,))
            con.execute("DELETE FROM eventos WHERE fecha < now() - make_interval(days => %s)", (DIAS_EVENTOS,))

    def cerrar(self) -> None:
        self._pool.close()

    def _con(self, accion):
        """Corre `accion(conexion)`. Si la conexión falla (cortada o sin poder conectar),
        reintenta una vez con una nueva; si vuelve a fallar, avisa con BaseDeDatosNoDisponible."""
        from psycopg import OperationalError

        for intento in (1, 2):
            try:
                with self._pool.connection() as con:
                    return accion(con)
            except OperationalError as e:
                if intento == 2:
                    log.error("La base no respondió dos veces seguidas: %s", str(e).strip()[:200])
                    raise BaseDeDatosNoDisponible("La base de datos no respondió.") from None
                log.warning("Falló una conexión a la base (%s); se reintenta con otra", str(e).strip()[:200])

    def ping(self) -> bool:
        """Una consulta mínima. Si Neon dormía, esto lo despierta."""
        return self._uno("SELECT 1") == (1,)

    def borrar_cliente(self, empresa_id: int, numero: str) -> int:
        """Borra la conversación y la pausa de un cliente. Devuelve cuántos mensajes borró."""
        def borrar(con):
            n = con.execute("DELETE FROM mensajes WHERE empresa_id = %s AND numero = %s", (empresa_id, numero)).rowcount
            con.execute("DELETE FROM pausas WHERE empresa_id = %s AND numero = %s", (empresa_id, numero))
            return n
        return self._con(borrar)

    def _uno(self, sql, params=()):
        return self._con(lambda con: con.execute(sql, params).fetchone())

    def _todos(self, sql, params=()):
        return self._con(lambda con: con.execute(sql, params).fetchall())

    def _ejecutar(self, sql, params=()):
        self._con(lambda con: con.execute(sql, params))

    # ------------------------------------------------ empresas
    _SELECT_EMPRESA = "SELECT id, slug, nombre, estado, creada, actualizada, datos FROM empresas"

    def crear_empresa(self, nombre: str, slug: str, ahora: datetime, datos: dict | None = None) -> dict:
        from psycopg.errors import UniqueViolation
        from psycopg.types.json import Jsonb

        try:
            fila = self._uno(
                "INSERT INTO empresas (slug, nombre, estado, creada, actualizada, datos) "
                "VALUES (%s, %s, 'borrador', %s, %s, %s) "
                "RETURNING id, slug, nombre, estado, creada, actualizada, datos",
                (slug, nombre, ahora, ahora, Jsonb(datos or {})),
            )
        except UniqueViolation:
            raise ValueError(f"Ya existe una empresa con el slug {slug}") from None
        return _empresa_de_fila(fila)

    def empresa(self, empresa_id: int) -> dict | None:
        fila = self._uno(self._SELECT_EMPRESA + " WHERE id = %s", (empresa_id,))
        return _empresa_de_fila(fila) if fila else None

    def empresa_por_slug(self, slug: str) -> dict | None:
        fila = self._uno(self._SELECT_EMPRESA + " WHERE slug = %s", (slug,))
        return _empresa_de_fila(fila) if fila else None

    def empresas(self) -> list[dict]:
        return [_empresa_de_fila(f) for f in self._todos(self._SELECT_EMPRESA + " ORDER BY id")]

    def actualizar_empresa(self, empresa_id: int, cambios: dict, ahora: datetime) -> dict:
        from psycopg.types.json import Jsonb

        columnas = {k: v for k, v in cambios.items() if k in COLUMNAS_EMPRESA}
        datos = {k: v for k, v in cambios.items() if k not in COLUMNAS_EMPRESA}
        sets = [f"{k} = %s" for k in columnas] + ["datos = datos || %s", "actualizada = %s"]
        fila = self._uno(
            f"UPDATE empresas SET {', '.join(sets)} WHERE id = %s "
            "RETURNING id, slug, nombre, estado, creada, actualizada, datos",
            (*columnas.values(), Jsonb(datos), ahora, empresa_id),
        )
        return _empresa_de_fila(fila)

    # ------------------------------------------------ enlaces de alta
    def crear_invitacion(self, token_hash: str, empresa_id: int, vence: datetime, ahora: datetime) -> None:
        self._ejecutar("INSERT INTO invitaciones (token_hash, empresa_id, creada, vence) VALUES (%s, %s, %s, %s)",
                       (token_hash, empresa_id, ahora, vence))

    def invitacion(self, token_hash: str) -> dict | None:
        fila = self._uno("SELECT token_hash, empresa_id, creada, vence, usada FROM invitaciones WHERE token_hash = %s",
                         (token_hash,))
        if not fila:
            return None
        return dict(zip(("token_hash", "empresa_id", "creada", "vence", "usada"), fila))

    def usar_invitacion(self, token_hash: str, ahora: datetime) -> None:
        self._ejecutar("UPDATE invitaciones SET usada = %s WHERE token_hash = %s", (ahora, token_hash))

    # ------------------------------------------------ conversacion
    def es_nuevo(self, empresa_id: int, mensaje_id: str, ahora: datetime) -> bool:
        fila = self._uno(
            "INSERT INTO mensajes_atendidos (empresa_id, id, creado) VALUES (%s, %s, %s) "
            "ON CONFLICT (empresa_id, id) DO NOTHING RETURNING id",
            (empresa_id, mensaje_id, ahora),
        )
        return fila is not None

    def historial(self, empresa_id: int, numero: str) -> list[dict]:
        filas = self._todos(
            "SELECT rol, texto FROM ("
            "  SELECT id, rol, texto FROM mensajes WHERE empresa_id = %s AND numero = %s ORDER BY id DESC LIMIT %s"
            ") ultimos ORDER BY id",
            (empresa_id, numero, self._max),
        )
        return [{"role": rol, "content": texto} for rol, texto in filas]

    def agregar(self, empresa_id: int, numero: str, rol: str, texto: str, ahora: datetime) -> None:
        self._ejecutar("INSERT INTO mensajes (empresa_id, numero, rol, texto, fecha) VALUES (%s, %s, %s, %s, %s)",
                       (empresa_id, numero, rol, texto, ahora))

    def pausado_hasta(self, empresa_id: int, numero: str) -> datetime | None:
        fila = self._uno("SELECT hasta FROM pausas WHERE empresa_id = %s AND numero = %s", (empresa_id, numero))
        return fila[0] if fila else None

    def pausar(self, empresa_id: int, numero: str, hasta: datetime) -> None:
        self._ejecutar(
            "INSERT INTO pausas (empresa_id, numero, hasta) VALUES (%s, %s, %s) "
            "ON CONFLICT (empresa_id, numero) DO UPDATE SET hasta = EXCLUDED.hasta",
            (empresa_id, numero, hasta),
        )

    # ------------------------------------------------ uso, actividad y eventos
    def sumar_uso(self, empresa_id: int, dia: date, entrada: int, salida: int) -> None:
        self._ejecutar(
            "INSERT INTO uso (empresa_id, dia, llamadas, entrada, salida) VALUES (%s, %s, 1, %s, %s) "
            "ON CONFLICT (empresa_id, dia) DO UPDATE SET llamadas = uso.llamadas + 1, "
            "entrada = uso.entrada + EXCLUDED.entrada, salida = uso.salida + EXCLUDED.salida",
            (empresa_id, dia, entrada, salida),
        )

    def uso(self, empresa_id: int, desde: date) -> list[dict]:
        filas = self._todos(
            "SELECT dia, llamadas, entrada, salida FROM uso WHERE empresa_id = %s AND dia >= %s ORDER BY dia",
            (empresa_id, desde),
        )
        return [dict(zip(("dia", "llamadas", "entrada", "salida"), f)) for f in filas]

    def marcar_actividad(self, empresa_id: int, tipo: str, ahora: datetime) -> None:
        self._ejecutar(
            "INSERT INTO actividad (empresa_id, tipo, fecha) VALUES (%s, %s, %s) "
            "ON CONFLICT (empresa_id, tipo) DO UPDATE SET fecha = EXCLUDED.fecha",
            (empresa_id, tipo, ahora),
        )

    def actividad(self, empresa_id: int) -> dict[str, datetime]:
        return dict(self._todos("SELECT tipo, fecha FROM actividad WHERE empresa_id = %s", (empresa_id,)))

    def registrar_evento(self, empresa_id: int, tipo: str, detalle: str, ahora: datetime) -> None:
        self._ejecutar("INSERT INTO eventos (empresa_id, tipo, detalle, fecha) VALUES (%s, %s, %s, %s)",
                       (empresa_id, tipo, detalle, ahora))

    def eventos(self, empresa_id: int, limite: int = 20) -> list[dict]:
        filas = self._todos(
            "SELECT id, empresa_id, tipo, detalle, fecha FROM eventos WHERE empresa_id = %s ORDER BY id DESC LIMIT %s",
            (empresa_id, limite),
        )
        return [dict(zip(("id", "empresa_id", "tipo", "detalle", "fecha"), f)) for f in filas]

    def contar_eventos(self, empresa_id: int, tipo: str, desde: datetime) -> int:
        return self._uno("SELECT count(*) FROM eventos WHERE empresa_id = %s AND tipo = %s AND fecha >= %s",
                         (empresa_id, tipo, desde))[0]


def crear_almacen(config):
    if config.database_url:
        log.info("Almacen: PostgreSQL")
        return AlmacenPostgres(config.database_url)
    log.warning("Sin DATABASE_URL: todo vive en memoria y se pierde al reiniciar (solo para probar en tu PC).")
    return AlmacenMemoria()
