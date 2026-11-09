# Pruebas y trazabilidad

- Proyecto: Bots de WhatsApp con Claude · Responsable: Hugo Zúñiga
- Fecha: 09/11/2026 · Versión: v3.4.2
- Requisitos: [README, sección 1](../README.md#1-qué-hace) · Arquitectura: [arquitectura.md](arquitectura.md)

## 1. Cómo se ejecutan

```powershell
python -m pytest -v
```

No hacen falta llaves ni internet. `tests/conftest.py` reemplaza a Meta, a Claude y al verificador por dobles (`WhatsAppFalso`, `AsistenteFalso`, `VerificadorFalso`) que anotan lo que reciben, y fija la hora en el 07/11/2026 a las 20:00 UTC. Cada test tiene comentarios Dado / Cuando / Entonces y lleva en su nombre el requisito que cubre.

Los tests de `test_verificaciones.py` imitan las respuestas reales de Claude y de Meta: los mismos códigos de error (401, 400 por saldo, 190) y la misma forma del JSON.

Los tests del almacén (`test_almacen.py`) son un **contrato** (D-12): cada uno corre con `AlmacenMemoria` y con `AlmacenPostgres`. Los de Postgres necesitan `TEST_DATABASE_URL`:

- **En tu PC**, sin esa variable, salen **104 passed, 16 skipped**.
- **En el CI**, un PostgreSQL 17 temporal; salen **120 passed**, y el CI falla si alguno se salta.
- **Para correrlos en tu PC**, usa una base **de prueba**: los tests vacían las tablas. **Nunca la de producción.**

## 2. Estado

| Corrida | Fecha | Resultado |
|---|---|---|
| v3.1.1 · entorno de armado, con PostgreSQL 16 real | 08/11/2026 | **144 passed**, 0 saltadas. La prueba de reservas simultáneas falla si se quita el candado (comprobado) |
| v3.1.1 · migración | 08/11/2026 | El esquema de la v3.1 aplicado sobre una base con el de la v3.0, dos veces seguidas, sin errores |
| v3.1.1 · GitHub Actions | — | **Pendiente** |
| v3.0 · entorno de armado, sin base | 08/11/2026 | **104 passed, 16 skipped** |
| v3.0 · entorno de armado, con PostgreSQL 16 real | 08/11/2026 | **120 passed**, 0 saltadas |
| v3.0 · recorrido en navegador de celular (390 px), modo claro y oscuro | 08/11/2026 | Entrar, semana, día, mes, detalle de cita y horario con datos de ejemplo; sin errores en la consola |
| v3.0 · GitHub Actions | — | **Pendiente** |
| v2.5 · entorno de armado, sin base | 08/11/2026 | **78 passed, 11 skipped** |
| v2.5 · entorno de armado, con PostgreSQL 16 real | 08/11/2026 | **89 passed**, 0 saltadas |
| v2.5 · GitHub Actions | — | Se sube junto con la v3.0 si no se subió antes |
| v2.4 · en vivo (Render + Meta + Claude) | 08/11/2026 | Hugo le escribió "Hola" al número de prueba (+1 555-046-3561) desde su celular y el bot respondió como Sentirse Única |
| v2.4 · GitHub Actions | 08/11/2026 | **82 passed** (run #6, commit d369a84); Render Live con ese commit |
| v2.4 · entorno de armado, sin base | 08/11/2026 | **71 passed, 11 skipped** |
| v2.4 · entorno de armado, con PostgreSQL 16 real | 08/11/2026 | **82 passed**, 0 saltadas |
| v2.3 · GitHub Actions | 08/11/2026 | **78 passed** (run #5, commit 31b1233); en Render, Sentirse Única guardada con Claude, número y token verificados |
| v2.3 · entorno de armado, sin base | 08/11/2026 | **68 passed, 10 skipped** |
| v2.3 · entorno de armado, con PostgreSQL 16 real | 08/11/2026 | **78 passed**, 0 saltadas |
| v2.2 · entorno de armado, sin base | 08/11/2026 | **65 passed, 10 skipped** |
| v2.2 · entorno de armado, con PostgreSQL 16 real | 08/11/2026 | **75 passed**, 0 saltadas |
| v2.1 · GitHub Actions | 08/11/2026 | **72 passed** (run #3, commit 4d9219a) |
| v2.1 · entorno de armado, sin base | 08/11/2026 | **63 passed, 9 skipped** |
| v2.0 · GitHub Actions (Python 3.13, PostgreSQL 17) | 08/11/2026 | **69 passed**, 0 saltadas (run #2, commit 6bdc7ec) |
| v2.0 · entorno de armado, sin base | 08/11/2026 | **60 passed, 9 skipped** |
| v2.0 · entorno de armado, con PostgreSQL 16 real | 08/11/2026 | **69 passed**, 0 saltadas |
| v2.0 · recorrido en navegador de celular (390 px) con gunicorn + PostgreSQL | 08/11/2026 | Ver sección 3 |
| v2.0 · tu PC (Windows) | — | **Pendiente:** anota aquí el resultado |
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

## 3c. Guardar con la base caída (v2.3, 08/11/2026)

Servicio en gunicorn con PostgreSQL 16 y navegador Chromium de celular:

| Momento | Resultado |
|---|---|
| Formulario abierto, llave pegada, base **apagada**, "Guardar cambios" | Aviso a los 0,1 s: "La base de datos no respondió, así que todavía no se guardó nada…". La página sigue siendo el formulario y la llave sigue pegada |
| Base **prendida**, "Guardar cambios" otra vez | Guardado al primer intento ("Cambios guardados") y la llave aparece enmascarada en el detalle |
| Conexiones cortadas por la base (como Neon al dormirse), luego `/salud/base` | 200: la consulta se repitió con una conexión nueva |

La consola del navegador no tuvo errores.

## 3b. Base que se cae y vuelve (v2.2, 08/11/2026; con psycopg-pool, reemplazado en v2.3)

Servicio en gunicorn con PostgreSQL 16:

| Momento | Resultado |
|---|---|
| Base arriba | Responde al instante |
| Base apagada | **503 en 15 s**, con "La base de datos no respondió" (antes: 500) |
| Primer pedido al volver la base | Responde en 7,4 s (el pool reconecta solo) |
| Segundo pedido | Responde al instante |

Un servidor que acepta la conexión y nunca contesta: con `connect_timeout`, el intento se corta en el tiempo fijado. Sin él, esperaría para siempre.

## 4. Requisito → test

Requisitos cubiertos (más RF-20, agregado en v2.4; RF-08 y RF-09 ampliados en v2.5; RF-21 a 25, agregados en v3.0): RF-01, RF-02, RF-03, RF-04, RF-05, RF-06, RF-07, RF-08, RF-09, RF-10, RF-11, RF-12, RF-13, RF-14, RF-15, RF-16, RF-17, RF-18, RF-19.

| Requisito | Test | Archivo | Estado |
|---|---|---|---|
| BOT-RF-01 | `test_RF01_el_bot_le_pide_a_haiku_sin_razonamiento_y_a_otros_modelos_sin_cambios` | `test_servicios.py` | Pasa |
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
| BOT-RF-08 | `test_RF08_cambiar_el_token_pide_la_contrasena_del_panel` | `test_panel.py` | Pasa |
| BOT-RF-08 | `test_RF08_el_admin_cambia_el_token_y_solo_el_nuevo_verifica` | `test_panel.py` | Pasa |
| BOT-RF-08 | `test_RF08_token_incorrecto_o_empresa_inexistente_se_rechaza` | `test_webhook.py` | Pasa |
| BOT-RF-08 | `test_RF08_verificacion_con_el_token_de_la_empresa_devuelve_el_challenge` | `test_webhook.py` | Pasa |
| BOT-RF-09 | `test_RF09_extrae_mensajes_e_ignora_estados_de_entrega` | `test_reglas.py` | Pasa |
| BOT-RF-09 | `test_RF09_los_avisos_de_falla_se_leen_con_su_motivo_y_los_demas_estados_no` | `test_reglas.py` | Pasa |
| BOT-RF-09 | `test_RF09_una_falla_con_un_codigo_desconocido_muestra_lo_que_dice_meta` | `test_reglas.py` | Pasa |
| BOT-RF-09 | `test_RF09_un_mensaje_no_entregado_queda_en_la_actividad_una_sola_vez` | `test_servicios.py` | Pasa |
| BOT-RF-09 | `test_RF09_meta_avisa_que_no_pudo_entregar_y_el_panel_lo_muestra` | `test_webhook.py` | Pasa |
| BOT-RF-10 | `test_RF10_config_incompleta_avisa_que_variables_faltan` | `test_config.py` | Pasa |
| BOT-RF-10 | `test_RF10_contrasena_corta_no_se_acepta` | `test_config.py` | Pasa |
| BOT-RF-10 | `test_RF10_en_render_usa_su_url_y_cookies_seguras` | `test_config.py` | Pasa |
| BOT-RF-11 | `test_RF11_si_la_base_corta_las_conexiones_el_almacen_sigue_funcionando` (solo postgres) | `test_almacen.py` | Pasa |
| BOT-RF-11 | `test_RF11_una_conexion_libre_se_reutiliza_y_una_vieja_se_reemplaza` | `test_almacen.py` | Pasa |
| BOT-RF-11 | `test_RF11_si_se_corta_una_conexion_se_reintenta_con_otra` | `test_almacen.py` | Pasa |
| BOT-RF-11 | `test_RF11_si_la_base_no_responde_dos_veces_se_avisa_claro` | `test_almacen.py` | Pasa |
| BOT-RF-11 | `test_RF11_salud_base_responde_si_la_base_funciona_y_503_si_no` | `test_panel.py` | Pasa |
| BOT-RF-11 | `test_RF11_si_la_base_no_responde_el_panel_lo_explica_y_meta_reintenta` | `test_panel.py` | Pasa |
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
| BOT-RF-16 | `test_RF16_si_meta_acepta_la_prueba_se_aclara_donde_ver_si_no_llego` | `test_panel.py` | Pasa |
| BOT-RF-16 | `test_RF16_el_webhook_y_el_estado_general` | `test_verificaciones.py` | Pasa |
| BOT-RF-16 | `test_RF16_en_el_enlace_se_puede_probar_la_llave_antes_de_enviar` | `test_panel.py` | Pasa |
| BOT-RF-16 | `test_RF16_llave_de_claude_invalida_o_sin_creditos_se_explica` | `test_verificaciones.py` | Pasa |
| BOT-RF-16 | `test_RF16_la_prueba_de_haiku_apaga_el_razonamiento_y_deja_espacio_para_responder` | `test_verificaciones.py` | Pasa |
| BOT-RF-16 | `test_RF16_un_400_muestra_el_motivo_que_da_la_api` | `test_verificaciones.py` | Pasa |
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
| BOT-RF-20 | `test_RF20_borrar_un_cliente_borra_solo_su_conversacion_en_esa_empresa` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-20 | `test_RF20_las_paginas_de_privacidad_y_borrado_son_publicas_y_propias_de_cada_empresa` | `test_panel.py` | Pasa |
| BOT-RF-20 | `test_RF20_el_admin_borra_los_datos_de_un_cliente_desde_el_panel` | `test_panel.py` | Pasa |
| BOT-RF-21 | `test_RF21_con_la_contrasena_temporal_primero_hay_que_elegir_una_propia` | `test_negocio.py` | Pasa |
| BOT-RF-21 | `test_RF21_el_admin_crea_el_acceso_y_ve_la_contrasena_temporal_una_sola_vez` | `test_negocio.py` | Pasa |
| BOT-RF-21 | `test_RF21_el_panel_del_negocio_no_da_acceso_al_de_administracion` | `test_negocio.py` | Pasa |
| BOT-RF-21 | `test_RF21_los_usuarios_tienen_login_unico_y_se_actualizan` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-21 | `test_RF21_pacientes_y_citas_de_una_empresa_no_se_ven_desde_otra` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-21 | `test_RF21_se_bloquea_tras_5_intentos_fallidos` | `test_negocio.py` | Pasa |
| BOT-RF-21 | `test_RF21_sin_csrf_no_se_guarda_nada` | `test_negocio.py` | Pasa |
| BOT-RF-21 | `test_RF21_sin_sesion_o_con_un_acceso_desactivado_no_se_entra` | `test_negocio.py` | Pasa |
| BOT-RF-21 | `test_RF21_un_usuario_no_ve_ni_toca_lo_de_otra_empresa` | `test_negocio.py` | Pasa |
| BOT-RF-21 | `test_RF21_usuarios_y_contrasenas_con_reglas_simples` | `test_agenda.py` | Pasa |
| BOT-RF-22 | `test_RF22_la_agenda_muestra_los_turnos_libres_del_horario` | `test_negocio.py` | Pasa |
| BOT-RF-22 | `test_RF22_la_semana_empieza_el_lunes_y_el_mes_se_completa_con_dias_vecinos` | `test_agenda.py` | Pasa |
| BOT-RF-22 | `test_RF22_los_turnos_libres_salen_del_horario_y_las_citas_los_ocupan` | `test_agenda.py` | Pasa |
| BOT-RF-22 | `test_RF22_una_cita_larga_ocupa_varios_turnos_y_una_fuera_de_horario_igual_aparece` | `test_agenda.py` | Pasa |
| BOT-RF-23 | `test_RF23_choques_detecta_superposicion_salvo_canceladas_y_la_misma_cita` | `test_agenda.py` | Pasa |
| BOT-RF-23 | `test_RF23_crear_una_cita_con_paciente_nuevo_y_no_dejar_otra_en_el_mismo_horario` | `test_negocio.py` | Pasa |
| BOT-RF-23 | `test_RF23_las_citas_se_leen_por_rango_con_el_paciente_y_se_actualizan` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-23 | `test_RF23_montos_en_bolivianos` | `test_agenda.py` | Pasa |
| BOT-RF-23 | `test_RF23_reprogramar_marcar_atendida_y_cancelar` | `test_negocio.py` | Pasa |
| BOT-RF-24 | `test_RF24_buscar_pacientes_y_borrar_uno_con_sus_citas` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-24 | `test_RF24_lo_pagado_suma_adelantos_aunque_se_cancele_y_lo_cobrado_solo_si_se_atendio` | `test_agenda.py` | Pasa |
| BOT-RF-24 | `test_RF24_pacientes_se_agregan_buscan_y_no_repiten_numero` | `test_negocio.py` | Pasa |
| BOT-RF-25 | `test_RF25_bloqueos_por_rango_de_fechas` [memoria, postgres] | `test_almacen.py` | Pasa |
| BOT-RF-25 | `test_RF25_el_horario_se_lee_del_formulario_y_explica_cada_fila_mal_escrita` | `test_agenda.py` | Pasa |
| BOT-RF-25 | `test_RF25_el_horario_y_los_bloqueos_se_guardan_desde_el_panel` | `test_negocio.py` | Pasa |
| BOT-RF-25 | `test_RF25_un_dia_bloqueado_no_ofrece_turnos_pero_muestra_sus_citas` | `test_agenda.py` | Pasa |
| BOT-RF-27 | `test_RF27_dos_reservas_a_la_vez_no_toman_el_mismo_turno` | `test_reservas.py` | Pasa |
| BOT-RF-28 | `test_RF28_un_archivo_que_no_es_foto_ni_pdf_no_se_guarda_como_comprobante` | `test_reservas.py` | Pasa |
| BOT-RF-28 | `test_RF28_los_mensajes_automaticos_respetan_el_trato_de_tu` | `test_reservas.py` | Pasa |
| BOT-RF-30 | `test_RF30_los_archivos_se_sirven_aislados_y_solo_si_son_foto_o_pdf` | `test_reservas.py` | Pasa |
| BOT-RF-30 | `test_RF30_un_qr_que_no_es_imagen_se_rechaza_aunque_el_navegador_diga_que_si` | `test_reservas.py` | Pasa |

"Pasa" se refiere a la corrida con PostgreSQL del entorno de armado. Cuando corras en tu PC y en Actions, actualiza la sección 2.

## 5. Lo que no se prueba (declarado)

- **Las llaves reales de Claude y de Meta:** las pruebas automáticas usan dobles. La prueba real son los pasos 4 a 6 del [despliegue](despliegue.md), con los botones **Probar** y **Verificar todo**.
- **Neon en sí:** los tests usan un PostgreSQL normal. Que la base de Neon funcione se comprueba en los pasos 1 y 2 del despliegue.
- **La calidad de las respuestas de Claude:** depende del manual. Se revisa leyendo conversaciones reales en la prueba en vivo (paso 5).
- **El JavaScript del formulario** (pasos, copiar, probar, estado del webhook): solo se probó en el recorrido de la sección 3, sin tests automáticos. Sin JavaScript, el formulario igual funciona.
- **Dos mensajes del mismo cliente en el mismo instante:** hay un candado por chat, pero no hay test de concurrencia.
- **El aviso al dueño fuera de la ventana de 24 h:** falla por regla de Meta (README, sección 9). Desde la v2.5, el motivo llega a la Actividad; se probó con el JSON que documenta Meta, no con un aviso real.

## Etapa 2: reservas por WhatsApp (v3.1, 08/11/2026)

| Corrida | Resultado |
|---|---|
| Entorno de armado, sin base | **122 passed, 17 skipped** |
| Entorno de armado, con PostgreSQL 16 real | **139 passed**, 0 saltadas |
| Base de la v3.0 actualizada a la v3.1 | Las citas existentes se conservan; las columnas nuevas y la tabla `archivos` se crean solas |
| Navegador de celular (390 px) con gunicorn + PostgreSQL | Pagos, cita con comprobante y Cobros sin errores de consola; hora de Bolivia correcta; las 5 pestañas entran en el celular |
| GitHub Actions | **Pendiente** |

| Requisito | Tests (`test_reservas.py`, salvo indicación) |
|---|---|
| BOT-RF-26 | `test_RF26_ofrece_solo_turnos_reales_del_horario_y_libres`, `test_RF26_sin_activar_o_sin_horario_el_bot_no_agenda` |
| BOT-RF-27 | `test_RF27_un_paciente_nuevo_reserva_y_debe_el_50_de_la_valoracion_de_su_sede`, `test_RF27_los_casos_que_no_se_agendan_solos_piden_derivar`, `test_RF27_en_el_chat_claude_usa_las_herramientas_y_el_bot_manda_el_qr`, `test_RF27_el_asistente_ejecuta_las_herramientas_que_pide_claude_y_suma_los_tokens` |
| BOT-RF-28 | `test_RF28_la_foto_del_comprobante_pasa_la_cita_a_por_revisar_y_avisa_a_la_asistente`, `test_RF28_una_foto_sin_reserva_recibe_la_respuesta_de_siempre`, `test_RF28_meta_avisa_el_id_de_la_foto_y_su_texto`, `test_RF28_archivos_y_campos_de_reserva_se_guardan` [memoria, postgres] (`test_almacen.py`) |
| BOT-RF-29 | `test_RF29_reprograma_si_faltan_mas_de_24_horas_y_no_si_faltan_menos`, `test_RF29_sin_comprobante_a_tiempo_el_horario_se_libera_y_se_avisa`, `test_RF29_cancelar_avisa_que_el_adelanto_no_se_devuelve` |
| BOT-RF-30 | `test_RF30_aprobar_confirma_la_cita_anota_el_adelanto_y_le_avisa_al_paciente`, `test_RF30_rechazar_vuelve_a_pedir_el_comprobante_con_un_plazo_nuevo`, `test_RF30_la_pestana_pagos_cuenta_los_comprobantes_y_otra_empresa_no_ve_los_archivos`, `test_RF30_la_duena_configura_los_cobros_y_la_asistente_no`, `test_RF30_el_qr_de_cobro_es_publico_y_solo_si_es_un_qr` |

**Lo que no se prueba automáticamente:** la conversación real con Claude (las pruebas usan un doble que "decide" qué herramientas usar) y la descarga real de una foto desde Meta. Se prueban con el número de prueba, siguiendo `docs/despliegue.md`.

## v3.4.2: ventana de Meta y canje del código (09/11/2026)

| Entorno | Resultado |
|---|---|
| v3.4.1 · GitHub Actions #15 (commit `638f82f`) | **192 passed**, 0 saltadas |
| v3.4.2 · entorno de armado, con PostgreSQL 16 real | **194 passed**, 0 saltadas (2 nuevas: `test_RF36_si_meta_pide_redirect_uri_se_reintenta_con_redirect_uri_vacio`, `test_RF36_si_la_ventana_se_cierra_sin_registro_el_panel_lo_explica`) |
| v3.4.2 · GitHub Actions | **Pendiente:** confirmar al subir |

## v3.4.1: la conexión no depende del aviso de Meta (09/11/2026)

| Entorno | Resultado |
|---|---|
| v3.4 · GitHub Actions #14 (commit `f7fa0fe`) | **189 passed**, 0 saltadas |
| v3.4.1 · entorno de armado, con PostgreSQL 16 real | **192 passed**, 0 saltadas (3 nuevas) |
| v3.4.1 · GitHub Actions #15 (commit `638f82f`) | **192 passed**, 0 saltadas (09/11/2026) |

| Requisito | Tests nuevos (`test_coexistencia.py`) |
|---|---|
| BOT-RF-36 | `test_RF36_si_meta_no_manda_el_id_de_la_cuenta_el_bot_la_busca_con_el_token`, `test_RF36_sin_cuenta_en_el_token_no_cambia_nada_y_la_actividad_dice_lo_que_aviso_meta`, `test_RF36_registro_lee_las_cuentas_del_token` |

## v3.4: coexistencia del número del negocio (09/11/2026)

| Entorno | Resultado |
|---|---|
| v3.3.1 · GitHub Actions #13 (commit `5c40504`) | **175 passed**, 0 saltadas |
| v3.4 · entorno de armado, con PostgreSQL 16 real | **189 passed**, 0 saltadas (14 nuevas en `tests/test_coexistencia.py`) |
| v3.4 · pantalla WhatsApp Business del negocio a 390 px (Playwright) | Sin desplazamiento horizontal, sin errores en la consola |
| v3.4 · GitHub Actions #14 (commit `f7fa0fe`) | **189 passed**, 0 saltadas (09/11/2026) |

| Requisito | Tests (`test_coexistencia.py`) |
|---|---|
| BOT-RF-36 | `test_RF36_registro_canjea_el_codigo_sincroniza_y_nunca_registra_el_numero`, `test_RF36_conectar_cambia_al_numero_del_negocio_y_sincroniza_en_orden`, `test_RF36_si_el_numero_no_esta_en_la_app_o_falla_el_codigo_no_cambia_nada`, `test_RF36_volver_al_numero_de_prueba`, `test_RF36_la_pantalla_pide_sesion_y_carga_meta_solo_ahi`, `test_RF36_sin_sesion_no_se_ve_ni_se_conecta`, `test_RF36_el_id_de_la_configuracion_son_solo_numeros` |
| BOT-RF-37 | `test_RF37_extrae_lo_que_el_negocio_escribe_desde_el_celular`, `test_RF37_si_la_duena_responde_a_mano_el_bot_se_calla_en_ese_chat`, `test_RF37_webhook_con_un_eco_firmado_pausa_el_chat` |
| BOT-RF-38 | `test_RF38_avisos_de_historial_contactos_y_cuenta`, `test_RF38_la_actividad_cuenta_el_historial_y_avisa_la_desconexion` |
| BOT-RF-39 | `test_RF39_cada_sincronizacion_una_vez_en_orden_y_dentro_de_24_horas`, `test_RF39_pasadas_24_horas_no_se_pide_la_sincronizacion` |

**Lo que no se prueba automáticamente:** la ventana de Meta (el SDK, el QR y el mensaje que avisa el fin del registro) y las respuestas reales de la Graph API: las pruebas usan dobles con la forma que da la documentación de Meta del 09/11/2026. La primera conexión real se hace desde el panel, con la empresa en prueba.

## v3.3.1: revisión de seguridad de la v3.3 (09/11/2026)

| Entorno | Resultado |
|---|---|
| v3.3 tal como está en GitHub (commit `2293994`) · GitHub Actions #12 | **165 passed**, 0 saltadas |
| v3.3 · entorno de armado, con PostgreSQL 16 real | **165 passed** (punto de partida) |
| v3.3.1 · entorno de armado, con PostgreSQL 16 real | **175 passed**, 0 saltadas (10 pruebas nuevas y 1 corregida) |
| Las pruebas nuevas contra el código de la v3.3 | **11 fallan**: cada una muestra un problema real que la v3.3.1 corrige |
| v3.3.1 · GitHub Actions #13 (commit `5c40504`) | **175 passed**, 0 saltadas (09/11/2026) |

| Requisito | Tests nuevos o cambiados |
|---|---|
| BOT-RF-12 | `test_RF12_el_webhook_ignora_los_mensajes_de_otra_pagina_u_otro_instagram`, `test_RF12_reglas_separan_los_avisos_de_cada_cuenta` (`test_canales.py`) |
| BOT-RF-14 | `test_RF14_el_bloqueo_no_se_salta_cambiando_x_forwarded_for`, `test_RF14_en_render_cuenta_la_ip_que_pone_cloudflare` (`test_panel.py`) |
| BOT-RF-20 | `test_RF20_las_paginas_legales_nombran_messenger_e_instagram_si_estan_conectados`, `test_RF20_el_admin_borra_un_chat_de_messenger_con_la_cuenta_del_aviso` (`test_canales.py`) |
| BOT-RF-33 | `test_RF33_si_falla_la_conexion_el_token_de_la_pagina_no_queda_en_los_registros`, `test_RF33_la_ventana_de_24_horas_se_explica_bien_y_no_como_falta_de_permiso`, `test_RF33_si_meta_no_acepta_la_respuesta_la_actividad_dice_por_que`, `test_RF33_solo_se_bajan_archivos_de_los_servidores_de_meta`; cambiada: `test_RF33_mensajeria_manda_cada_destino_por_su_canal_y_parte_los_textos_largos` (el token va en la cabecera) |

**Revisado y sin cambios:** firma del webhook (`X-Hub-Signature-256` con el App Secret de cada empresa, comparación de tiempo constante, sin secreto se rechaza); llaves cifradas con Fernet y la `CLAVE_MAESTRA`, enmascaradas en pantalla; CSRF en todos los formularios del panel, del negocio y del alta; sesiones `HttpOnly`, `SameSite=Lax` y `Secure` en Render; cabeceras de seguridad (CSP, `X-Frame-Options`); aislamiento del panel del negocio (cada consulta usa la empresa del usuario); archivos servidos por su tipo real y aislados; SQL siempre con parámetros.

**Queda anotado, sin cambiar:** las llamadas de la pantalla Canales a Meta (`debug_token`, páginas, suscripciones) siguen mandando los tokens como parámetro, como pide la API para `debug_token`; no se registran si fallan. El candidato de prueba de Messenger e Instagram se guarda leyendo la empresa al llegar el mensaje: si justo en ese momento se cambia algo en Canales, puede perderse ese cambio (es raro y se vuelve a hacer).

## v3.3: Messenger e Instagram (09/11/2026)

| Entorno | Resultado |
|---|---|
| v3.3 · entorno de armado, con PostgreSQL 16 real | **165 passed**, 0 saltadas (18 nuevas en `tests/test_canales.py`) |
| v3.3 · pantalla Canales a 390 px de ancho (Playwright) | Sin desplazamiento horizontal |
| v3.3 · GitHub Actions #12 (commit `2293994`) | **165 passed**, 0 saltadas (09/11/2026) |

| Requisito | Tests |
|---|---|
| BOT-RF-32 | `test_RF32_extrae_mensajes_de_messenger_e_ignora_ecos`, `test_RF32_extrae_mensajes_de_instagram_y_no_los_propios`, `test_RF32_webhook_de_messenger_firmado_se_atiende` |
| BOT-RF-33 | `test_RF33_messenger_conectado_responde_por_su_canal_sin_agenda`, `test_RF33_derivar_desde_instagram_avisa_al_dueno_por_whatsapp`, `test_RF33_mensajeria_manda_cada_destino_por_su_canal_y_parte_los_textos_largos` |
| BOT-RF-34 | `test_RF34_en_prueba_solo_responde_a_las_cuentas_de_prueba`, `test_RF34_panel_enciende_apaga_y_marca_cuentas_de_prueba` |
| BOT-RF-35 | `test_RF35_panel_busca_las_paginas_y_conecta_messenger_e_instagram`, `test_RF35_conector_revisa_permisos_y_trae_paginas_con_instagram`, `test_RF35_verificar_todo_revisa_la_pagina_conectada_sin_bloquear_whatsapp` |

No se prueba contra Meta de verdad: las llamadas a la Graph API se reemplazan por dobles. La primera conexión real se hace desde la pantalla Canales.

## v3.2: listo para sumar empresas (08/11/2026)

| Corrida | Resultado |
|---|---|
| v3.1.1 tal como está en GitHub (punto de partida) | **144 passed** con PostgreSQL |
| v3.2 · entorno de armado, sin base | **130 passed, 17 skipped** |
| v3.2 · entorno de armado, con PostgreSQL 16 real | **147 passed**, 0 saltadas |
| v3.2 · GitHub Actions (setup-python@v6, upload-artifact@v5, ubuntu-24.04) | **Pendiente:** confirmar que el CI sale en verde y sin avisos de Node.js 20 |

| Requisito | Tests (`test_panel.py`) |
|---|---|
| BOT-RF-17 | `test_RF17_si_el_saldo_alcanza_para_anos_no_muestra_una_fecha_enganosa` (y la fecha con año en `test_RF17_el_detalle_muestra_cuantos_dias_de_credito_quedan`) |
| BOT-RF-31 | `test_RF31_la_puesta_en_marcha_dice_que_falta_y_se_completa_paso_a_paso`, `test_RF31_el_alta_trae_las_direcciones_para_publicar_la_app` |
