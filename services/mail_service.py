import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def enviar_mail_smtp(destinatario, asunto, contenido_ia):
    # Configuración de tu server (ej: Gmail o Outlook)
    SMTP_SERVER = "C2720203.ferozo.com"
    SMTP_PORT = 465
    SENDER_EMAIL = "agent@callbotia.com"
    SENDER_PASSWORD = "J@dEGO*8cD" 

    # Armamos el HTML con un template fijo
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

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = destinatario
    msg['Subject'] = asunto
    msg.attach(MIMEText(html, 'html'))

    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, destinatario, msg.as_string())
        
        server.quit()
        print("DEBUG: Mail enviado")
        return True
    except smtplib.SMTPAuthenticationError:
        print("DEBUG: Error de autenticacion")
        return False
    except Exception as e:
        print(f"DEBUG: Error inesperado: {str(e)}")
        return False