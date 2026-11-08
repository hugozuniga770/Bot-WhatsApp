"""Manual de cada empresa (bot/manual.py). Requisitos BOT-RF-01 y 12."""
from bot.config import RAIZ
from bot.manual import componer

PLANTILLA = (RAIZ / "instrucciones.md").read_text(encoding="utf-8")


def test_RF12_cada_empresa_tiene_su_manual_con_sus_datos():
    # Dada una empresa con algunos datos del negocio
    empresa = {"nombre": "Boutique Las Palmas", "dueno_nombre": "Rosa", "trato": "tu",
               "info": {"horario": "Lunes a sábado de 9 a 19"}, "instrucciones_extra": "Saluda con buenos días."}
    # Cuando se arma su manual
    manual = componer(PLANTILLA, empresa)
    # Entonces lleva su nombre, su horario, el trato, sus indicaciones y la marca de derivación
    assert "Boutique Las Palmas" in manual and "Lunes a sábado de 9 a 19" in manual
    assert "de tú" in manual and "Saluda con buenos días." in manual
    assert "[PASAR_A_HUMANO]" in manual and "$" not in manual
    # Y lo que no se llenó le dice al bot que no invente
    assert "Sin información. Si preguntan, di que Rosa le confirmará." in manual
