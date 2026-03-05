import resend
import os

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
        # Una vez verificado el dominio, podés usar tu mail oficial
        # Si todavía no lo verificaste, usá "onboarding@resend.dev" para probar
        params = {
            "from": "CallBotIA <agent@callbotia.com>",
            "to": [destinatario],
            "subject": asunto,
            "html": html,
        }

        resend.Emails.send(params)
        print("DEBUG: Mail enviado via API")
        return True
    except Exception as e:
        print(f"DEBUG: Error inesperado en Resend: {str(e)}")
        return False