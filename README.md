# CallBotIA WhatsApp Bot (Meta Business)

Este proyecto es un bot de WhatsApp que se integra con Meta Business y OpenAI para automatizar conversaciones, responder mensajes, gestionar leads y agendar reuniones.

## 🧠 Descripción general

- `app.py`: servidor Flask principal.
- `database.py`: conexión a MySQL y control de leads / mensajes procesados.
- `bot_logic.py`: lógica de filtro seguro, extracción de contenido y flujo inicial.
- `ia_logic.py`: integración con OpenAI, gestión de conversaciones y ejecución de herramientas.
- `services/whatsapp_service.py`: envíos de mensajes a Meta Graph API, botones interactivos, descarga de multimedia y transcripción de audio.
- `services/mail_service.py`: envío de correos con Resend.
- `services/calendar_service.py`: creación de eventos en Google Calendar.

## 🚀 Funcionalidades principales

- Recibe webhook de Meta / WhatsApp.
- Detecta mensajes de texto, botones interactivos, imágenes y audio.
- Envía un mensaje de bienvenida con botones al primer contacto.
- Transcribe audios usando OpenAI Whisper.
- Procesa imágenes con visión en OpenAI y agrega la descripción al prompt.
- Mantiene sesiones de conversación con OpenAI usando `conversation_id`.
- Ejecuta acciones automáticas mediante funciones (`function_call`):
  - mostrar menú de botones
  - guardar contacto
  - agendar reunión
  - enviar email

## 📦 Requisitos

- Python 3.10+ recomendado
- MySQL accesible desde la app
- Cuenta Meta Business / WhatsApp Business API activa
- Cuenta OpenAI con acceso a `responses` y `whisper`
- Cuenta Resend para envío de correos
- Cuenta de servicio Google para crear eventos de Calendar

Instalar dependencias:

```bash
python -m pip install -r requirements.txt
```

## ⚙️ Variables de entorno

Crea un archivo `.env` con estas variables:

```env
VERIFY_TOKEN=tu_token_de_verificacion_meta
OPENAI_API_KEY=tu_api_key_openai
PROMPT_ID=tu_prompt_id_openai
RESEND_API_KEY=tu_api_key_resend
TOKEN_EU=token_whatsapp_eu
TOKEN_AR=token_whatsapp_ar
TOKEN_ES=token_whatsapp_es
MYSQLHOST=host_mysql
MYSQLUSER=usuario_mysql
MYSQLPASSWORD=clave_mysql
MYSQLDATABASE=nombre_bd
MYSQLPORT=3306
```

> Nota: `google_key.json` se utiliza como credencial para `calendar_service.py`. Asegúrate de tener el archivo.

## 🧩 Estructura del flujo

1. Meta envía eventos al endpoint `/webhook`.
2. `app.py` valida el webhook y recibe mensajes.
3. `bot_logic.py` extrae contenido y decide si es primer contacto.
4. Si es primer contacto, se envía un mensaje de bienvenida con botones.
5. Si el contacto ya existe, se crea o actualiza la conversación en MySQL.
6. `ia_logic.py` consulta OpenAI y procesa la respuesta.
7. Si OpenAI solicita una función, se ejecuta y el resultado puede reenviarse a la IA.
8. La respuesta final se envía a WhatsApp con `services/whatsapp_service.py`.

## 📌 Endpoints disponibles

- `GET /webhook` — verificación de Meta Webhook.
- `POST /webhook` — recibe mensajes entrantes de WhatsApp.
- `GET /dashboard` — dashboard básico de leads (requiere auth básica: `diego` / `diego`).
- `POST /eliminar_lote` — borrar leads seleccionados.
- `GET /eliminar/<id>` — borrar un lead específico.
- `GET /log` — ver logs recientes.

## 🛠️ Ejecución local

```bash
cd meta-bot
python app.py
```

O con Gunicorn (producción):

```bash
gunicorn app:app
```

## 🌐 Despliegue

El `Procfile` ya está configurado para ejecutar:

```text
web: gunicorn app:app
```

Puedes desplegar en Railway, Heroku u otra plataforma compatible con Gunicorn.

## 📁 Archivos clave

- `app.py` — servidor y rutas HTTP.
- `database.py` — pool de MySQL, creación de tablas y deduplicación de mensajes.
- `bot_logic.py` — flujo seguro de mensajes y manejo de multimedia.
- `ia_logic.py` — llamadas a OpenAI y ejecución de herramientas.
- `services/whatsapp_service.py` — envíos por WhatsApp y llamadas a Meta Graph.
- `services/mail_service.py` — envío de emails HTML vía Resend.
- `services/calendar_service.py` — agendado de reuniones en Google Calendar.

## 💡 Notas importantes

- `database.py` crea las tablas `leads` y `mensajes_procesados` si no existen.
- `if_primer_contacto` considera como "nuevo" al usuario si no escribió en las últimas 24 horas.
- En `calendar_service.py` el enlace Meet está fijo a `https://meet.google.com/mmn-munx-pts`; reemplázalo si es necesario.
- Los tokens de WhatsApp se seleccionan según el `phone_id` receptor.

## 🔒 Seguridad

- No subas el `.env` ni credenciales privadas.
- `services/google_key.json` debería mantenerse seguro.
- Ajusta los permisos de la cuenta de servicio de Google para Calendar.

### Contacto

Proyecto desarrollado como parte de CallBotIA para integración de chat inteligente en WhatsApp con Meta Business y OpenAI.
