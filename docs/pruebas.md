# Pruebas y trazabilidad

- Proyecto: Bots de WhatsApp con Claude · Responsable: Hugo Zúñiga
- Fecha: 08/11/2026 · Versión: v2.0
- Requisitos: [README, sección 1](../README.md#1-qué-hace) · Arquitectura: [arquitectura.md](arquitectura.md)

## 1. Cómo se ejecutan

```powershell
python -m pytest -v
```

No hacen falta llaves ni internet. `tests/conftest.py` reemplaza a Meta, a Claude y al verificador por dobles (`WhatsAppFalso`, `AsistenteFalso`, `VerificadorFalso`) que anotan lo que reciben, y fija la hora en el 07/11/2026 a las 20:00 UTC. Cada test tiene comentarios Dado / Cuando / Entonces y lleva en su nombre el requisito que cubre.

Los tests de `test_verificaciones.py` imitan las respuestas reales de Claude y de Meta: los mismos códigos de error (401, 400 por saldo, 190) y la misma forma del JSON.

Los tests del almacén (`test_almacen.py`) son un **contrato** (D-12): cada uno corre con `AlmacenMemoria` y con `AlmacenPostgres`. Los de Postgres necesitan `TEST_DATABASE_URL`:

- **En tu PC**, sin esa variable, salen **60 passed, 9 skipped**.
- **En el CI**, un PostgreSQL 17 temporal; salen **69 passed**, y el CI falla si alguno se salta.
- **Para correrlos en tu PC**, usa una base **de prueba**: los tests vacían las tablas. **Nunca la de producción.**

## 2. Estado

| Corrida | Fecha | Resultado |
|---|---|---|
| v2.0 · entorno de armado, sin base | 08/11/2026 | **60 passed, 9 skipped** |
| v2.0 · entorno de armado, con PostgreSQL 16 real | 08/11/2026 | **69 passed**, 0 saltadas |
| v2.0 · recorrido en navegador de celular (390 px) con gunicorn + PostgreSQL | 08/11/2026 | Ver sección 3 |
| v2.0 · tu PC (Windows) | — | **Pendiente:** anota aquí el resultado |
| v2.0 · GitHub Actions (Python 3.13, PostgreSQL 17) | — | **Pendiente:** anota aquí el resultado y el enlace al run |
| v1.0 · GitHub Actions | 07/11/2026 | En verde (17 passed), según Hugo |

## 3. Recorrido de punta a punta (08/11/2026)

Se arrancó el servicio con gunicorn, PostgreSQL 16 y solo las variables obligatorias, y se recorrió con un navegador Chromium en tamaño de celular, con llaves falsas pero bien formadas. Cada paso dio lo esperado:

1. En el panel se creó "Ferretería Don Lucho" y se obtuvo el enlace de alta.
2. En el enlace se llenaron los 6 pasos.
   - Al avanzar con datos obligatorios vacíos, cada uno queda marcado ("Este dato hace falta para seguir").
   - "Probar la llave" **llamó de verdad a la API de Claude** y mostró "La llave no es válida…".
3. Una petición igual a la de Meta verificó el webhook: respondió `200` con el challenge. El paso 5 cambió solo a **Conectado**.
4. Al enviar el formulario se llegó a "¡Listo! Recibimos tus datos", y la empresa quedó **En prueba**.
5. **Verificar todo** consultó de verdad a Claude y a Meta: 3 fallas explicadas (llave, token, App Secret) y el webhook en verde.
6. **Activar para todos** se bloqueó: "Antes de activar, verifica la empresa y resuelve lo que falle".
7. Un mensaje firmado del dueño al webhook respondió `200`. El bot intentó responder: Claude devolvió 401 y Meta, 190. El error quedó en **Actividad** y el servicio siguió funcionando.
8. La lista y el detalle se vieron en modo claro y oscuro.

**La consola del navegador no tuvo errores.** Si la base no responde al arrancar, el servicio se detiene en vez de quedar a medias. En la v1.x también se probó cortar a mano las conexiones de la base: el pool reconecta solo.

## 4. Requisito → test

Requisitos cubiertos: RF-01, RF-02, RF-03, RF-04, RF-05, RF-06, RF-07, RF-08, RF-09, RF-10, RF-11, RF-12, RF-13, RF-14, RF-15, RF-16, RF-17, RF-18, RF-19.

| Requisito | Test | Archivo | Estado |
|---|---|---|---|
| BOT-RF-01 | `test_RF01_responde_un_texto_con_el_asistente_y_guarda_ambos_mensajes` | `test_servicios.py` | Pasa |
| BOT-RF-02 | `test_RF02_el_asistente_recibe_la_conversacion_anterior` | `test_servicios.py` | Pasa |
| BOT-RF-02 | `test_RF02_historial_se_recorta_y_empieza_por_el_cliente` | `test_reglas.py` | Pasa |
| BOT-RF-03 | `test_RF03_audio_recibe_aviso_de_solo_texto_sin_llamar_al_asistente` | `test_servicios.py` | Pasa |
| BOT-RF-04 | `test_RF04_chat_en_pausa_no_recibe_respuesta_hasta_que_vence` | `test_servicios.py` | Pasa |
| BOT-RF-04 | `test_RF04_la_marca_deriva_al_dueno_pausa_el_chat_y_no_se_envia_la_marca` | `test_servicios.py` | Pasa |
| BOT-RF-05 | `test_RF05_mensaje_repetido_se_atiende_una_sola_vez` | `test_servicios.py` | Pasa |
| BOT-RF-06 | `test_RF06_si_falla_el_asistente_el_cliente_recibe_una_disculpa_y_queda_registrado` | `test_servicios.py` | Pasa |
| BOT-RF-07 | `test_RF07_firma_correcta_se_acepta_y_alterada_se_rechaza` | `test_reglas.py` | Pasa |
| BOT-RF-07 | `test_RF07_sin_firma_o_con_el_secreto_de_otra_empresa_se_rechaza` | `test_webhook.py` | Pasa |
| BOT-RF-07 | `test_RF07_webhook_firmado_con_el_secreto_de_la_empresa_se_atiende` | `test_webhook.py` | Pasa |
| BOT-RF-08 | `test_RF08_token_incorrecto_o_empresa_inexistente_se_rechaza` | `test_webhook.py` | Pasa |
| BOT-RF-08 | `test_RF08_verificacion_con_el_token_de_la_empresa_devuelve_el_challenge` | `test_webhook.py` | Pasa |
| BOT-RF-09 | `test_RF09_extrae_mensajes_e_ignora_estados_de_entrega` | `test_reglas.py` | Pasa |
| BOT-RF-10 | `test_RF10_config_incompleta_avisa_que_variables_faltan` | `test_config.py` | Pasa |
| BOT-RF-10 | `test_RF10_contrasena_corta_no_se_acepta` | `test_config.py` | Pasa |
| BOT-RF-10 | `test_RF10_en_render_usa_su_url_y_cookies_seguras` | `test_config.py` | Pasa |
| BOT-RF-11 | `test_RF11_el_estado_sobrevive_a_un_reinicio` (solo postgres) | `test_almacen.py` | Pasa |
| BOT-RF-11 | `test_RF11_el_historial_devuelve_los_ultimos_en_orden` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-11 | `test_RF11_la_pausa_se_guarda_y_se_puede_extender` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-12 | `test_RF12_cada_empresa_tiene_su_manual_con_sus_datos` | `test_manual.py` | Pasa |
| BOT-RF-12 | `test_RF12_las_conversaciones_de_dos_empresas_no_se_mezclan` | `test_servicios.py` | Pasa |
| BOT-RF-12 | `test_RF12_las_conversaciones_y_pausas_de_cada_empresa_estan_separadas` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-12 | `test_RF12_no_puede_haber_dos_empresas_con_el_mismo_slug` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-12 | `test_RF12_slug_y_numeros_se_normalizan` | `test_reglas.py` | Pasa |
| BOT-RF-12 | `test_RF12_una_empresa_se_crea_en_borrador_y_se_actualiza_por_partes` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-13 | `test_RF13_con_otra_clave_maestra_no_se_puede_leer` | `test_cifrado.py` | Pasa |
| BOT-RF-13 | `test_RF13_el_detalle_nunca_muestra_las_llaves_completas` | `test_panel.py` | Pasa |
| BOT-RF-13 | `test_RF13_las_llaves_se_muestran_enmascaradas` | `test_cifrado.py` | Pasa |
| BOT-RF-13 | `test_RF13_una_llave_cifrada_no_se_ve_y_se_recupera_con_la_misma_clave` | `test_cifrado.py` | Pasa |
| BOT-RF-14 | `test_RF14_contrasena_incorrecta_no_entra_y_se_bloquea_tras_5_intentos` | `test_panel.py` | Pasa |
| BOT-RF-14 | `test_RF14_el_panel_pide_contrasena` | `test_panel.py` | Pasa |
| BOT-RF-14 | `test_RF14_un_formulario_sin_csrf_se_rechaza` | `test_panel.py` | Pasa |
| BOT-RF-15 | `test_RF15_crear_una_empresa_da_un_enlace_para_compartir_por_whatsapp` | `test_panel.py` | Pasa |
| BOT-RF-15 | `test_RF15_el_dueno_llena_el_enlace_y_la_empresa_queda_en_prueba_con_llaves_cifradas` | `test_panel.py` | Pasa |
| BOT-RF-15 | `test_RF15_el_enlace_de_alta_se_guarda_y_se_marca_usado` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-15 | `test_RF15_los_formatos_incorrectos_se_explican_en_palabras_simples` | `test_reglas.py` | Pasa |
| BOT-RF-15 | `test_RF15_si_faltan_datos_se_explica_cada_uno_y_no_se_guarda` | `test_panel.py` | Pasa |
| BOT-RF-15 | `test_RF15_un_enlace_vencido_no_sirve` | `test_panel.py` | Pasa |
| BOT-RF-16 | `test_RF16_actividad_y_eventos_quedan_registrados` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-16 | `test_RF16_el_mensaje_de_prueba_explica_la_regla_de_las_24_horas` | `test_panel.py` | Pasa |
| BOT-RF-16 | `test_RF16_el_webhook_y_el_estado_general` | `test_verificaciones.py` | Pasa |
| BOT-RF-16 | `test_RF16_en_el_enlace_se_puede_probar_la_llave_antes_de_enviar` | `test_panel.py` | Pasa |
| BOT-RF-16 | `test_RF16_llave_de_claude_invalida_o_sin_creditos_se_explica` | `test_verificaciones.py` | Pasa |
| BOT-RF-16 | `test_RF16_llave_de_claude_que_funciona` | `test_verificaciones.py` | Pasa |
| BOT-RF-16 | `test_RF16_no_se_puede_activar_sin_verificar` | `test_panel.py` | Pasa |
| BOT-RF-16 | `test_RF16_numero_y_token_de_meta_correctos` | `test_verificaciones.py` | Pasa |
| BOT-RF-16 | `test_RF16_si_la_verificacion_falla_se_muestra_y_no_se_activa` | `test_panel.py` | Pasa |
| BOT-RF-16 | `test_RF16_token_temporal_y_calidad_baja_dan_atencion` | `test_verificaciones.py` | Pasa |
| BOT-RF-16 | `test_RF16_token_vencido_o_app_secret_equivocado_se_explican` | `test_verificaciones.py` | Pasa |
| BOT-RF-16 | `test_RF16_verificar_guarda_el_resultado_y_permite_activar` | `test_panel.py` | Pasa |
| BOT-RF-17 | `test_RF17_avisa_cuando_queda_poco_o_se_agoto` | `test_reglas.py` | Pasa |
| BOT-RF-17 | `test_RF17_cada_respuesta_suma_sus_tokens_al_dia_de_bolivia` | `test_servicios.py` | Pasa |
| BOT-RF-17 | `test_RF17_el_detalle_muestra_cuantos_dias_de_credito_quedan` | `test_panel.py` | Pasa |
| BOT-RF-17 | `test_RF17_el_dia_se_cuenta_en_la_hora_de_bolivia` | `test_reglas.py` | Pasa |
| BOT-RF-17 | `test_RF17_el_uso_se_suma_por_dia` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-17 | `test_RF17_estima_saldo_y_dias_con_el_promedio_de_la_ultima_semana` | `test_reglas.py` | Pasa |
| BOT-RF-17 | `test_RF17_serie_diaria_rellena_los_dias_sin_uso` | `test_reglas.py` | Pasa |
| BOT-RF-18 | `test_RF18_en_prueba_solo_le_responde_al_dueno` | `test_servicios.py` | Pasa |
| BOT-RF-18 | `test_RF18_pausada_o_en_borrador_no_responde_a_nadie` | `test_servicios.py` | Pasa |
| BOT-RF-19 | `test_RF19_los_numeros_ignorados_no_reciben_respuesta` | `test_servicios.py` | Pasa |

"Pasa" se refiere a la corrida con PostgreSQL del entorno de armado. Cuando corras en tu PC y en Actions, actualiza la sección 2.

## 5. Lo que no se prueba (declarado)

- **Las llaves reales de Claude y de Meta:** las pruebas automáticas usan dobles. La prueba real son los pasos 4 a 6 del [despliegue](despliegue.md), con los botones **Probar** y **Verificar todo**.
- **Neon en sí:** los tests usan un PostgreSQL normal. Que la base de Neon funcione se comprueba en los pasos 1 y 2 del despliegue.
- **La calidad de las respuestas de Claude:** depende del manual. Se revisa leyendo conversaciones reales en la prueba en vivo (paso 5).
- **El JavaScript del formulario** (pasos, copiar, probar, estado del webhook): solo se probó en el recorrido de la sección 3, sin tests automáticos. Sin JavaScript, el formulario igual funciona.
- **Dos mensajes del mismo cliente en el mismo instante:** hay un candado por chat, pero no hay test de concurrencia.
- **El aviso al dueño fuera de la ventana de 24 h:** falla por regla de Meta (README, sección 9).
