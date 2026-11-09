# Despliegue paso a paso (v2.0)

- Proyecto: Bots de WhatsApp con Claude · Responsable: Hugo Zúñiga
- Fecha: 08/11/2026 · Estado: v1.0 subida; pasos de la v2.0 **pendientes**
- Relacionados: [README](../README.md) · [Arquitectura](arquitectura.md) · [Decisiones](decisiones.md)

Cada paso termina con una **comprobación**. Si no da lo esperado, no pases al siguiente: mira la tabla de problemas al final. Los menús de Meta, Render y Neon cambian de nombre seguido; si algo no se llama igual, busca el más parecido.

## Paso 0. Subir la v2.0 a GitHub

`$env:USERPROFILE` es tu carpeta de usuario (`C:\Users\hugor` en la PC, `C:\Users\sebas` en la laptop), así que los mismos comandos sirven en las dos. Antes de trabajar en una máquina, haz `git pull`.

```powershell
cd $env:USERPROFILE\Downloads\Bot-WhatsApp
git pull origin main
Expand-Archive -Path "$env:USERPROFILE\Downloads\parche-v2.0.zip" -DestinationPath . -Force
git add -A
git status
git commit -m "v2.0: multiempresa, panel, enlaces de alta, llaves cifradas y estimación de crédito"
git push origin main
```

La v2.0 ya incluye lo del parche v1.1: no hace falta aplicarlo aparte.

**Comprobación:**
- En `git status` no aparece ningún `.env`.
- En GitHub → **Actions**, "CI - pruebas del bot" sale en verde con 69 passed y 0 saltadas.

## Paso 1. Base de datos en Neon

