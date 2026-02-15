import os
from flask import Flask, request, jsonify
import requests
from openai import OpenAI
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import json

load_dotenv()
app = Flask(__name__)

# Configuracion
TOKEN = os.getenv("TOKEN")
PHONE_ID = os.getenv("PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PROMPT_ID = os.getenv("PROMPT_ID")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Configuracion de Google
SCOPES = ['https://www.googleapis.com/auth/calendar']

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

def agendar_reunion(fecha_iso, nombre_cliente, telefono):
    """
    Funcion que llama la IA para crear el evento.
    fecha_iso debe venir en formato '2026-02-18T10:00:00'
    """
    print(f"📅 Intentando agendar: {nombre_cliente} ({telefono}) para el {fecha_iso}")
    try:
        # Autenticación
        if not os.path.exists('google_key.json'):
            print("❌ ERROR: No se encontró el archivo google_key.json")
            return "Error interno: Falta configuración de Google."

        creds = service_account.Credentials.from_json_keyfile_name(
            'google_key.json', scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)

        evento = {
            'summary': f'Reunión CallBotIA: {nombre_cliente}',
            'description': f'Consulta técnica de lead de WhatsApp. Tel: {telefono}',
            'start': {'dateTime': fecha_iso, 'timeZone': 'America/Argentina/Buenos_Aires'},
            'end': {
                'dateTime': (datetime.datetime.fromisoformat(fecha_iso) + datetime.timedelta(minutes=30)).isoformat(),
                'timeZone': 'America/Argentina/Buenos_Aires'
            },
        }

        print("🚀 Enviando petición a Google Calendar API...")
        evento_creado = service.events().insert(calendarId='reuniones.callbotia@gmail.com', body=evento).execute()
        
        url_reunion = evento_creado.get('htmlLink')
        print(f"✅ ¡Éxito! Reunión creada: {url_reunion}")
        return f"Reunión agendada con éxito: {url_reunion}"

    except Exception as e:
        print(f"❌ ERROR en agendar_reunion: {str(e)}")
        return f"Error al agendar: {e}"

def consultar_ia(texto_usuario, conversation_id, phone_number):
    try:
        response = client.responses.create(
            model="gpt-4o-mini", 
            prompt={"id": PROMPT_ID},
            conversation=conversation_id, 
            input=texto_usuario 
        )
        
        # Analizamos qué decidió hacer la IA
        for item in response.output:
            # Caso 1: La IA decide que DEBE llamar a la función
            if item.type == 'call' and item.call.name == 'agendar_reunion':
                args = item.call.arguments
                if isinstance(args, str): args = json.loads(args)
                
                print(f"📞 ¡KAT-IA ACTIVÓ LA FUNCIÓN! Datos capturados: {args}")
                
                # Ejecutamos la lógica de Google Calendar
                resultado = agendar_reunion(
                    fecha_iso=args['fecha_hora'], 
                    nombre_cliente=args['nombre_cliente'],
                    telefono=phone_number
                )
                
                print(f"📤 Enviando resultado de la función a la IA: {resultado}")
                
                # Segunda vuelta para que la IA confirme al usuario
                final_response = client.responses.create(
                    model="gpt-4o-mini",
                    conversation=conversation_id,
                    input=resultado 
                )
                
                respuesta_final = final_response.output[0].content[0].text
                print(f"💬 Confirmación final de Kat-IA: {respuesta_final}")
                return respuesta_final

            # Caso 2: La IA responde un mensaje común (chat)
            if item.type == 'message' and item.role == 'assistant':
                texto_respuesta = item.content[0].text
                print(f"💬 Kat-IA respondió sin llamar a funciones: {texto_respuesta[:50]}...")
                return texto_respuesta
                
        print("⚠️ Advertencia: La IA no devolvió ni mensaje ni llamada a función.")
        return "Recibí una respuesta pero no contenía texto."

    except Exception as e:
        print(f"❌ ERROR CRÍTICO en consultar_ia: {str(e)}")
        return "Hubo un error en la comunicación, por favor intente más tarde."


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
            respuesta_ia = consultar_ia(texto_usuario, conv_id, numero_destino)
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

@app.route('/dashboard')
def ver_dashboard():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        # Traemos todos los leads ordenados por la última vez que escribieron
        cur.execute("SELECT id, telefono, ultimo_mensaje, fecha_actualizacion FROM leads ORDER BY fecha_actualizacion DESC")
        leads = cur.fetchall()
        cur.close()
        conn.close()

        # Armamos un HTML ultra básico para que se vea ordenado
        html = """
        <html>
        <head><title>Dashboard CallBotIA</title></head>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Leads de CallBotIA - Kat-IA</h2>
            <table border="1" style="width:100%; border-collapse: collapse;">
                <tr style="background-color: #f2f2f2;">
                    <th>ID</th>
                    <th>Teléfono</th>
                    <th>Último Mensaje</th>
                    <th>Fecha</th>
                </tr>
        """
        for lead in leads:
            html += f"<tr><td>{lead[0]}</td><td>{lead[1]}</td><td>{lead[2]}</td><td>{lead[3]}</td></tr>"
        
        html += "</table></body></html>"
        return html
    except Exception as e:
        return f"<h3>Error al cargar el dashboard:</h3><p>{e}</p>"

if __name__ == '__main__':
    init_db() # Inicializamos la tabla
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)