import datetime
import resend
import os
from logger import get_logger

logger = get_logger()
# Configuramos la API Key desde Railway
resend.api_key = os.getenv("RESEND_API_KEY")

def enviar_mail_resend(destinatario, asunto, contenido_ia):
    # template
    html = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <title>{asunto}</title>
</head>
<body style="font-family:'Roboto',Arial,sans-serif;margin:0;padding:0;">
    <div style="max-width:600px;margin:20px auto;background-color:#1e1e1e;border-radius:10px;box-shadow:0 4px 20px rgba(0,0,0,0.6);overflow:hidden;">
        <div style="background-color:#cee9fe;padding:20px;text-align:center;">
            <h1 style="color:#333333;font-size:26px;margin:0;">{asunto}</h1>
        </div>
        <div style="padding:30px;color:#e0e0e0;font-size:16px;line-height:1.6;">
            <div style="margin:0 0 20px;">{contenido_ia}</div>
            <p style="margin:20px 0 0;">Si tenés alguna duda adicional, visítanos en <a href="https://callbotia.com" style="color:#3399ff;text-decoration:none;">callbotia.com</a>.</p>
        </div>
        <div style="background-color:#cee9fe;padding:15px;text-align:center;color:#333333;font-size:14px;font-weight:bold;">
            <p style="margin:0;">© 2026 CallBotIA. Todos los derechos reservados.</p>
            <p style="margin:5px 0 0;"><a href="https://callbotia.com" style="color:#333333;text-decoration:none;font-weight:bold;">Visita CallBotIA</a></p>
        </div>
    </div>
</body>
</html>
    """
    try:
        params = {
            "from": "CallBotIA <agent@callbotia.com>",
            "to": [destinatario],
            "subject": asunto,
            "html": html,
        }

        resend.Emails.send(params)
        logger.info("DEBUG: Mail enviado exitosamente a", destinatario)
        return True
    except Exception as e:
        logger.info(f"DEBUG: Error inesperado en Resend: {str(e)}")
        return False
    
def enviar_mail_reunion(email_destinatario, nombre_cliente, fecha_dt, fecha_fin_dt, resumen, meet_link):
    """
    genera el html y el archivo .ics para enviar la confirmacion de la reunion via resend.
    """
    try:
        fecha_formateada = fecha_dt.strftime('%d/%m/%Y') + " a las " + fecha_dt.strftime('%H:%M')
        asunto_mail = "Reunión con CallBotIA"
        
        contenido_html = f"""
        <!DOCTYPE html>
        <html lang='es'>
        <head><meta charset='UTF-8'></head>
        <body style="font-family:Arial,sans-serif;margin:0;padding:0;background-color:#f4f4f4;">
            <div style='max-width:600px;margin:20px auto;background-color:#1e1e1e;border-radius:10px;overflow:hidden;'>
                <div style='background-color:#cee9fe;padding:20px;text-align:center;'>
                    <h1 style='color:#333333;font-size:26px;margin:0;'>{asunto_mail}</h1>
                </div>
                <div style='padding:30px;color:#e0e0e0;'>
                    ¡Hola! Un gusto saludarte {nombre_cliente}. <br><br> 
                    Te confirmamos que hemos agendado tu reunión para el día <strong>{fecha_formateada}</strong> hs. <br><br> 
                    <strong>Motivo de la consulta:</strong> {resumen} <br><br>
                    <strong>Link de la reunión:</strong> <a href='{meet_link}' style='color:#cee9fe; font-weight:bold;'>Ingresar a Google Meet</a><br>
                    <small>(Podés guardar este link para el día de la charla)</small>
                    <br><br>
                    <hr style='border:0; border-top:1px solid #333; margin:20px 0;'>
                    Cualquier duda o modificación, por favor comunícate con <strong>Lucas L.</strong> a <a href='mailto:lucasl@callbotia.com' style='color:#cee9fe;'>lucasl@callbotia.com</a>. <br><br>
                    ¡Nos vemos pronto!
                </div>
                <div style='background-color:#cee9fe;padding:15px;text-align:center;color:#333333;'>
                    © 2026 CallBotIA
                </div>
            </div>
        </body>
        </html>
        """
        dtstart = fecha_dt.strftime('%Y%m%dT%H%M%S')
        dtend = fecha_fin_dt.strftime('%Y%m%dT%H%M%S')
        today = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')

        resumen_limpio = resumen.replace('\n', '\\n')

        # estructuramos el calendario sin espacios iniciales molestos
        ics_content = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//CallBotIA//NONSGML Event//EN\r\n"
            "CALSCALE:GREGORIAN\r\n"
            "BEGIN:VEVENT\r\n"
            f"DTSTAMP:{today}\r\n"
            f"DTSTART:{dtstart}\r\n"
            f"DTEND:{dtend}\r\n"
            f"SUMMARY:{asunto_mail}\r\n"
            f"DESCRIPTION:{resumen_limpio}\r\n"
            f"LOCATION:Google Meet: {meet_link}\r\n"
            f"URL:{meet_link}\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR"
        )

        email_params = {
            "from": "CallBotIA <agent@callbotia.com>",
            "to": [email_destinatario],
            "subject": asunto_mail,
            "html": contenido_html,
            "attachments": [
                {
                    "filename": "reunion_callbotia.ics",
                    "content": list(ics_content.encode('utf-8')),
                }
            ]
        }
        resend.Emails.send(email_params)
        logger.info(f"Mail con adjunto ICS enviado correctamente a {email_destinatario}")
        return True

    except Exception as e:
        logger.error(f"Error al enviar mail por Resend: {str(e)}", exc_info=True)
        return False