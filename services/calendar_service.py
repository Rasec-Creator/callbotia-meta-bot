import os
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']

def agendar_reunion(fecha_iso, nombre_cliente, telefono):
    try:
        ruta_key = 'google_key.json'
        if not os.path.exists(ruta_key):
            print(f"ERROR: No se encontró el archivo {ruta_key}")
            return {"error": "Archivo de credenciales no encontrado"}

        MEET_LINK = "https://meet.google.com/mmn-munx-pts"

        # 1. Verificación de Credenciales
        creds = service_account.Credentials.from_service_account_file(ruta_key, scopes=SCOPES)
        print(f"Credenciales cargadas. Email de cuenta de servicio: {creds.service_account_email}")

        service = build('calendar', 'v3', credentials=creds)
        
        fecha_dt = datetime.datetime.fromisoformat(fecha_iso)
        fecha_fin_iso = (fecha_dt + datetime.timedelta(minutes=60)).isoformat()

        # 2. Verificación del Paylod
        print(f"Payload preparado:")
        print(f"   - Inicio: {fecha_iso}")
        print(f"   - Fin: {fecha_fin_iso}")
        print(f"   - Cliente: {nombre_cliente}")

        evento = {
            'summary': f'Reunión CallBotIA: {nombre_cliente}',
            'description': f'WhatsApp: {telefono}\nLink de la reunión: {MEET_LINK}',
            'location': MEET_LINK,
            'start': {'dateTime': fecha_iso, 'timeZone': 'America/Argentina/Buenos_Aires'},
            'end': {'dateTime': fecha_fin_iso, 'timeZone': 'America/Argentina/Buenos_Aires'},
        }
        
        # 3. Intento de Inserción
        # NOTA: Usamos 'primary' si la cuenta de servicio es dueña o le compartiste TU calendario
        print(f"📡 Enviando solicitud a Google Calendar API...")
        evento_creado = service.events().insert(calendarId='reuniones.callbotia@gmail.com', body=evento).execute()
        
        print(f"✅ EVENTO CREADO EXITOSAMENTE")
        print(f"🔗 ID del Evento: {evento_creado.get('id')}")
        print(f"🔗 Link público: {evento_creado.get('htmlLink')}")
        print(f"--- 📅 DEBUG CALENDAR END ---\n")

        return {
            "status": "success",
            "calendar_link": evento_creado.get('htmlLink'),
            "meet_link": MEET_LINK,
            "inicio": fecha_iso,
            "cliente": nombre_cliente
        }

    except Exception as e:
        print(f"❌ ERROR CRÍTICO EN CALENDAR: {str(e)}")
        # Si el error es 404, es porque 'primary' no existe para la cuenta de servicio
        return {"status": "error", "message": str(e)}