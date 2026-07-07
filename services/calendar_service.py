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
        
        # armamos los strings formateados en iso real que google exige
        nueva_fecha_inicio = fecha_dt.isoformat()
        nueva_fecha_fin = fecha_fin_dt.isoformat()

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
                (nueva_fecha_inicio, duracion_minutos, nueva_fecha_inicio, nueva_fecha_fin, duracion_minutos, nueva_fecha_fin)
            )
            row = cur.fetchone()
            
            if row:
                return {
                    "status": "error", 
                    "message": "Lo sentimos, este horario ya está reservado. Por favor, elige otro."
                }

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

            MEET_LINK = "https://meet.google.com/mmn-munx-pts"

            evento = {
                'summary': f'Reunión CallBotIA: {nombre_cliente}',
                'description': f'WhatsApp: +{telefono}\nMotivo: {resumen}',
                'location': f'{MEET_LINK}',
                'start': {'dateTime': nueva_fecha_inicio, 'timeZone': 'America/Argentina/Buenos_Aires'},
                'end': {'dateTime': nueva_fecha_fin, 'timeZone': 'America/Argentina/Buenos_Aires'},
            }
            
            service.events().insert(
                calendarId='reuniones.callbotia@gmail.com', 
                body=evento
            ).execute()

            cur.execute(
                "INSERT INTO meetings (telefono, fecha_hora) VALUES (?, ?)",
                (telefono, nueva_fecha_inicio)
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
                "fecha_confirmada": nueva_fecha_inicio,
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