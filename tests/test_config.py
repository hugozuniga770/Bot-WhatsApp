"""Configuracion (bot/config.py). Requisito BOT-RF-10."""
import pytest

from bot.config import ConfigIncompleta, cargar


def test_RF10_config_incompleta_avisa_que_variables_faltan():
    # Dado un entorno al que le faltan la llave de Claude y el App Secret
    entorno = {"WHATSAPP_TOKEN": "t", "PHONE_NUMBER_ID": "1", "VERIFY_TOKEN": "v"}
    # Cuando se carga la configuración
    # Entonces se detiene nombrando exactamente lo que falta
    with pytest.raises(ConfigIncompleta, match="ANTHROPIC_API_KEY, APP_SECRET"):
        cargar(entorno)


def test_RF10_config_completa_lee_el_manual_y_los_valores_por_defecto(tmp_path):
    # Dado un entorno completo y un manual
    manual = tmp_path / "manual.md"
    manual.write_text("Eres el asistente", encoding="utf-8")
    entorno = {"ANTHROPIC_API_KEY": "k", "WHATSAPP_TOKEN": "t", "PHONE_NUMBER_ID": "1",
               "VERIFY_TOKEN": "v", "APP_SECRET": "s", "INSTRUCCIONES_ARCHIVO": str(manual)}
    # Cuando se carga la configuración
    config = cargar(entorno)
    # Entonces trae el manual y los valores por defecto
    assert config.instrucciones == "Eres el asistente"
    assert (config.limite_historial, config.pausa_horas, config.mongodb_uri) == (20, 12.0, "")
