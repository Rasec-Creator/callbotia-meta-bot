import os, json
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI
import datetime
import threading
from psycopg2.extras import DictCursor
from database import init_db, get_db_connection, check_if_processed, create_or_update_conv, if_primer_contacto
from services.whatsapp_service import enviar_mensaje, enviar_botones_bienvenida, enviar_botones_dinamicos, descargar_y_codificar, obtener_media_url, transcribir_audio
from services.calendar_service import agendar_reunion
from services.mail_service import enviar_mail_smtp

load_dotenv()
app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PROMPT_ID = os.getenv("PROMPT_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

def consultar_ia(texto, conv_id, phone,imagen_b64=None):
    ahora = datetime.datetime.now()
    fecha_string = ahora.strftime("%A %d/%m/%Y %H:%M hs")
    # usamos la API de chat (soporta imagenes) para describirla
    if imagen_b64:
        try:
            res_vision = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Describe brevemente que se ve en esta imagen para que otro asistente pueda entender el contexto."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{imagen_b64}"}}
                    ]
                }]
            )
            descripcion = res_vision.choices[0].message.content
            input_ia = f"\n[EL USUARIO ENVIÓ UNA IMAGEN: {descripcion}]\n Caption de la imagen: {texto}"
        except Exception as e:
            print(f"Error en visión: {e}")
            input_ia = "\n[EL USUARIO ENVIÓ UNA IMAGEN QUE NO PUDISTE PROCESAR]\n Caption de la imagen: {texto}"
    else:
        input_ia = texto
    try:
        response = client.responses.create(
            model="gpt-4o-mini", 
            prompt={"id": PROMPT_ID,
                    "variables": {
                        "fecha_actual": fecha_string
                    }},
            conversation=conv_id, 
            input=input_ia 
        )
        outputs_pendientes = []
        texto_final = None

        for item in response.output:
            c_id = getattr(item, 'call_id', None)

            if item.type == 'function_call':
                resultado_tool, msg_usuario = ejecutar_herramienta(item, phone)
                # si la herramienta trajo mensaje
                if msg_usuario:
                    enviar_mensaje(phone, msg_usuario)
                outputs_pendientes.append({
                    "type": "function_call_output",
                    "call_id": c_id,
                    "output": json.dumps(resultado_tool)
                })
            elif item.type == 'message':
                texto_final = item.content[0].text
        # cierre de ciclo
        if outputs_pendientes:
           threading.Thread(target=sincronizar_ia, args=(conv_id, outputs_pendientes)).start()
        return texto_final
    except Exception as e:
        print(f"ERROR IA: {str(e)}")
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
    elif nombre == 'enviar_email':
        exito = enviar_mail_smtp(
            destinatario=args['email_destino'],
            asunto=args['asunto'],
            contenido_ia=args['cuerpo']
        )
        
        if exito:
            res = {"status": "success", "email": args['email_destino']}
            msg_p_usuario = (
                f"📩 ¡Listo! Acabo de enviarte toda la info a *{args['email_destino']}*.\n\n"
                f"Fijate si te llegó y cualquier cosa me avisás."
            )
            return res, msg_p_usuario
        else:
            res = {"status": "error", "message": "fallo el servidor smtp"}
            return res, "Uy, tuve un problema técnico al intentar mandarte el mail. ¿Querés que probemos de nuevo?"
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
    #to = "54" + numero[3:] if numero.startswith("549") else numero
    to = numero
    
    texto, boton_id, media_id, tipo = extraer_contenido(mensaje)
      
    if texto or media_id:
        thread = threading.Thread(  # procesamiento en segundo plano (responde 200 a meta evita reintentos)
            target=procesar_respuesta_ia, 
            args=(to, nombre_wa, texto, boton_id, media_id, tipo)
        )
        thread.start()

    # respuesta a meta
    return jsonify({"status": "received"}), 200

"""Extrae el texto o el ID del boton del mensaje"""
def extraer_contenido(mensaje):
    texto = ""
    boton_id = None
    media_id = None
    tipo = mensaje.get('type')

    if tipo == 'text':
        texto = mensaje['text']['body']
    elif tipo == 'interactive':
        texto = mensaje['interactive']['button_reply']['title']
        boton_id = mensaje['interactive']['button_reply']['id']
    elif tipo == 'image':
        media_id = mensaje['image']['id']
        texto = mensaje['image'].get('caption', 'El usuario envió una imagen') # texto que acompaña la foto
    elif tipo == 'audio':
        media_id = mensaje['audio']['id']
        
    return texto, boton_id, media_id, tipo
"""Logica de negocio"""
def procesar_respuesta_ia(to, nombre_wa, texto, boton_id, media_id=None, tipo=None):
    try:
        nuevo=if_primer_contacto(to)
        c_id = create_or_update_conv(to, nombre_wa, texto, client)
        # manejo de base de datos y conver
        if nuevo:
            enviar_botones_bienvenida(to, nombre_wa)
            return
        # imagen o audio, procesamos antes de mandar a IA
        imagen_b64 = None
        input_ia = f"{nombre_wa}: {texto}"
        # procesamiento multimedia
        if tipo == 'image' and media_id:
            url = obtener_media_url(media_id)
            imagen_b64 = descargar_y_codificar(url)
        
        elif tipo == 'audio' and media_id:
            url = obtener_media_url(media_id)
            texto_audio = transcribir_audio(url) 
            if texto_audio:
                input_ia = f"{nombre_wa} (audio transcripto): {texto_audio}"
        # contexto para botones
        if boton_id == "btn_si":
            input_ia = f"{nombre_wa} acepto el Modo Botones. Ejecuta 'mostrar_menu_botones' para darle opciones."
        elif boton_id == "btn_no":
            input_ia = f"{nombre_wa} prefirio seguir en chat. Continuar la conversacion en modo texto."
        # consulta a la IA y envio
        res_ia = consultar_ia(input_ia, c_id, to, imagen_b64)
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