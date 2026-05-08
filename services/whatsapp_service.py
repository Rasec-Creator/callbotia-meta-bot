import base64
import requests
import os
from dotenv import load_dotenv 
import requests
from openai import OpenAI
import logging

logger = logging.getLogger("KatIA")
load_dotenv()
TOKENeu = os.getenv("TOKEN_EU")
TOKENar = os.getenv("TOKEN_AR")
TOKENes = os.getenv("TOKEN_ES")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def enviar_mensaje(phone_id,to, text):
    token_a_usar = obtener_token_por_phone_id(phone_id)
    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token_a_usar}", "Content-Type": "application/json"}
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()

def enviar_botones_bienvenida(phone_id,to, nombre_usuario):
    token_a_usar = obtener_token_por_phone_id(phone_id)
    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token_a_usar}", "Content-Type": "application/json"}
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
        logger.info(f"Error en la bienvenida: {e}")

def enviar_botones_dinamicos(phone_id,to, texto, lista_botones):
    token_a_usar = obtener_token_por_phone_id(phone_id)
    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token_a_usar}", "Content-Type": "application/json"}
    
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
        logger.info(f"ERROR META: {res_json}")
        
    return res_json

def obtener_media_url(media_id,phone_id):
    token_a_usar = obtener_token_por_phone_id(phone_id)
    url = f"https://graph.facebook.com/v18.0/{media_id}"
    headers = {"Authorization": f"Bearer {token_a_usar}"}
    res = requests.get(url, headers=headers)
    return res.json().get('url')

def descargar_y_codificar(url,phone_id):
    token_a_usar = obtener_token_por_phone_id(phone_id)
    headers = {"Authorization": f"Bearer {token_a_usar}"}
    img_res = requests.get(url, headers=headers)
    # La pasamos a base64 para que OpenAI la reciba 
    return base64.b64encode(img_res.content).decode('utf-8')

# descarga un audio de la URL de Meta y lo transcribe con Whisper.
def transcribir_audio(url,phone_id):
    token_a_usar = obtener_token_por_phone_id(phone_id)
    headers = {"Authorization": f"Bearer {token_a_usar}"}
    temp_filename = "temp_audio.ogg"
    try:
        # bajamos el archivo de meta
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            logger.info(f"ERROR DESCARGA: {response.status_code}")
            return None

        # guardamos
        with open(temp_filename, "wb") as f:
            f.write(response.content)

        # mandamos a whisper
        with open(temp_filename, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
        
        # borramos el archivo para no llenar la memoria
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        return transcription.text

    except Exception as e:
        logger.info(f"ERROR EN TRANSCRIPCION: {e}")
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        return None
    
def obtener_token_por_phone_id(phone_id):
    # IDs de Argentina / Global
    print("phone: ",phone_id)
    ids_argentina = ["918005154740840", "1027702013752458"] # 11 2049-5801 // 2346 45-4493
    # ID de España
    id_espana = "635147226357107" # +34 608 33 27 73
    id_eu = "1035046919698899" # +1 555-954-6766

    if str(phone_id) == id_espana:
        return TOKENes
    elif str(phone_id) in ids_argentina:
        return TOKENar
    elif str(phone_id) == id_eu: # Reemplaza con el ID real de la UE
        return TOKENeu
    else:
        # Por defecto usamos el TOKEN estándar si no coincide ninguno
        return TOKENar

        