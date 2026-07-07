import json
import os
import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
import sqlite3
from database import get_db_connection
from services.mail_service import enviar_mail_reunion
from logger import get_logger

logger = get_logger()
SCOPES = ['https://www.googleapis.com/auth/calendar']

def agendar_reunion(fecha_iso, nombre_cliente, telefono, email=None, resumen='Consulta general'):
    try:
        fecha_iso_limpia = fecha_iso.replace(' ', 'T')
        fecha_dt = datetime.datetime.fromisoformat(fecha_iso_limpia)        
        # obtenemos el dia de la semana (1 = lunes, 7 = domingo)
        dia_semana = fecha_dt.isoweekday() 
        hora_str = fecha_dt.strftime('%H:%M')

        if dia_semana > 5:
            return {
                "status": "error", 
                "message": "Lo sentimos, solo atendemos de lunes a viernes. Por favor, elegí otro día."
            }

        if hora_str < '09:00' or hora_str > '16:00':
            return {
                "status": "error", 
                "message": "Nuestro horario de atención es de 09:00 a 16:00 hs. Por favor, elegí un horario dentro de ese rango."
            }

        # calculamos la fecha de fin sumando los 30 minutos de duracion standar
        duracion_minutos = 30
        fecha_fin_dt = fecha_dt + datetime.timedelta(minutes=duracion_minutos)
        
        nueva_fecha_inicio_google = fecha_dt.isoformat()
        nueva_fecha_fin_google = fecha_fin_dt.isoformat()

        fecha_db_inicio = fecha_dt.strftime('%Y-%m-%d %H:%M:%S')
        fecha_db_fin = fecha_fin_dt.strftime('%Y-%m-%d %H:%M:%S')

        google_creds_json = os.getenv("GOOGLE_CREDENTIALS")
        if not google_creds_json:
            logger.error("ERROR: No se encontró la variable de entorno GOOGLE_CREDENTIALS")
            return {"status": "error", "message": "Credenciales de Google no configuradas"}

        try:
            creds_dict = json.loads(google_creds_json)
            SCOPES = ['https://www.googleapis.com/auth/calendar']
            creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            service = build('calendar', 'v3', credentials=creds)
        except json.JSONDecodeError as json_err:
            logger.error(f"Error al parsear el JSON de GOOGLE_CREDENTIALS: {json_err}")
            return {"status": "error", "message": "Formato de credenciales invalido"}

        CALENDAR_ID = 'reuniones.callbotia@gmail.com'

        try:
            # listamos eventos que se solapen con nuestro rango (formato ISO con zona horaria)
            events_result = service.events().list(
                calendarId=CALENDAR_ID,
                timeMin=nueva_fecha_inicio_google + "-03:00", # offset de Argentina
                timeMax=nueva_fecha_fin_google + "-03:00",
                singleEvents=True
            ).execute()
            
            events = events_result.get('items', [])
            
            if events:
                logger.info(f"Cruce detectado en Google Calendar para el horario: {fecha_db_inicio}")
                return {
                    "status": "error",
                    "message": "Lo sentimos, este horario ya está ocupado en nuestra agenda. Por favor, elige otro."
                }
        except Exception as api_err:
            logger.error(f"Error al validar contra Google Calendar API: {api_err}", exc_info=True)
            return {"status": "error", "message": "No se pudo verificar la disponibilidad en el calendario central."}

        conn = get_db_connection()
        if not conn:
            return {"status": "error", "message": "Error de conexion con la base de datos local"}
        
        try:
            cur = conn.cursor()
            check_sql = """
                SELECT id FROM meetings 
                WHERE (
                    (fecha_hora <= ? AND datetime(fecha_hora, ? || ' minutes') > ?)
                    OR 
                    (fecha_hora < ? AND datetime(fecha_hora, ? || ' minutes') >= ?)
                )
            """
            cur.execute(
                check_sql, 
                (fecha_db_inicio, duracion_minutos, fecha_db_inicio, fecha_db_fin, duracion_minutos, fecha_db_fin)
            )
            row = cur.fetchone()
            
            if row:
                return {
                    "status": "error", 
                    "message": "Lo sentimos, este horario ya está reservado. Por favor, elige otro."
                }

            MEET_LINK = "https://meet.google.com/mmn-munx-pts"

            evento = {
                'summary': f'Reunión CallBotIA: {nombre_cliente}',
                'description': f'WhatsApp: +{telefono}\nMotivo: {resumen}',
                'location': f'{MEET_LINK}',
                'start': {'dateTime': nueva_fecha_inicio_google, 'timeZone': 'America/Argentina/Buenos_Aires'},
                'end': {'dateTime': nueva_fecha_fin_google, 'timeZone': 'America/Argentina/Buenos_Aires'},
            }
            
            service.events().insert(
                calendarId=CALENDAR_ID, 
                body=evento
            ).execute()

            cur.execute(
                "INSERT INTO meetings (telefono, fecha_hora) VALUES (?, ?)",
                (telefono, fecha_db_inicio)
            )
            
            if email:
                cur.execute("UPDATE leads SET email = ? WHERE telefono = ?", (email, telefono))
                
            conn.commit()
            
            if email:
                enviar_mail_reunion(
                    email_destinatario=email,
                    nombre_cliente=nombre_cliente,
                    fecha_dt=fecha_dt,
                    fecha_fin_dt=fecha_fin_dt,
                    resumen=resumen,
                    meet_link=MEET_LINK
                )

            return {
                "status": "success",
                "message": "Reunion guardada y mail enviado",
                "meet_link": MEET_LINK,
                "fecha_confirmada": fecha_db_inicio,
                "cliente": nombre_cliente
            }

        except sqlite3.Error as db_err:
            logger.error(f"Error ejecutando queries en sqlite: {db_err}", exc_info=True)
            return {"status": "error", "message": f"Error interno en la db: {str(db_err)}"}
        finally:
            conn.close()

    except Exception as e:
        logger.info(f" ERROR CRÍTICO EN AGENDAR_REUNION: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e)}