1. En [neon.com](https://neon.com) (puedes entrar con GitHub) crea un proyecto en el plan gratis, en la región **AWS US East (N. Virginia)**.
2. En **Connect**, copia la cadena de conexión: empieza con `postgresql://` y termina con `?sslmode=require`.

Usa una base **nueva**. Si probaste la v1.1 contra Neon, esa base tiene tablas viejas y el servicio no va a arrancar hasta que uses otra.

**Comprobación:** tienes la cadena copiada. Las tablas las crea el servicio al arrancar.

## Paso 2. Servicio en Render

1. Entra a [render.com](https://render.com) con tu cuenta de GitHub y dale acceso al repositorio `Bot-WhatsApp`.
2. **New → Blueprint**, elige el repositorio. Render lee `render.yaml`.
3. Te pide dos valores:
   - `DATABASE_URL`: la cadena de Neon.
   - `ADMIN_PASSWORD`: la contraseña del panel. Usa una larga y guárdala en tu gestor de contraseñas.
4. Aplica y espera el primer despliegue.
5. **Guarda la `CLAVE_MAESTRA`:** Render la genera sola. Cópiala desde el servicio → **Environment** a tu gestor de contraseñas. Si algún día se pierde o cambia, las llaves de las empresas ya no se pueden leer y hay que volver a cargarlas.

**Comprobación:** en **Logs** aparece `Almacen: PostgreSQL`, y `https://<tu-servicio>.onrender.com/salud` muestra `ok`.

## Paso 3. Entrar al panel

Abre `https://<tu-servicio>.onrender.com/` en tu celular, entra con tu contraseña y guárdalo en la pantalla de inicio (menú del navegador → **Agregar a pantalla de inicio**).

**Comprobación:** ves la pantalla **Empresas** vacía.

## Paso 4. La primera empresa

1. En **Agregar una empresa**, escribe el nombre del negocio y toca **Crear y generar enlace**.
2. Tienes dos caminos:
   - **Que lo llene el dueño:** toca **Enviar por WhatsApp**. El enlace sirve una vez y vence en 7 días.
   - **Llenarlo tú:** en el detalle de la empresa, toca **Editar datos y llaves**. Son los mismos pasos, más uno de ajustes.
3. Los pasos 3 y 4 del formulario explican dónde sacar cada llave y tienen botones **Probar**. Para probar sin tocar el número real, usa el número de prueba que Meta da en **WhatsApp → Configuración de la API**, y agrega tu celular como destinatario de prueba.
4. El paso 5 muestra la dirección del webhook y su token para pegarlos en Meta. Cuando Meta los verifica, ese paso cambia solo a **Conectado**. Después suscríbete a `messages`.
5. Con el webhook ya conectado, en el detalle de la empresa → **Conexión → Cambiar el token de verificación**. Meta lo mandó dentro de la dirección y quedó en los registros de Render (D-24). El bot sigue recibiendo mensajes igual; solo si algún día vuelves a tocar **Verificar y guardar** en Meta, pega antes el token nuevo.

**Comprobación:** al enviar, la empresa aparece **En prueba**. Las pruebas del formulario salieron en verde y el webhook dice **Conectado**.

## Paso 4b. Publicar la app en Meta

Mientras la app está "sin publicar", Meta solo le manda al bot los avisos de prueba de su panel: **los mensajes reales no llegan**, ni siquiera los del administrador. Para publicarla:

1. En el panel del bot, sección **Conexión → Para publicar la app en Meta**, copia las dos direcciones: política de privacidad y eliminación de datos.
2. En developers.facebook.com → tu app → **Configuración de la app → Básica**, completa:
   - la **URL de la política de privacidad**;
   - la **URL de instrucciones para eliminar los datos**;
   - el **ícono de la app** (1024 × 1024, JPG o PNG, hasta 5 MB; el logo del negocio centrado sobre fondo blanco);
   - la **categoría** (por ejemplo, "Negocios y páginas" o "Mensajería").

   Luego toca **Guardar cambios**.
3. Publica la app desde el botón o interruptor de publicar (los nombres cambian: "Publicar", "Modo: Activo"). Meta revisa que esté todo lo anterior.

**Comprobación:** la app ya no dice "Sin publicar". Al escribirle al número desde tu celular, el panel muestra en **Actividad** el último mensaje de un cliente.

Las páginas de privacidad y borrado se generan solas para cada empresa, con su nombre. Son un texto base: revísalas con el negocio.

### Dónde va el logo del negocio

| Dónde | Para qué | Tamaño |
|---|---|---|
| developers.facebook.com → la app → **Configuración de la app → Básica → Ícono de la app** | Lo pide Meta para publicar la app. Los clientes no lo ven | 1024 × 1024 |
| business.facebook.com → **WhatsApp Manager → Números de teléfono** → el número → **Perfil** | La foto que ven los clientes en el chat con el bot | 640 × 640, con el logo dentro del círculo (WhatsApp la recorta redonda) |
| App de WhatsApp Business del celular → **Herramientas para la empresa → Perfil de empresa** (en Android, desde el menú ⋮; en iPhone, desde Configuración) | La foto del número que atiende la dueña | La misma de 640 × 640 |

El número de prueba de Meta no deja cambiar su nombre visible; la foto de perfil importa recién con el número real (paso 8).

## Paso 5. Prueba en vivo

1. Desde el celular del dueño (el número que se cargó como "tu número personal"), escríbele al número del negocio.
2. Prueba lo básico: un saludo, una pregunta sobre el negocio, un audio y "quiero hablar con una persona".

**Comprobación:**
- El bot le responde **solo** al dueño.
- En el panel, **Actividad** muestra la derivación.
- **Uso de los últimos 14 días** muestra la barra de hoy.

## Paso 6. Verificar y activar

1. Toca **Verificar todo**. Cada línea debe salir con ✓. Si algo sale en rojo, el texto dice qué arreglar.
2. Toca **Enviar mensaje de prueba**. Llega al dueño si él le escribió al número en las últimas 24 h. Si Meta lo rechaza, el panel lo explica al instante; si lo acepta pero no lo entrega, el motivo aparece en **Actividad** unos segundos después.
3. Escribe el saldo real de la cuenta de Claude en **Actualizar saldo**.
4. Toca **Activar para todos**.

**Comprobación:** la empresa dice **Activo** y la lista muestra los días de crédito.

## Paso 6b. La agenda del negocio

1. En el detalle de la empresa → **Agenda del negocio** → **Crear un acceso**: nombre, usuario y rol. Uno para la dueña y otro para la asistente.
2. Copia el texto que aparece (dirección, usuario y contraseña temporal) o tócalo **Enviar por WhatsApp**. La contraseña no se vuelve a mostrar; si se pierde, **Contraseña nueva**.
3. Cada una entra en `https://<tu-servicio>.onrender.com/negocio/entrar`, elige su contraseña y carga el **Horario**: una fila por bloque (día, sede, desde, hasta) y la duración del turno.

**Comprobación:** en **Agenda** aparecen los turnos libres de la semana; al tocar uno y guardar una cita, el turno pasa a ocupado y otra cita en ese horario no se deja guardar.

## Paso 7. Token permanente de Meta

El token de **Configuración de la API** vence en unas 24 h, y la verificación lo marca en amarillo. Para uno permanente:

1. En [Configuración del negocio → Usuarios del sistema](https://business.facebook.com/settings/system-users), crea un usuario de administrador.
2. Asígnale la app y la cuenta de WhatsApp.
3. Genera un token con `whatsapp_business_messaging` y `whatsapp_business_management`, sin vencimiento.
4. Pégalo en **Editar datos y llaves** (paso 4) y vuelve a verificar.

**Comprobación:** la verificación dice "El token no vence".

## Paso 8. El número real de tu mamá — pendiente (D-05)

| Opción | Su app de WhatsApp Business | Costo | Trabajo |
|---|---|---|---|
| A. Proveedor con coexistencia | Sigue funcionando con el mismo número | Depende del proveedor | Conectar el número por el proveedor y adaptar `whatsapp.py` si usa su propia API |
| B. Número nuevo para el bot | Su número no cambia; el del bot no tiene app | Un chip | Registrar el número en la Cloud API |
| C. Pasar su número actual solo a la API | Deja de funcionar | — | No recomendado |

Para la coexistencia, Meta pide que el número lleve al menos 7 días de uso activo en WhatsApp Business. Mientras tanto, que tu mamá lo siga usando normal y complete el perfil del negocio.

## Paso 9. Messenger e Instagram (v3.3)

1. En Meta Business Suite → Configuración → Usuarios del sistema, el usuario del sistema debe tener asignadas la página y la cuenta de Instagram.
2. Genera un token de ese usuario para la app con: `pages_show_list`, `pages_manage_metadata`, `pages_messaging`, `instagram_basic`, `instagram_manage_messages` (y los de WhatsApp, si es el mismo token).
3. En Instagram → Configuración → Mensajes → Herramientas conectadas, activa «Permitir acceso a los mensajes».
4. En el panel: la empresa → **Canales** → pega el token (o déjalo vacío para usar el guardado) → **Buscar mis páginas** → elige la página y los canales → **Conectar**. El bot suscribe la página y registra el webhook en Meta con la misma dirección y token de WhatsApp.
5. Con la empresa en prueba, escríbele a la página desde tu cuenta y, en Canales, toca **Usar para probar**.
6. Para que responda a todo el público, Meta exige la revisión de la app para `pages_messaging` e `instagram_manage_messages`. Hasta entonces solo entrega mensajes de quienes tienen un rol en la app.

## Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El servicio no arranca: `Faltan estas variables` | Falta `ADMIN_PASSWORD` o `CLAVE_MAESTRA` | Render → Environment |
| El servicio no arranca: "tablas de una versión anterior" | La base tiene tablas de la v1.x | Usa una base nueva en Neon |
| `No se pudo leer una llave guardada` | Cambió la `CLAVE_MAESTRA` | Restaura la anterior, o vuelve a cargar las llaves de cada empresa |
| "Demasiados intentos" al entrar | 5 contraseñas incorrectas | Espera 15 minutos |
| "El formulario venció" | Se abrió hace mucho o en otra sesión | Recarga la página |
| Meta no acepta el webhook | Token de verificación distinto, o el servicio estaba dormido | Cópialo con el botón; abre `/salud` para despertarlo y reintenta |
| Webhook en "Esperando a Meta…" | Falta tocar Verificar y guardar en Meta | Paso 5 del formulario |
| La prueba dice "últimas 24 horas" | Regla de WhatsApp | El dueño le escribe primero al número del negocio |
| "Meta aceptó el mensaje de prueba" pero no llega | Meta lo aceptó y después no lo pudo entregar | Recarga el detalle de la empresa: en **Actividad** está el motivo ("Meta no pudo entregar un mensaje a ...") |
| "no está en la lista de destinatarios" | Número de prueba de Meta | Agrega el celular en Configuración de la API |
| Claude "no tiene créditos" | Saldo en cero | Carga en platform.claude.com y actualiza el saldo en el panel |
| El primer mensaje tarda ~1 min | Render gratis se había dormido | Esperado (D-02) |
| "La base de datos no respondió" | Neon caído o sin red (si solo dormía, el bot lo despierta solo) | El formulario no se envía y conserva tus llaves: espera un minuto y vuelve a tocar el botón. `https://<tu-servicio>.onrender.com/salud/base` debe decir `ok`. Si se repite, busca en los logs de Render `Falló una conexión a la base`: dice el motivo |
| En Actions aparece "pages-build-deployment" | GitHub Pages quedó activado en el repositorio | No hace falta para el bot: GitHub → Settings → Pages → desactivarlo |
| Render no despliega tras un push | El CI falló (`checksPass`, D-09) | Mira Actions |
| La agenda no muestra turnos libres | Falta cargar el horario, o el día está bloqueado | `/negocio/horario` |
| "Usuario o contraseña incorrectos" en la agenda | Contraseña equivocada o acceso desactivado | En el panel → Agenda del negocio → **Contraseña nueva** o **Activar** |

## Activar las reservas por WhatsApp (v3.1)

1. Entra a `/negocio` con el usuario de la dueña. En **Horario**, carga los días, las sedes y las horas. Sin horario, el bot no tiene turnos para ofrecer.
2. En **Pagos → Configurar cobros**:
   - el precio de la valoración de cada sede, y su ubicación (dirección o enlace de Maps);
   - el porcentaje del adelanto (50) y las horas para mandar el comprobante (2);
   - los datos para pagar y, si hay, la imagen del QR de cobro;
   - el WhatsApp de la asistente, que recibe el aviso de cada comprobante.

   Marca **El bot agenda y cobra adelantos** y guarda.
3. **Prueba con el número de prueba:** desde tu celular escribe "Quiero una cita de valoración". El bot pregunta el motivo y la sede, ofrece turnos, pide el nombre y aparta el horario. Manda una foto cualquiera como comprobante: la cita aparece en **Pagos** con el contador. Ábrela, revisa la foto y toca **Aprobar pago**. El bot te confirma la cita con la ubicación.

**Comprobación:** en la Agenda, la cita pasa de "Pendiente de pago" a "Pago por revisar" y a "Confirmada". Si no mandas el comprobante en 2 horas, el horario se libera solo.

**Sobre el aviso a la asistente:** WhatsApp solo deja mandárselo si ella le escribió al número del negocio en las últimas 24 horas. Si no, el aviso no llega (queda en la Actividad del panel) y ella ve el contador en la pestaña **Pagos**. El aviso con botones de Aprobar y Rechazar, con una plantilla de Meta, es la etapa 2b.
