import os, json, datetime, threading, time
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from openai import OpenAI
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

from database import init_db, get_db_connection, check_if_processed, create_or_update_conv, if_primer_contacto
from services.whatsapp_service import enviar_mensaje, enviar_botones_bienvenida, enviar_botones_dinamicos, descargar_y_codificar, obtener_media_url, transcribir_audio
from services.calendar_service import agendar_reunion
from services.mail_service import enviar_mail_smtp

load_dotenv()
app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PROMPT_ID = os.getenv("PROMPT_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

# inicializacion de base de datos
try:
    threading.Thread(target=init_db).start()
except Exception as e:
    print(f"error db init: {e}")

# configuracion de hilos y locks para concurrencia
executor = ThreadPoolExecutor(max_workers=10)
locks = {}

def limpiar_locks_viejos():
    # limpia locks inactivos para liberar memoria cada una hora
    while True:
        time.sleep(3600)
        ahora = time.time()
        for phone in list(locks.keys()):
            if ahora - locks[phone]['last_seen'] > 3600:
                if not locks[phone]['lock'].locked():
                    del locks[phone]
                    print(f"limpieza: lock eliminado para {phone}")

threading.Thread(target=limpiar_locks_viejos, daemon=True).start()

def consultar_ia(texto, conv_id, phone, imagen_b64=None):
    # gestion de lock por usuario y consulta a openai
    if phone not in locks:
        locks[phone] = {"lock": Lock(), "last_seen": time.time()}
    
    locks[phone]['last_seen'] = time.time()
    
    with locks[phone]['lock']:
        fecha_string = datetime.datetime.now().strftime("%A %d/%m/%Y %H:%M hs")
        input_ia = texto

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
                }])
                descripcion = res_vision.choices[0].message.content
                input_ia = f"\n[EL USUARIO ENVIÓ UNA IMAGEN: {descripcion}]\n Caption de la imagen: {texto}"
            except Exception as e:
                print(f"error vision: {e}")
                input_ia = f"\n[IMAGEN NO PROCESADA]\n Caption: {texto}"

        try:
            response = client.responses.create(
                model="gpt-4o-mini", 
                prompt={"id": PROMPT_ID, "variables": {"fecha_actual": fecha_string}},
                conversation=conv_id, 
                input=input_ia 
            )
            
            outputs_pendientes = []
            texto_final = None

            for item in response.output:
                if item.type == 'function_call':
                    res_t, msg_u = ejecutar_herramienta(item, phone)
                    if msg_u: enviar_mensaje(phone, msg_u)
                    outputs_pendientes.append({
                        "type": "function_call_output",
                        "call_id": getattr(item, 'call_id', None),
                        "output": json.dumps(res_t)
                    })
                elif item.type == 'message':
                    texto_final = item.content[0].text
            
            if outputs_pendientes:
                client.responses.create(model="gpt-4o-mini", conversation=conv_id, input=outputs_pendientes)
                
            return texto_final
        except Exception as e:
            print(f"error openai: {e}")
            return None

def ejecutar_herramienta(item, phone):
    # despacha las funciones llamadas por la ia
    args = json.loads(item.arguments)
    n = item.name
    
    if n == 'mostrar_menu_botones':
        enviar_botones_dinamicos(phone, args['texto_cuerpo'], args['botones'])
        return {"status": "ok"}, None
        
    elif n == 'agendar_reunion':
        res = agendar_reunion(args['fecha_hora'], args['nombre_cliente'], phone)
        if res.get("status") == "success":
            try:
                dt_i = datetime.datetime.fromisoformat(res['inicio'])
                dt_f = datetime.datetime.fromisoformat(res['fin'])
                rango = f"{dt_i.strftime('%d/%m/%Y')} de {dt_i.strftime('%H:%M')} a {dt_f.strftime('%H:%M')} hs"
            except: rango = res['inicio']
            msg = f"✅ ¡Reunion confirmada, {res['cliente']}!\n\n📅 *Fecha:* {rango}\n🔗 *Link:* {res['meet_link']}\n\n¡Te espero! 🚀"
            return res, msg
        return res, f"error al agendar: {res.get('message')}"

    elif n == 'enviar_email':
        if enviar_mail_smtp(args['email_destino'], args['asunto'], args['cuerpo']):
            return {"status": "success"}, f"📩 ¡Listo! Info enviada a *{args['email_destino']}*."
        return {"status": "error"}, "uy, fallo el mail. probamos de nuevo?"

    return {"error": "no encontrada"}, None

