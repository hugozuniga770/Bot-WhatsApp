# Despliegue paso a paso

- Proyecto: Bot de WhatsApp con Claude (negocio de mi mamá) · Responsable: Hugo Zúñiga
- Fecha: 07/11/2026 · Estado: **pendiente**, ningún paso ejecutado todavía
- Relacionados: [README](../README.md) · [Arquitectura](arquitectura.md) · [Decisiones](decisiones.md)

Cada paso termina con una **comprobación**. Si la comprobación no da lo esperado, no pases al siguiente: mira la tabla de problemas al final. Los menús de Meta, Render y Atlas cambian de nombre seguido; si algo no se llama igual, busca el equivalente.

## Paso 0. Subir el proyecto a GitHub

Repositorio: [hugozuniga770/Bot-WhatsApp](https://github.com/hugozuniga770/Bot-WhatsApp). La primera vez (repositorio vacío), en PowerShell:

```powershell
cd C:\Users\hugor\Downloads
git clone https://github.com/hugozuniga770/Bot-WhatsApp.git
cd Bot-WhatsApp
Expand-Archive -Path "C:\Users\hugor\Downloads\bot-whatsapp-v1.0.zip" -DestinationPath . -Force
git add -A
git status
git commit -m "v1.0: bot de WhatsApp con Claude, pruebas, CI y despliegue en Render"
git branch -M main
git push -u origin main
```

Cada versión siguiente llega como un parche y se aplica igual que en Reserva de Salas:

```powershell
cd C:\Users\hugor\Downloads\Bot-WhatsApp
git pull origin main
Expand-Archive -Path "C:\Users\hugor\Downloads\parche-vX.Y.zip" -DestinationPath . -Force
git add -A
git commit -m "vX.Y: qué cambia"
git push origin main
```

**Comprobación:** en `git status`, el archivo `.env` **no** aparece (si aparece, no hagas commit y revisa `.gitignore`). En GitHub, la pestaña **Actions** muestra el workflow "CI - pruebas del bot" en verde, con 17 passed. El repositorio puede ser público o privado: en ningún caso tiene llaves ni datos de clientes.

## Paso 1. Créditos y llave de Claude

1. En [platform.claude.com](https://platform.claude.com), compra créditos de uso. Para empezar alcanza con el monto mínimo; la misma página dice que USD 5 basta para crear y probar una primera integración. Los créditos vencen un año después de la compra.
2. Ve a **Settings → API keys** y crea una llave. Se muestra una sola vez: cópiala a tu `.env` como `ANTHROPIC_API_KEY`.
3. Si la consola ofrece un límite de gasto mensual, ponlo bajo mientras pruebas.

**Comprobación:** la llave empieza con `sk-ant-`. En el paso 6, el bot responde con texto de Claude y no con la disculpa de BOT-RF-06.

Si la tarjeta es rechazada, revisa con tu banco que esté habilitada para compras internacionales en línea.

## Paso 2. App de Meta y número de prueba

1. En [developers.facebook.com](https://developers.facebook.com) crea una app y elige el caso de uso de WhatsApp.
2. En **WhatsApp → API Setup** vas a ver el número de prueba, el **Phone number ID** y un **token temporal**. Cópialos a `PHONE_NUMBER_ID` y `WHATSAPP_TOKEN`.
3. En esa misma pantalla, agrega tu celular como destinatario de prueba (te llega un código por WhatsApp).
4. En **App settings → Basic**, muestra y copia el **App secret** a `APP_SECRET`.
5. Inventa una palabra para `VERIFY_TOKEN`.

**Comprobación:** desde API Setup, el botón para enviar el mensaje de prueba te hace llegar la plantilla `hello_world` a tu celular.

## Paso 3. Base de datos en MongoDB Atlas

1. En [mongodb.com/atlas](https://www.mongodb.com/atlas) crea un clúster gratuito (M0).
2. **Database Access:** crea un usuario con contraseña. Usa una contraseña sin símbolos raros, o tendrás que codificarlos en la cadena de conexión.
3. **Network Access:** permite `0.0.0.0/0`. Render gratis no tiene una IP fija, así que no se puede limitar por IP; la protección es el usuario y la contraseña.
4. **Connect → Drivers → Python:** copia la cadena `mongodb+srv://...`, reemplaza `<password>` y ponla en `MONGODB_URI`.

**Comprobación:** con `MONGODB_URI` en tu `.env`, `python -m bot` muestra `Almacen: MongoDB (base bot_whatsapp)` y no se detiene con un error de conexión.

## Paso 4. Servicio en Render

1. Entra a [render.com](https://render.com) con tu cuenta de GitHub y dale acceso al repositorio.
2. **New → Blueprint**, elige el repositorio. Render lee `render.yaml`.
3. Te pide los valores de las variables marcadas `sync: false`: copia los de tu `.env` (deja `DUENA_NUMERO` vacío si todavía no lo usas).
4. Aplica y espera el primer despliegue.

**Comprobación:** en **Logs** aparece `Booting worker` y `Almacen: MongoDB`. `https://<tu-servicio>.onrender.com/` muestra `ok`. El nombre exacto de la URL está arriba en el panel del servicio.

## Paso 5. Webhook en Meta

1. Abre `https://<tu-servicio>.onrender.com/` en el navegador para despertar el servicio.
2. En Meta: **WhatsApp → Configuration → Webhook → Edit**.
   - Callback URL: `https://<tu-servicio>.onrender.com/webhook`
   - Verify token: la misma palabra de `VERIFY_TOKEN`
3. Guarda y, en **Webhook fields**, suscríbete a `messages`.

**Comprobación:** Meta acepta el webhook y en los logs de Render aparece `Webhook verificado por Meta`.

## Paso 6. Prueba de punta a punta

Desde tu celular (destinatario de prueba), escríbele al número de prueba:

| Prueba | Qué haces | Qué debe pasar |
|---|---|---|
| Respuesta (RF-01) | Escribes "Hola" | Respuesta de Claude en segundos |
| Memoria (RF-02) | Preguntas algo que dependa del mensaje anterior | Responde con el contexto |
| Solo texto (RF-03) | Mandas un audio | Llega el aviso de "solo puedo leer texto" |
| Derivación (RF-04) | Escribes "quiero hablar con una persona" | Aviso de que la dueña le escribe; tu siguiente mensaje no recibe respuesta; si pusiste `DUENA_NUMERO`, llega el aviso |
| Datos (Mongo) | Abres Atlas → Browse Collections | Ves `conversaciones` con tu número y `mensajes_atendidos` |
| Dormido (D-02) | Esperas 20 min y escribes | Responde, con alrededor de un minuto de demora |

Para volver a probar la derivación con tu número, borra `pausado_hasta` de tu documento en Atlas o espera las 12 h.

## Paso 7. Token permanente

El token de API Setup vence en unas 24 h. Para uno permanente:

1. En la configuración del negocio en Meta (Business Settings), crea un **usuario del sistema** con rol de administrador.
2. Asígnale la app y la cuenta de WhatsApp.
3. Genera un token con los permisos `whatsapp_business_messaging` y `whatsapp_business_management`, sin vencimiento.
4. Reemplaza `WHATSAPP_TOKEN` en Render (Environment) y guarda: Render reinicia solo.

**Comprobación:** al día siguiente el bot sigue respondiendo y no hay errores con `code 190` en los logs.

## Paso 8. Número de tu mamá — pendiente (D-05)

No se ejecuta todavía. Opciones a decidir:

| Opción | Tu mamá sigue usando su app | Costo | Trabajo |
|---|---|---|---|
| A. Proveedor de WhatsApp con coexistencia | Sí, con el mismo número | Depende del proveedor | Se conecta el número a través del proveedor |
| B. Número nuevo solo para el bot | Su número personal no cambia; el del bot no tiene app | Un chip | Registrar el número en la Cloud API |
| C. Pasar su número actual solo a la API | No | — | No recomendado |

Además, para un número real Meta puede pedir verificación del negocio y aprobación del nombre visible, y un método de pago para mensajes que inicie el negocio (las respuestas a clientes que escriben primero no se cobran).

## Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Meta no acepta el webhook | `VERIFY_TOKEN` distinto, o el servicio estaba dormido | Iguala la palabra; abre `/` para despertarlo y reintenta |
| Log: `Peticion con firma invalida` | `APP_SECRET` mal copiado | Cópialo de nuevo desde App settings → Basic |
| Log: `Meta rechazo el envio` con `code 190` | Token vencido o mal copiado | Token nuevo, o el permanente (paso 7) |
| Log: `Meta rechazo el envio` con `131030` | Con el número de prueba, ese celular no está en los destinatarios | Agrégalo en API Setup |
| Log: `Fallo la llamada al asistente` con `401` | `ANTHROPIC_API_KEY` mala | Crea otra en platform.claude.com |
| Log: `Fallo la llamada al asistente` por saldo | Sin créditos | Recarga en platform.claude.com |
| El bot se detiene con `Faltan estas variables` | Variable vacía | Llénala en `.env` o en Render → Environment |
| Error `ServerSelectionTimeoutError` al arrancar | Atlas no deja entrar | Revisa `0.0.0.0/0`, usuario y contraseña |
| El primer mensaje tarda ~1 min | Render gratis se había dormido | Esperado (D-02) |
| Render no despliega después de un push | El CI falló (`checksPass`, D-09) | Mira la pestaña Actions y corrige |
