import requests
import os
from dotenv import load_dotenv 
load_dotenv()

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
    try:
        requests.post(url, headers=headers, json=data)
    except Exception as e:
        print(f"Error en la bienvenida: {e}")

def enviar_botones_dinamicos(to, texto, lista_botones):
    url = f"https://graph.facebook.com/v18.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    
    botones_formateados = []
    
    # whatsapp solo permite hasta 3 botones, limitemos la lista
    for i, btn in enumerate(lista_botones[:3]):
        btn_id = btn.get('id', f"btn_dyn_{i}")
        titulo = btn.get('titulo', 'Opción')
        
        # si supera los 20, cortamos y ponemos puntos suspensivos
        if len(titulo) > 20:
            titulo = titulo[:17] + "..."
        
        botones_formateados.append({
            "type": "reply",
            "reply": {
                "id": btn_id,
                "title": titulo
            }
        })

    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": texto},
            "action": {
                "buttons": botones_formateados
            }
        }
    }
    
    response = requests.post(url, headers=headers, json=data)
    res_json = response.json()
    if response.status_code != 200:
        print(f"ERROR META: {res_json}")
        
    return res_json