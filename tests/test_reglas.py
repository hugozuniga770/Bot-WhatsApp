"""Reglas puras (bot/reglas.py)."""
import hashlib
import hmac
from datetime import date, datetime, timedelta, timezone

from bot import reglas


def test_RF02_historial_se_recorta_y_empieza_por_el_cliente():
    # Dado un historial largo cuyo recorte empezaría con una respuesta del bot
    historial = [{"role": r, "content": str(i)} for i, r in enumerate(["user", "assistant"] * 5)]
    # Cuando se recorta a los últimos 5 mensajes
    recorte = reglas.recortar_historial(historial, 5)
    # Entonces quedan 4: se descarta la respuesta suelta del inicio
    assert [m["role"] for m in recorte] == ["user", "assistant", "user", "assistant"]


def test_RF07_firma_correcta_se_acepta_y_alterada_se_rechaza():
    # Dado un cuerpo firmado con el App Secret
    cuerpo = b'{"entry": []}'
    firma = "sha256=" + hmac.new(b"secreto", cuerpo, hashlib.sha256).hexdigest()
    # Cuando se verifica con el mismo secreto, con un cuerpo alterado y sin firma
    # Entonces solo la primera se acepta
    assert reglas.firma_valida(cuerpo, firma, "secreto")
    assert not reglas.firma_valida(b'{"entry": [1]}', firma, "secreto")
    assert not reglas.firma_valida(cuerpo, None, "secreto")
    assert not reglas.firma_valida(cuerpo, firma, "")


def test_RF09_extrae_mensajes_e_ignora_estados_de_entrega(payload):
    # Dado un aviso de Meta con un texto, una imagen y un estado "leído"
    datos = payload(
        {"id": "wamid.1", "from": "591700", "type": "text", "text": {"body": "  Hola  "}},
        {"id": "wamid.2", "from": "591700", "type": "image", "image": {"id": "x"}},
        estados=[{"id": "wamid.0", "status": "read"}],
    )
    # Cuando se extraen los mensajes
    # Entonces salen solo los dos mensajes, y el texto llega limpio
    assert [(m.id, m.tipo, m.texto) for m in reglas.extraer_mensajes(datos)] == [
        ("wamid.1", "text", "Hola"), ("wamid.2", "image", "")]


def test_RF17_estima_saldo_y_dias_con_el_promedio_de_la_ultima_semana():
    # Dado USD 5 cargados hace 3 días y 1 millón de tokens de entrada por día con Haiku (USD 0.10/día)
    hoy = date(2026, 11, 7)
    uso = [{"dia": hoy - timedelta(days=i), "llamadas": 300, "entrada": 1_000_000, "salida": 0} for i in range(3)]
    # Cuando se resume el crédito
    r = reglas.resumen_credito(5, hoy - timedelta(days=2), uso, hoy, 0.10, 0.50)
    # Entonces quedan 4.70 y alcanzan 47 días, hasta el 24/12
    assert round(r["restante"], 2) == 4.70
    assert (r["dias"], r["hasta"], r["estado"]) == (47, date(2026, 12, 24), "ok")


def test_RF17_avisa_cuando_queda_poco_o_se_agoto():
    hoy = date(2026, 11, 7)
    uso = [{"dia": hoy, "llamadas": 1, "entrada": 1_000_000, "salida": 1_000_000}]  # USD 0.60 hoy
    # Dado un saldo que alcanza para menos de una semana, y otro que ya se gastó
    # Entonces el primero queda en "poco" y el segundo en "agotado"
    assert reglas.resumen_credito(3, hoy, uso, hoy, 0.10, 0.50)["estado"] == "poco"
    assert reglas.resumen_credito(0.5, hoy, uso, hoy, 0.10, 0.50)["estado"] == "agotado"
    assert reglas.resumen_credito(None, None, uso, hoy, 0.10, 0.50)["estado"] == "sin_saldo"
    assert reglas.resumen_credito(5, hoy, [], hoy, 0.10, 0.50)["estado"] == "sin_uso"


def test_RF17_serie_diaria_rellena_los_dias_sin_uso():
    # Dado uso solo hoy
    hoy = date(2026, 11, 7)
    serie = reglas.serie_diaria([{"dia": hoy, "llamadas": 2, "entrada": 900, "salida": 100}], hoy, 14, 0.10, 0.50)
    # Entonces hay 14 días, 13 en cero, y hoy es la barra más alta
    assert len(serie) == 14 and serie[0]["dia"] == hoy - timedelta(days=13)
    assert [s["tokens"] for s in serie[:-1]] == [0] * 13
    assert (serie[-1]["tokens"], serie[-1]["altura"]) == (1000, 100)


def test_RF17_el_dia_se_cuenta_en_la_hora_de_bolivia():
    # Dado un mensaje a las 02:00 UTC del 8 de noviembre (22:00 del 7 en Bolivia)
    momento = datetime(2026, 11, 8, 2, 0, tzinfo=timezone.utc)
    # Entonces cuenta para el 7
    assert reglas.dia_local(momento, "America/La_Paz") == date(2026, 11, 7)


def test_RF15_los_formatos_incorrectos_se_explican_en_palabras_simples():
    # Dados datos con forma equivocada
    errores = reglas.errores_de_formato({
        "anthropic_key": "hola", "meta_app_id": "12ab", "meta_app_secret": "corto",
        "whatsapp_token": "EAA corto", "dueno_numero": "123", "saldo_usd": "cinco"})
    # Entonces cada uno tiene su explicación
    assert set(errores) == {"anthropic_key", "meta_app_id", "meta_app_secret", "whatsapp_token", "dueno_numero", "saldo_usd"}
    # Y los datos bien formados no dan errores
    assert reglas.errores_de_formato({"anthropic_key": "sk-ant-abc", "meta_app_id": "1234567",
                                      "meta_app_secret": "a" * 32, "dueno_numero": "59170000000"}) == {}


def test_RF12_slug_y_numeros_se_normalizan():
    assert reglas.crear_slug("Sentirse Única S.R.L.") == "sentirse-unica-s-r-l"
    assert reglas.normalizar_numero("+591 750-13150") == "59175013150"
    assert reglas.lista_de_numeros("+591 7000 0001, 59170000002\n") == {"59170000001", "59170000002"}
