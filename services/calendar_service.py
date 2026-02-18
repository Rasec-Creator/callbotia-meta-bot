import os
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']

def agendar_reunion(fecha_iso, nombre_cliente, telefono):
    try:
        creds = service_account.Credentials.from_service_account_file('google_key.json', scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        evento = {
            'summary': f'Reunión CallBotIA: {nombre_cliente}',
            'description': f'WhatsApp: {telefono}',
            'start': {'dateTime': fecha_iso, 'timeZone': 'America/Argentina/Buenos_Aires'},
            'end': {
                'dateTime': (datetime.datetime.fromisoformat(fecha_iso) + datetime.timedelta(minutes=60)).isoformat(),
                'timeZone': 'America/Argentina/Buenos_Aires'
            },
        }
        evento_creado = service.events().insert(calendarId='primary', body=evento).execute()
        return f"Reunión agendada con éxito: {evento_creado.get('htmlLink')}"
    except Exception as e:
        return f"Error al agendar: {e}"