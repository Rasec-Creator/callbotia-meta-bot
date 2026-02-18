import os, json
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI
from database import init_db, check_if_processed, obtener_o_crear_conv, if_primer_contacto
from services.whatsapp_service import enviar_mensaje, enviar_botones_bienvenida 
from services.calendar_service import agendar_reunion

load_dotenv()
app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PROMPT_ID = os.getenv("PROMPT_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

def consultar_ia(texto, conv_id, phone):
    try:
        response = client.responses.create(
            model="gpt-4o-mini", prompt={"id": PROMPT_ID},
            conversation=conv_id, input=texto 
        )
        for item in response.output:
            if item.type == 'function_call' and item.name == 'agendar_reunion':
                args = json.loads(item.arguments)
                res = agendar_reunion(args['fecha_hora'], args['nombre_cliente'], phone)
                client.responses.create(
                    model="gpt-4o-mini", conversation=conv_id,
                    input=[{"type": "function_call_output", "call_id": item.call_id, "output": json.dumps({"resultado": res})}]
                )
                return f"Confirmado: {res}"
            if item.type == 'message':
                return item.content[0].text
        return "Kat-IA fuera de servicio."
    except Exception as e:
        return f"Error técnico: {e}"

@app.route('/webhook', methods=['POST'])
def recibir_mensajes():
    body = request.get_json()
    value = body.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {})
    
    if 'messages' in value:
        mensaje = value['messages'][0]
        msg_id = mensaje.get('id') 
        contacto = value.get('contacts', [{}])[0]
        nombre_wa = contacto.get('profile', {}).get('name', 'Usuario') # 'Usuario' por si no tiene nombre

        if check_if_processed(msg_id):
            return jsonify({"status": "skipped"}), 200

        numero = mensaje['from']
        to = "54" + numero[3:] if numero.startswith("549") else numero
        
        texto = ""
        if mensaje.get('type') == 'text':
            texto = mensaje['text']['body']
        elif mensaje.get('type') == 'interactive':
            texto = mensaje['interactive']['button_reply']['title']

        if texto:
            # CHEQUEO DE ORO: ¿Es la primera vez que nos escribe?
            if if_primer_contacto(to):
                print(f"🌟 Nuevo lead detectado: {to}")
                # Enviamos el saludo inicial con botones de Lum-IA
                enviar_botones_bienvenida(to, nombre_wa)
            else:
                # Ya es un cliente conocido, seguimos la charla con OpenAI
                c_id = obtener_o_crear_conv(to, texto, client)
                res_ia = consultar_ia(texto, c_id, to)
                enviar_mensaje(to, res_ia)
                
    return jsonify({"status": "ok"}), 200

@app.route('/webhook', methods=['GET'])
def webhook_verificar():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge'), 200
    return "error", 403

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))