# Pruebas y trazabilidad

- Proyecto: Bot de WhatsApp con Claude (negocio de mi mamá) · Responsable: Hugo Zúñiga
- Fecha: 07/11/2026
- Requisitos: [README, sección 1](../README.md#1-qué-hace) · Arquitectura: [arquitectura.md](arquitectura.md)

## 1. Cómo se ejecutan

```powershell
python -m pytest -v
```

No hacen falta llaves, internet ni MongoDB. `tests/conftest.py` reemplaza WhatsApp y Claude por dobles (`WhatsAppFalso`, `AsistenteFalso`) que anotan lo que reciben, usa `AlmacenMemoria` y fija la hora en el 07/11/2026 a las 20:00 UTC. Cada test tiene comentarios Dado / Cuando / Entonces y lleva en su nombre el requisito que cubre.

## 2. Estado

| Corrida | Fecha | Resultado |
|---|---|---|
| Entorno donde Claude armó el proyecto (Linux, Python 3.12.3) | 07/11/2026 | **17 passed** in 0.05 s |
| Tu PC (Windows) | — | **Pendiente:** anota aquí el resultado |
| GitHub Actions (Python 3.13) | — | **Pendiente:** anota aquí el resultado y el enlace al run |

**Prueba de humo**, mismo entorno, 07/11/2026: con gunicorn y llaves falsas, `GET /` respondió 200, la verificación devolvió el `hub.challenge`, un `POST` sin firma recibió 403 y uno firmado recibió 200. El bot llamó a las APIs reales: Claude respondió 401 (llave falsa), el bot intentó enviar la disculpa y Meta respondió `code 190` (token falso). El error quedó en el log y el bot siguió funcionando.

## 3. Requisito → test

| Requisito | Test | Archivo | Estado |
|---|---|---|---|
| BOT-RF-01 | `test_RF01_responde_un_texto_con_el_asistente_y_guarda_ambos_mensajes` | `test_servicios.py` | Pasa |
| BOT-RF-02 | `test_RF02_el_asistente_recibe_la_conversacion_anterior` | `test_servicios.py` | Pasa |
| BOT-RF-02 | `test_RF02_historial_se_recorta_y_empieza_por_el_cliente` | `test_reglas.py` | Pasa |
| BOT-RF-03 | `test_RF03_audio_recibe_aviso_de_solo_texto_sin_llamar_al_asistente` | `test_servicios.py` | Pasa |
| BOT-RF-04 | `test_RF04_la_marca_deriva_a_la_duena_pausa_el_chat_y_no_se_envia_la_marca` | `test_servicios.py` | Pasa |
| BOT-RF-04 | `test_RF04_chat_en_pausa_no_recibe_respuesta` | `test_servicios.py` | Pasa |
| BOT-RF-04 | `test_RF04_al_vencer_la_pausa_el_bot_vuelve_a_responder` | `test_servicios.py` | Pasa |
| BOT-RF-05 | `test_RF05_mensaje_repetido_se_atiende_una_sola_vez` | `test_servicios.py` | Pasa |
| BOT-RF-06 | `test_RF06_si_falla_el_asistente_el_cliente_recibe_una_disculpa` | `test_servicios.py` | Pasa |
| BOT-RF-07 | `test_RF07_firma_correcta_se_acepta_y_alterada_se_rechaza` | `test_reglas.py` | Pasa |
| BOT-RF-07 | `test_RF07_webhook_sin_firma_valida_se_rechaza_y_no_responde` | `test_webhook.py` | Pasa |
| BOT-RF-07 | `test_RF07_webhook_firmado_se_atiende` | `test_webhook.py` | Pasa |
| BOT-RF-08 | `test_RF08_verificacion_con_token_correcto_devuelve_el_challenge` | `test_webhook.py` | Pasa |
| BOT-RF-08 | `test_RF08_verificacion_con_token_incorrecto_se_rechaza` | `test_webhook.py` | Pasa |
| BOT-RF-09 | `test_RF09_extrae_mensajes_e_ignora_estados_de_entrega` | `test_reglas.py` | Pasa |
| BOT-RF-10 | `test_RF10_config_incompleta_avisa_que_variables_faltan` | `test_config.py` | Pasa |
| BOT-RF-10 | `test_RF10_config_completa_lee_el_manual_y_los_valores_por_defecto` | `test_config.py` | Pasa |

"Pasa" se refiere a la corrida del entorno de armado. Cuando corras en tu PC y en Actions, actualiza la sección 2.

## 4. Lo que no se prueba (declarado)

- **`AlmacenMongo`**: no tiene test automático; se comprueba a mano en el [paso 6 del despliegue](despliegue.md#paso-6-prueba-de-punta-a-punta).
- **Las llamadas reales a Meta y a Claude**: solo la prueba de humo con llaves falsas; la prueba real es el paso 6.
- **La calidad de las respuestas de Claude**: depende del manual; se revisa leyendo conversaciones reales los primeros días.
- **Dos mensajes del mismo cliente en el mismo instante**: hay un candado por cliente, pero no hay test de concurrencia.
- **El aviso a la dueña fuera de la ventana de 24 h**: falla por regla de Meta (README, sección 9).