def procesar_seguro(to, nombre_wa, texto, boton_id, media_id, tipo):
    # ejecucion protegida para el pool de hilos
    try:
        nuevo = if_primer_contacto(to)
        c_id = create_or_update_conv(to, nombre_wa, texto, client)
        
        if nuevo:
            enviar_botones_bienvenida(to, nombre_wa)
            return

        img_b64 = None
        input_ia = f"{nombre_wa}: {texto}"

        if tipo == 'image' and media_id:
            img_b64 = descargar_y_codificar(obtener_media_url(media_id))
        elif tipo == 'audio' and media_id:
            t_audio = transcribir_audio(obtener_media_url(media_id))
            if t_audio: input_ia = f"{nombre_wa} (audio): {t_audio}"

        if boton_id == "btn_si": input_ia = "SISTEMA: usuario acepto botones. ejecutar mostrar_menu_botones."
        elif boton_id == "btn_no": input_ia = "SISTEMA: usuario prefirio chat de texto."

        res_ia = consultar_ia(input_ia, c_id, to, img_b64)
        if res_ia: enviar_mensaje(to, res_ia)
    except Exception as e:
        print(f"error hilo: {e}")

@app.route('/webhook', methods=['POST'])
def recibir_mensajes():
    # punto de entrada para mensajes de whatsapp
    v = request.get_json().get('entry', [{}])[0].get('changes', [{}])[0].get('value', {})
    if 'messages' not in v: return jsonify({"status": "ignored"}), 200

    msg = v['messages'][0]
    if check_if_processed(msg.get('id')): return jsonify({"status": "skipped"}), 200

    contacto = v.get('contacts', [{}])[0]
    nombre = contacto.get('profile', {}).get('name', 'Usuario')
    num = msg['from']
    
    # extraer contenido segun tipo
    txt, b_id, m_id, tipo = "", None, None, msg.get('type')
    if tipo == 'text': txt = msg['text']['body']
    elif tipo == 'interactive':
        txt = msg['interactive']['button_reply']['title']
        b_id = msg['interactive']['button_reply']['id']
    elif tipo == 'image':
        m_id, txt = msg['image']['id'], msg['image'].get('caption', '')
    elif tipo == 'audio': m_id = msg['audio']['id']
      
    executor.submit(procesar_seguro, num, nombre, txt, b_id, m_id, tipo)
    return jsonify({"status": "received"}), 200

@app.route('/webhook', methods=['GET'])
def verificar():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge'), 200
    return "error", 403
""" 
@app.route('/dashboard')
def ver_dashboard():
    # panel visual de leads en mysql
    conn = get_db_connection()
    if not conn: return "error db connection"
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM leads ORDER BY fecha_actualizacion DESC")
        leads = cur.fetchall()
        
        html = "<html><head><title>Dashboard</title><meta http-equiv='refresh' content='30'></head><body>"
        html += "<h2>Leads CallBotIA</h2><table border='1'><tr><th>Tel</th><th>Nombre</th><th>Mensaje</th><th>Accion</th></tr>"
        for l in leads:
            html += f"<tr><td>{l['telefono']}</td><td>{l['nombre'] or '-'}</td><td>{l['ultimo_mensaje'] or '-'}</td>"
            html += f"<td><a href='/eliminar/{l['id']}'>Borrar</a></td></tr>"
        return html + "</table></body></html>"
    finally: conn.close() """
""" 
@app.route('/eliminar/<int:id>')
def eliminar(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM leads WHERE id = %s", (id,))
    conn.commit()
    conn.close()
    return "<script>window.location.href='/dashboard';</script>"
 """
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))