"""Llaves cifradas (bot/cifrado.py). Requisito BOT-RF-13."""
import pytest

from bot.cifrado import Cifrador, ClaveIncorrecta
from bot.reglas import enmascarar


def test_RF13_una_llave_cifrada_no_se_ve_y_se_recupera_con_la_misma_clave():
    # Dada una llave cifrada con la clave maestra
    c = Cifrador("clave-maestra-larga-123")
    cifrada = c.cifrar("sk-ant-secreta")
    # Entonces el texto guardado no contiene la llave, y con la misma clave se recupera
    assert "sk-ant" not in cifrada
    assert c.descifrar(cifrada) == "sk-ant-secreta"


def test_RF13_con_otra_clave_maestra_no_se_puede_leer():
    # Dada una llave cifrada con una clave maestra
    cifrada = Cifrador("clave-maestra-larga-123").cifrar("sk-ant-secreta")
    # Cuando se intenta leer con otra
    # Entonces falla con un mensaje claro
    with pytest.raises(ClaveIncorrecta, match="CLAVE_MAESTRA"):
        Cifrador("otra-clave-maestra-456").descifrar(cifrada)


def test_RF13_las_llaves_se_muestran_enmascaradas():
    assert enmascarar("sk-ant-api03-abcdefghij1234") == "sk-ant-…1234"
    assert enmascarar("") == ""
