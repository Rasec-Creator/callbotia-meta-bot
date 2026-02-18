import os
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']

def agendar_reunion(fecha_iso, nombre_cliente, telefono):
    try:
        ruta_key = 'google_key.json'
        if not os.path.exists(ruta_key):
            return {"error": "Archivo de credenciales no encontrado"}

        # Link fijo de la reunion
        MEET_LINK = "https://meet.google.com/mmn-munx-pts"

        creds = service_account.Credentials.from_service_account_file(ruta_key, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        
        # Calculamos el fin
        fecha_dt = datetime.datetime.fromisoformat(fecha_iso)
        fecha_fin_iso = (fecha_dt + datetime.timedelta(minutes=60)).isoformat()

        evento = {
            'summary': f'Reunión CallBotIA: {nombre_cliente}',
            'description': f'WhatsApp: {telefono}\nLink de la reunión: {MEET_LINK}',
            'location': MEET_LINK,
            'start': {'dateTime': fecha_iso, 'timeZone': 'America/Argentina/Buenos_Aires'},
            'end': {'dateTime': fecha_fin_iso, 'timeZone': 'America/Argentina/Buenos_Aires'},
        }
        
        evento_creado = service.events().insert(calendarId='primary', body=evento).execute()
        
        return {
            "status": "success",
            "calendar_link": evento_creado.get('htmlLink'),
            "meet_link": MEET_LINK,
            "inicio": fecha_iso,
            "cliente": nombre_cliente
        }

    except Exception as e:
        print(f"❌ ERROR EN CALENDAR: {str(e)}")
        return {"status": "error", "message": str(e)}