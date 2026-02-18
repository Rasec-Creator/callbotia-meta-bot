import os, json
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI
import datetime
import threading
from psycopg2.extras import DictCursor
from database import init_db, get_db_connection, check_if_processed, create_or_update_conv, if_primer_contacto
from services.whatsapp_service import enviar_mensaje, enviar_botones_bienvenida, enviar_botones_dinamicos
from services.calendar_service import agendar_reunion

load_dotenv()
app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PROMPT_ID = os.getenv("PROMPT_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

def consultar_ia(texto, conv_id, phone):

    try:
        response = client.responses.create(
            model="gpt-4o-mini", 
            prompt={"id": PROMPT_ID},
            conversation=conv_id, 
            input=texto 
        )
        outputs_pendientes = []
        texto_final = None

        for item in response.output:
            c_id = getattr(item, 'call_id', None)

            if item.type == 'function_call':
                resultado_tool, msg_usuario = ejecutar_herramienta(item, phone)
                
                outputs_pendientes.append({
                    "type": "function_call_output",
                    "call_id": c_id,
                    "output": json.dumps(resultado_tool)
                })
                # si la herramienta trajo mensaje
                if msg_usuario:
                    texto_final = msg_usuario
            elif item.type == 'message':
                texto_final = item.content[0].text
        # cierre de ciclo
        if outputs_pendientes:
            sincronizar_ia(conv_id, outputs_pendientes)
        return texto_final
    except Exception as e:
        print(f"❌ ERROR IA: {str(e)}")
        return None
    
"""Maneja cada funcion por separado."""
def ejecutar_herramienta(item, phone):
    args = json.loads(item.arguments)
    nombre = item.name
    
    if nombre == 'mostrar_menu_botones':
        enviar_botones_dinamicos(phone, args['texto_cuerpo'], args['botones'])
        return {"status": "ok"}, None
        
    elif nombre == 'agendar_reunion':
        res = agendar_reunion(args['fecha_hora'], args['nombre_cliente'], phone)
        
        if res.get("status") == "success":
            try:
                # procesamos inicio y fin
                dt_inicio = datetime.datetime.fromisoformat(res['inicio'])
                dt_fin = datetime.datetime.fromisoformat(res['fin'])
                
                # formateamos: dia/mes y el rango de horas
                fecha_dia = dt_inicio.strftime("%d/%m/%Y")
                hora_inicio = dt_inicio.strftime("%H:%M")
                hora_fin = dt_fin.strftime("%H:%M")
                
                rango_horario = f"{fecha_dia} de {hora_inicio} a {hora_fin} hs"
            except Exception as e:
                print(f"Error formateando fecha: {e}")
                rango_horario = res['inicio']

            msg_p_usuario = (
                f"✅ ¡Reunión confirmada, {res['cliente']}!\n\n"
                f"📅 *Fecha:* {rango_horario}\n"
                f"🔗 *Link de la reunión:* {res['meet_link']}\n\n"
                f"¡Te espero ahí para potenciar tu proyecto! 🚀"
            )
            return res, msg_p_usuario
        else:
            return res, f"Hubo un problema al agendar: {res.get('message')}"
    
    return {"error": "función no encontrada"}, None

"""Envia los outputs para cerrar la funcion."""
def sincronizar_ia(conv_id, outputs):
    try:
        client.responses.create(
            model="gpt-4o-mini",
            conversation=conv_id,
            input=outputs
        )
    except Exception as e:
        print(f"Error de sincronización: {e}")

@app.route('/webhook', methods=['POST'])
def recibir_mensajes():
    body = request.get_json()
    value = body.get('entry', [{}])[0].get('changes', [{}])[0].get('value', {})
    
    if 'messages' not in value:
        return jsonify({"status": "no messages"}), 200

    mensaje = value['messages'][0]
    msg_id = mensaje.get('id')
    
    # filtro de duplicados
    if check_if_processed(msg_id):
        return jsonify({"status": "skipped"}), 200

    # extraccion de datos
    contacto = value.get('contacts', [{}])[0]
    nombre_wa = contacto.get('profile', {}).get('name', 'Usuario')
    numero = mensaje['from']
    to = "54" + numero[3:] if numero.startswith("549") else numero
    
    texto, boton_id = extraer_contenido(mensaje)

    if texto:
        # procesamiento en segundo plano (responde 200 a meta evita reintentos)
        thread = threading.Thread(
            target=procesar_respuesta_ia, 
            args=(to, nombre_wa, texto, boton_id)
        )
        thread.start()

    # respuesta a meta
    return jsonify({"status": "received"}), 200

"""Extrae el texto o el ID del boton del mensaje"""
def extraer_contenido(mensaje):
    texto = ""
    boton_id = None
    if mensaje.get('type') == 'text':
        texto = mensaje['text']['body']
    elif mensaje.get('type') == 'interactive':
        texto = mensaje['interactive']['button_reply']['title']
        boton_id = mensaje['interactive']['button_reply']['id']
    return texto, boton_id

"""Logica de negocio"""
def procesar_respuesta_ia(to, nombre_wa, texto, boton_id):
    try:
        # manejo de base de datos y conver
        if if_primer_contacto(to):
            c_id = create_or_update_conv(to, nombre_wa, texto, client)
            enviar_botones_bienvenida(to, nombre_wa)
        else:
            c_id = create_or_update_conv(to, nombre_wa, texto, client)
            # contexto para botones
            input_ia = texto
            if boton_id == "btn_si":
                input_ia = f"SISTEMA: {nombre_wa} acepto el Modo Botones. Ejecuta 'mostrar_menu_botones' para darle opciones."
            # consulta a la IA y envio
            res_ia = consultar_ia(input_ia, c_id, to)
            if res_ia:
                enviar_mensaje(to, res_ia)
                
    except Exception as e:
        print(f"Error en procesar_respuesta_ia: {e}")

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
        cur.execute("SELECT id, telefono,nombre, ultimo_mensaje, fecha_actualizacion, fecha_creacion, conversation_id FROM leads ORDER BY fecha_actualizacion DESC")
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
                    <th>Nombre</th>
                    <th>Último Mensaje</th>
                    <th>Fecha Act</th>
                    <th>Fecha Creacion</th>
                    <th>Acciones</th>
                </tr>
        """
        for lead in leads:
            html += f"""
                <tr>
                    <td>{lead['id']}</td>
                    <td>{lead['telefono']}</td>
                    <td>{lead['nombre']}</td>
                    <td>{lead['ultimo_mensaje']}</td>
                    <td>{lead['fecha_actualizacion']}</td>
                    <td>{lead['fecha_creacion']}</td>
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