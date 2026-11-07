# Glosario

Para leer el código y los `docs/` sin perderse. Si algo de aquí contradice a otro documento, manda el otro documento y este se corrige.

| Término | Qué significa aquí |
|---|---|
| **API** | Puerta para que un programa use un servicio. Aquí se usan dos: la de Claude (Anthropic) y la Cloud API de WhatsApp (Meta). |
| **API key / llave** | Contraseña del programa ante la API de Claude. Va en `ANTHROPIC_API_KEY` y nunca se sube a GitHub. |
| **Créditos de uso** | Saldo prepagado en platform.claude.com. Cada respuesta de Claude descuenta según el texto procesado. |
| **Manual / instrucciones del sistema** | `instrucciones.md`: lo que Claude sabe del negocio y cómo debe hablar. También se le dice *system prompt*. |
| **Webhook** | Dirección (`/webhook`) a la que Meta avisa cada mensaje nuevo. |
| **Verify token** | Palabra que inventas tú; Meta la manda una vez para comprobar que el webhook es tuyo (BOT-RF-08). |
| **App Secret / firma** | Clave de la app de Meta. Meta firma cada aviso con ella (cabecera `X-Hub-Signature-256`) y el bot comprueba la firma (BOT-RF-07). |
| **Phone number ID** | Identificador del número desde el que el bot envía. No es el número de teléfono. |
| **Token de WhatsApp** | Permiso para enviar mensajes. El de API Setup vence en unas 24 h; el de un usuario del sistema no vence. |
| **Número de prueba** | Número gratis que da Meta para probar. Solo le escribe a los destinatarios que agregaste. |
| **WABA** | WhatsApp Business Account: la cuenta de WhatsApp del negocio dentro de Meta. |
| **Coexistencia** | Usar el mismo número en la app de WhatsApp Business y en la Cloud API a la vez (D-05). |
| **Ventana de 24 h** | Tiempo en que el negocio puede responder con mensajes libres después de que alguien le escribe. Fuera de ella, solo plantillas. |
| **Plantilla** | Mensaje aprobado por Meta para escribir primero o fuera de la ventana de 24 h. |
| **Derivar / marca** | Pasarle el chat a la dueña. Claude lo pide terminando su respuesta con `[PASAR_A_HUMANO]` (BOT-RF-04). |
| **Pausa** | Tiempo (12 h por defecto) en que el bot no responde en un chat derivado. |
| **Historial** | Últimos mensajes de un cliente; Claude recibe 20 en cada respuesta (BOT-RF-02). |
| **CI** | Integración continua: GitHub Actions corre los tests en cada push. |
| **Blueprint** | `render.yaml`: describe el servicio para que Render lo cree desde el repositorio. |
| **Dormirse (spin down)** | Render gratis apaga el servicio tras 15 min sin tráfico y lo prende con el siguiente mensaje (D-02). |
| **Atlas M0** | Plan gratuito de MongoDB Atlas, donde se guarda el historial (D-03). |
| **TTL** | Índice de MongoDB que borra documentos solos; aquí, los ids atendidos a los 7 días. |
| **Hilo** | Tarea que corre en paralelo dentro del mismo proceso; el bot atiende cada mensaje en uno (D-07). |
| **gunicorn** | Servidor que arranca el bot en Render. En tu PC se usa `python -m bot`. |
| **Túnel (cloudflared)** | Da a tu PC una URL pública temporal para que Meta llegue al bot mientras pruebas. |
| **Doble (de prueba)** | Objeto falso que reemplaza a WhatsApp o a Claude en los tests y anota lo que recibe. |
| **[ACUERDO] / [PROPUESTA] / [PROVISIONAL]** | Estado de una decisión: la tomó Hugo / la propuso Claude y falta confirmarla / vale mientras no se resuelva algo abierto. |
