import os
from flask import Flask, request, jsonify
import requests
import time
from openai import OpenAI
from dotenv import load_dotenv

# Cargamos las envs
load_dotenv()

app = Flask(__name__)

# Configuracion desde variables de entorno
TOKEN = os.getenv("TOKEN")
PHONE_ID = os.getenv("PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PROMPT_ID = os.getenv("PROMPT_ID")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Mapeo de nro de teléfono a conversation_id
conversations_db = {}

def obtener_o_crear_conversacion(phone_number):
    if phone_number not in conversations_db:
        # En la nueva API, creamos una 'conversation'
        conv = client.conversations.create()
        conversations_db[phone_number] = conv.id
    return conversations_db[phone_number]

def consultar_ia(texto_usuario, conversation_id):
    try:
        response = client.responses.create(
            model="gpt-4o-mini", 
            prompt={"id": PROMPT_ID},
            conversation=conversation_id, 
            input=texto_usuario 
        )
        #print(f"Respuesta cruda de Responses API: {response}")
        
        # La respuesta es una lista de ítems; buscamos el texto del asistente
        for item in response.output:
            if item.type == 'message' and item.role == 'assistant':
                return item.content[0].text
        return "Recibí una respuesta pero no contenía texto."

    except Exception as e:
        print(f"error con responses api: {e}")
        return "Hubo un error en mi nuevo cerebro de Responses API."

@app.route('/webhook', methods=['POST'])
def recibir_mensajes():
    body = request.get_json()
    value = body.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {})
    
    if 'messages' in value:
        mensaje = value['messages'][0]
        if mensaje.get('type') == 'text':
            texto_usuario = mensaje['text']['body']
            numero_que_llega = mensaje['from']

            # Tu parche de Argentina
            numero_destino = "54" + numero_que_llega[3:] if numero_que_llega.startswith("549") else numero_que_llega

            # Usamos el nuevo sistema de Conversaciones
            conv_id = obtener_o_crear_conversacion(numero_destino)
            respuesta_ia = consultar_ia(texto_usuario, conv_id)
            
            enviar_mensaje(numero_destino, respuesta_ia)
            
    return jsonify({"status": "ok"}), 200


 # Logica de verificacion
@app.route('/webhook', methods=['GET'])
def webhook():
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return challenge, 200
        return "error", 403

def enviar_mensaje(to, text):
    url = f"https://graph.facebook.com/v18.0/{PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {TOKEN}", 
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    response = requests.post(url, headers=headers, json=data)
    print(f"estado envio: {response.status_code}")
    return response.json()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)