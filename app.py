import os, json
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI
from psycopg2.extras import DictCursor
from database import init_db, get_db_connection, check_if_processed, obtener_o_crear_conv, if_primer_contacto
from services.whatsapp_service import enviar_mensaje, enviar_botones_bienvenida, enviar_botones_dinamicos
from services.calendar_service import agendar_reunion

load_dotenv()
app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PROMPT_ID = os.getenv("PROMPT_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

def consultar_ia(texto, conv_id, phone):
    try:
        # Primera llamada para recibir las instrucciones de la IA
        response = client.responses.create(
            model="gpt-4o-mini", prompt={"id": PROMPT_ID},
            conversation=conv_id, input=texto 
        )
        
        outputs_pendientes = []
        texto_final = None

        for item in response.output:
            c_id = getattr(item, 'id', None)

            if item.type == 'function_call':
                args = json.loads(item.arguments)
                
                if item.name == 'mostrar_menu_botones':
                    enviar_botones_dinamicos(phone, args['texto_cuerpo'], args['botones'])
                    
                    # Guardamos el output para enviarlo después del bucle
                    outputs_pendientes.append({
                        "type": "function_call_output",
                        "call_id": c_id,
                        "output": "ok"
                    })

                elif item.name == 'agendar_reunion':
                    res = agendar_reunion(args['fecha_hora'], args['nombre_cliente'], phone)
                    outputs_pendientes.append({
                        "type": "function_call_output",
                        "call_id": c_id,
                        "output": json.dumps({"resultado": res})
                    })
                    texto_final = f"Confirmado: {res}"

            elif item.type == 'message':
                texto_final = item.content[0].text

        # Si hubo funciones, hacemos una SEGUNDA llamada para cerrar el estado de la conversación
        if outputs_pendientes:
            client.responses.create(
                model="gpt-4o-mini",
                conversation=conv_id,
                input=outputs_pendientes 
            )
        
        return texto_final

    except Exception as e:
        print(f"❌ Error en IA: {e}")
        return None

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
            if if_primer_contacto(to):
                c_id = obtener_o_crear_conv(to, texto, client)
                enviar_botones_bienvenida(to, nombre_wa)
            else:
                c_id = obtener_o_crear_conv(to, texto, client)
                
                # Si el usuario clickeó el botón "SI", le damos contexto a la IA
                input_ia = texto
                if mensaje.get('type') == 'interactive':
                    boton_id = mensaje['interactive']['button_reply']['id']
                    if boton_id == "btn_si":
                        input_ia = "SISTEMA: El usuario aceptó el Modo Botones. Ejecuta 'mostrar_menu_botones' para darle opciones."
                
                res_ia = consultar_ia(input_ia, c_id, to)
                if res_ia:
                    enviar_mensaje(to, res_ia)
                
    return jsonify({"status": "ok"}), 200

@app.route('/webhook', methods=['GET'])
def webhook_verificar():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge'), 200
    return "error", 403

@app.route('/dashboard')
def ver_dashboard():
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT id, telefono, ultimo_mensaje, fecha_actualizacion, conversation_id FROM leads ORDER BY fecha_actualizacion DESC")
        leads = cur.fetchall()
        cur.close()
        conn.close()

        html = """
        <html>
        <head>
            <title>Dashboard CallBotIA</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; }
                table { width: 100%; border-collapse: collapse; margin-top: 20px; }
                th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
                th { background-color: #f2f2f2; }
                .btn-del { color: white; background-color: #ff4444; border: none; padding: 8px 12px; cursor: pointer; border-radius: 4px; text-decoration: none; }
                .btn-del:hover { background-color: #cc0000; }
            </style>
            </head>
        <body>
            <h2>Leads de CallBotIA - Kat-IA</h2>
            <p><i>Si el bot tira error 400, borrá el registro para resetear la charla.</i></p>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Teléfono</th>
                    <th>Último Mensaje</th>
                    <th>Fecha</th>
                    <th>Acciones</th>
                </tr>
        """
        for lead in leads:
            html += f"""
                <tr>
                    <td>{lead['id']}</td>
                    <td>{lead['telefono']}</td>
                    <td>{lead['ultimo_mensaje']}</td>
                    <td>{lead['fecha_actualizacion']}</td>
                    <td>
                        <a href="/eliminar/{lead['id']}" class="btn-del" onclick="return confirm('¿Seguro querés borrar este lead y resetear su chat?')">Eliminar</a>
                    </td>
                    </tr>"""
        
        html += "</table></body></html>"
        return html
    except Exception as e:
        return f"<h3>Error al cargar el dashboard:</h3><p>{e}</p>"

@app.route('/eliminar/<int:id>')
def eliminar_lead(id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM leads WHERE id = %s", (id,))
        conn.commit()
        cur.close()
        conn.close()
        print(f"Lead ID {id} eliminado de la base de datos.")
        return """<script>alert('Lead eliminado con éxito'); window.location.href='/dashboard';</script>"""
    except Exception as e:
        return f"Error al eliminar: {e}"

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))