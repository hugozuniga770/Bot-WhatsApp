"""Configuracion (bot/config.py). Requisito BOT-RF-10."""
import pytest

from bot.config import ConfigIncompleta, cargar


def test_RF10_config_incompleta_avisa_que_variables_faltan():
    # Dado un entorno sin la clave maestra ni la contraseña del panel
    # Cuando se carga la configuración
    # Entonces se detiene nombrando exactamente lo que falta
    with pytest.raises(ConfigIncompleta, match="CLAVE_MAESTRA, ADMIN_PASSWORD"):
        cargar({"DATABASE_URL": "postgresql://x"})


def test_RF10_contrasena_corta_no_se_acepta():
    with pytest.raises(ConfigIncompleta, match="ADMIN_PASSWORD"):
        cargar({"CLAVE_MAESTRA": "x" * 20, "ADMIN_PASSWORD": "1234"})


def test_RF10_en_render_usa_su_url_y_cookies_seguras():
    # Dado el entorno que pone Render
    config = cargar({"CLAVE_MAESTRA": "x" * 20, "ADMIN_PASSWORD": "una-contraseña-larga",
                     "RENDER": "true", "RENDER_EXTERNAL_URL": "https://bots.onrender.com/"})
    # Entonces toma la URL pública, activa cookies seguras y deriva la clave de sesión
    assert config.url_publica == "https://bots.onrender.com"
    assert config.cookie_segura and len(config.secret_key) == 64
