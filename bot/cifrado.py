"""Cifrado de las llaves que se guardan en la base (BOT-RF-13).

Las llaves de cada empresa (Claude, Meta) se guardan cifradas con una clave
maestra que solo existe en las variables de Render (CLAVE_MAESTRA). Si alguien
copia la base de datos, sin esa clave no puede leer ninguna llave.

OJO: si la CLAVE_MAESTRA cambia, las llaves guardadas ya no se pueden leer y
hay que volver a cargarlas. Guárdala en un lugar seguro.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class ClaveIncorrecta(Exception):
    """Un dato cifrado no se pudo leer con la CLAVE_MAESTRA actual."""


class Cifrador:
    def __init__(self, clave_maestra: str):
        if not clave_maestra or len(clave_maestra) < 16:
            raise ValueError("La CLAVE_MAESTRA debe tener al menos 16 caracteres.")
        # Cualquier texto largo sirve: se convierte en una clave Fernet valida.
        clave = base64.urlsafe_b64encode(hashlib.sha256(clave_maestra.encode()).digest())
        self._fernet = Fernet(clave)

    def cifrar(self, texto: str) -> str:
        return self._fernet.encrypt(texto.encode()).decode() if texto else ""

    def descifrar(self, cifrado: str) -> str:
        if not cifrado:
            return ""
        try:
            return self._fernet.decrypt(cifrado.encode()).decode()
        except InvalidToken:
            raise ClaveIncorrecta(
                "No se pudo leer una llave guardada: la CLAVE_MAESTRA cambió. Vuelve a cargar las llaves de esa empresa."
            ) from None
