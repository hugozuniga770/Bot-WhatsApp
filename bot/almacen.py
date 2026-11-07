"""Donde se guarda el estado del bot.

Hay dos almacenes con los mismos metodos:
- AlmacenMemoria: para los tests y para probar en tu PC. Se borra al reiniciar.
- AlmacenMongo: para produccion (MongoDB Atlas). Sobrevive a reinicios de Render.
"""
import logging
import threading
from datetime import datetime

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

log = logging.getLogger(__name__)

SIETE_DIAS = 7 * 24 * 3600


class AlmacenMemoria:
    def __init__(self, max_guardados: int = 100):
        self._lock = threading.Lock()
        self._mensajes: dict[str, list[dict]] = {}
        self._pausas: dict[str, datetime] = {}
        self._atendidos: dict[str, datetime] = {}
        self._max = max_guardados

    def es_nuevo(self, mensaje_id: str, ahora: datetime) -> bool:
        """True la primera vez que se ve un mensaje; False si Meta lo reenvia."""
        with self._lock:
            if mensaje_id in self._atendidos:
                return False
            self._atendidos[mensaje_id] = ahora
            if len(self._atendidos) > 5000:
                self._atendidos.pop(next(iter(self._atendidos)))
            return True

    def historial(self, numero: str) -> list[dict]:
        with self._lock:
            return [dict(m) for m in self._mensajes.get(numero, [])]

    def agregar(self, numero: str, rol: str, texto: str, ahora: datetime) -> None:
        with self._lock:
            lista = self._mensajes.setdefault(numero, [])
            lista.append({"role": rol, "content": texto})
            del lista[:-self._max]

    def pausado_hasta(self, numero: str) -> datetime | None:
        with self._lock:
            return self._pausas.get(numero)

    def pausar(self, numero: str, hasta: datetime) -> None:
        with self._lock:
            self._pausas[numero] = hasta


class AlmacenMongo:
    """Colecciones:
    - conversaciones: un documento por cliente (_id = numero), con sus
      ultimos mensajes y, si corresponde, hasta cuando esta en pausa.
    - mensajes_atendidos: ids de mensajes ya procesados; se borran solos
      a los 7 dias (indice TTL).
    """

    def __init__(self, uri: str, base: str = "bot_whatsapp", max_guardados: int = 100, cliente=None):
        self._cliente = cliente or MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=8000)
        db = self._cliente[base]
        self._chats = db["conversaciones"]
        self._atendidos = db["mensajes_atendidos"]
        self._atendidos.create_index("creado", expireAfterSeconds=SIETE_DIAS)
        self._max = max_guardados

    def es_nuevo(self, mensaje_id: str, ahora: datetime) -> bool:
        try:
            self._atendidos.insert_one({"_id": mensaje_id, "creado": ahora})
            return True
        except DuplicateKeyError:
            return False

    def historial(self, numero: str) -> list[dict]:
        doc = self._chats.find_one({"_id": numero}, {"mensajes": 1}) or {}
        return [{"role": m["rol"], "content": m["texto"]} for m in doc.get("mensajes", [])]

    def agregar(self, numero: str, rol: str, texto: str, ahora: datetime) -> None:
        self._chats.update_one(
            {"_id": numero},
            {
                "$push": {"mensajes": {"$each": [{"rol": rol, "texto": texto, "fecha": ahora}], "$slice": -self._max}},
                "$set": {"actualizado": ahora},
            },
            upsert=True,
        )

    def pausado_hasta(self, numero: str) -> datetime | None:
        doc = self._chats.find_one({"_id": numero}, {"pausado_hasta": 1}) or {}
        return doc.get("pausado_hasta")

    def pausar(self, numero: str, hasta: datetime) -> None:
        self._chats.update_one({"_id": numero}, {"$set": {"pausado_hasta": hasta}}, upsert=True)


def crear_almacen(config):
    if config.mongodb_uri:
        log.info("Almacen: MongoDB (base %s)", config.mongodb_base)
        return AlmacenMongo(config.mongodb_uri, config.mongodb_base)
    log.warning("Sin MONGODB_URI: el historial y las pausas viven en memoria y se pierden al reiniciar.")
    return AlmacenMemoria()
