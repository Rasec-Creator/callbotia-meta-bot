import requests
import os

PHONE_ID = os.getenv("PHONE_ID")
TOKEN = os.getenv("TOKEN")

def enviar_mensaje(to, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()
def enviar_botones_dinamicos(to, texto, lista_botones):
    url = f"https://graph.facebook.com/v18.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    
    formatted_buttons = []
    for btn in lista_botones:
        formatted_buttons.append({
            "type": "reply",
            "reply": {
                "id": btn['id'],
                "title": btn['titulo'][:20]
            }
        })

    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": texto},
            "action": {"buttons": formatted_buttons}
        }
    }
    return requests.post(url, headers=headers, json=data).json()

def enviar_botones_bienvenida(to, nombre_usuario):
    url = f"https://graph.facebook.com/v18.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"Hola {nombre_usuario}, ¿Cómo estás? 🙋‍♂️ Soy KatIA, asistente virtual de CallBotIA, si quieres, además de escribirme, también puedes interactuar conmigo en 'Modo Botones' 📊 ¿Quieres continuar? 👍"
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "btn_si",
                            "title": "¡Sí, dale! 👍"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "btn_no",
                            "title": "No, prefiero chat"
                        }
                    }
                ]
            }
        }
    }
    requests.post(url, headers=headers, json=data)