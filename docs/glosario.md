# Glosario

Para leer el código y los `docs/` sin perderse. Si algo de aquí contradice a otro documento, manda el otro documento y este se corrige.

| Término | Qué significa aquí |
|---|---|
| **Empresa** | Un negocio atendido por el bot, con sus propias llaves, número, manual y webhook (BOT-RF-12). |
| **Slug** | El nombre de la empresa en la dirección: `Boutique Las Palmas` → `boutique-las-palmas`. |
| **Panel** | `/panel`: donde el administrador ve y maneja todas las empresas. |
| **Enlace de alta** | `/alta/<token>`: formulario de 6 pasos para que el dueño cargue sus datos. Sirve una vez y vence en 7 días (BOT-RF-15). |
| **Estados** | Esperando datos (borrador), En prueba (solo le responde al dueño), Activo, Pausado (BOT-RF-18). |
| **Verificar** | Probar de verdad cada llave contra Claude y Meta y guardar el resultado (BOT-RF-16). |
| **Crédito estimado** | Saldo cargado menos lo gastado según los tokens que contó el bot. Los días restantes salen del gasto promedio de la última semana (BOT-RF-17, D-15). |
| **Token (de Claude)** | Unidad en la que Claude cobra: entrada (lo que lee) y salida (lo que escribe). Haiku 5.5: USD 0.10 y 0.50 por millón. |
| **Clave maestra** | `CLAVE_MAESTRA`: cifra las llaves de todas las empresas. Si cambia, hay que volver a cargarlas (D-14). |
| **CSRF** | Ataque en el que otra página envía un formulario en tu nombre. Cada formulario del panel lleva un token que lo evita. |
| **API key / llave de Claude** | Contraseña de la empresa ante la API de Claude. Empieza con `sk-ant-`. |
| **Créditos de uso** | Saldo prepagado en platform.claude.com. Vencen al año de la compra. |
| **Manual** | Lo que Claude sabe y cómo habla: la plantilla común `instrucciones.md` más los datos de cada empresa. |
| **Webhook** | Dirección (`/webhook/<slug>`) a la que Meta avisa cada mensaje de esa empresa. |
| **Verify token** | Palabra al azar de cada empresa; Meta la manda para comprobar que el webhook es suyo. |
| **App ID / App Secret** | Identificador y clave de la app de Meta. Con el App Secret, Meta firma cada aviso. |
| **Phone number ID** | Identificador del número en Meta. No es el número de teléfono. |
| **Token de WhatsApp** | Permiso para enviar mensajes. El de Configuración de la API vence en unas 24 h; el de un usuario del sistema no vence. |
| **Calidad del número** | Calificación de Meta (alta, media, baja) según bloqueos y reportes de clientes. Baja = límites. |
| **Ventana de 24 h** | Tiempo en que el negocio puede escribir libremente después de que alguien le escribe. Fuera de ella, solo plantillas. |
| **Coexistencia** | Usar el mismo número en la app de WhatsApp Business y en la API a la vez (D-05). |
| **Derivar / marca** | Pasar el chat al dueño: Claude termina con `[PASAR_A_HUMANO]` (BOT-RF-04). |
| **Números ignorados** | Familia, proveedores y otros números a los que el bot nunca responde (BOT-RF-19). |
| **PostgreSQL / Neon** | Base de datos donde se guarda todo (D-03). Neon la da gratis y la duerme sin uso. |
| **Pool de conexiones** | Conexiones a la base que el servicio reutiliza; prueba cada una antes de usarla. |
| **CI** | GitHub Actions corre los 69 tests en cada push, con un PostgreSQL temporal. |
| **Blueprint** | `render.yaml`: describe el servicio para que Render lo cree desde el repositorio. |
| **Dormirse** | Render gratis apaga el servicio tras 15 min sin tráfico y lo prende con el siguiente (D-02). |
| **Doble (de prueba)** | Objeto falso que reemplaza a Meta, Claude o el verificador en los tests. |
| **Contrato (tests)** | Los mismos tests corren contra los dos almacenes para garantizar que se comportan igual (D-12). |
| **[ACUERDO] / [PROPUESTA] / [PROVISIONAL]** | Estado de una decisión: la tomó Hugo / la propuso Claude y falta confirmarla / vale mientras no se resuelva algo abierto. |
