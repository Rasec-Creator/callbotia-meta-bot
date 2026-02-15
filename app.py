import os
from flask import Flask, request, jsonify
import requests
from openai import OpenAI
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor

load_dotenv()
app = Flask(__name__)

# Configuracion
TOKEN = os.getenv("TOKEN")
PHONE_ID = os.getenv("PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PROMPT_ID = os.getenv("PROMPT_ID")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            telefono TEXT UNIQUE NOT NULL,
            conversation_id TEXT,
            ultimo_mensaje TEXT,
            fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()

def obtener_o_crear_conversacion(phone_number, texto_usuario):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    cur.execute("SELECT conversation_id FROM leads WHERE telefono = %s", (phone_number,))
    result = cur.fetchone()
    
    if result and result['conversation_id']:
        conv_id = result['conversation_id']
        cur.execute('''
            UPDATE leads SET ultimo_mensaje = %s, fecha_actualizacion = CURRENT_TIMESTAMP 
            WHERE telefono = %s
        ''', (texto_usuario, phone_number))
    else:
        # En la Responses API creamos una conversation
        conv = client.conversations.create()
        conv_id = conv.id
        cur.execute('''
            INSERT INTO leads (telefono, conversation_id, ultimo_mensaje) 
            VALUES (%s, %s, %s)
        ''', (phone_number, conv_id, texto_usuario))
    
    conn.commit()
    cur.close()
    conn.close()
    return conv_id

def consultar_ia(texto_usuario, conversation_id):
    try:
        # Usamos la Responses API para mantener la memoria
        response = client.responses.create(
            model="gpt-4o-mini", 
            prompt={"id": PROMPT_ID},
            conversation=conversation_id, 
            input=texto_usuario 
        )
        
        for item in response.output:
            if item.type == 'message' and item.role == 'assistant':
                return item.content[0].text
        return "Recibí una respuesta pero no contenía texto."
    except Exception as e:
        print(f"error con responses api: {e}")
        return "Hubo un error en la comunicación, por favor intente más tarde."

@app.route('/webhook', methods=['POST'])
def recibir_mensajes():
    body = request.get_json()
    value = body.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {})
    
    if 'messages' in value:
        mensaje = value['messages'][0]
        if mensaje.get('type') == 'text':
            texto_usuario = mensaje['text']['body']
            numero_que_llega = mensaje['from']
            numero_destino = "54" + numero_que_llega[3:] if numero_que_llega.startswith("549") else numero_que_llega

            # CORREGIDO: Ahora pasamos ambos argumentos
            conv_id = obtener_o_crear_conversacion(numero_destino, texto_usuario)
            respuesta_ia = consultar_ia(texto_usuario, conv_id)
            enviar_mensaje(numero_destino, respuesta_ia)
            
    return jsonify({"status": "ok"}), 200

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
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
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
    init_db() # Inicializamos la tabla
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)