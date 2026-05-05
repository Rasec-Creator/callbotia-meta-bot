import json, datetime, time, os
from threading import Lock
from openai import OpenAI
from services.whatsapp_service import enviar_mensaje, enviar_botones_dinamicos
from services.calendar_service import agendar_reunion
from services.mail_service import enviar_mail_resend
import logging
import requests
import datetime
import json

logger = logging.getLogger("KatIA")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PROMPT_ID = os.getenv("PROMPT_ID")
locks = {}

def consultar_ia(phone_id,texto, conv_id, phone, imagen_b64=None):
    print("consultar_ia", phone_id, texto, conv_id, phone, imagen_b64 is not None)
    if phone not in locks:
        locks[phone] = {"lock": Lock(), "last_seen": time.time()}
    locks[phone]['last_seen'] = time.time()
    
    with locks[phone]['lock']:
        fecha_string = datetime.datetime.now().strftime("%A %d/%m/%Y %H:%M hs")
        input_ia = texto

        if imagen_b64:
            try:
                res_v = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "describe la imagen brevemente"},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{imagen_b64}"}}
                        ]
                    }]
                )
                descripcion = res_v.choices[0].message.content
                input_ia = f"\n[EL USUARIO ENVIÓ UNA IMAGEN: {descripcion}]\n Caption: {texto}"
            except Exception as e:
                logger.info(f"error vision: {e}")
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
                    res_t, msg_u = ejecutar_herramienta(phone_id,item, phone)
                    if msg_u: enviar_mensaje(phone_id,phone, msg_u)
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
            logger.info(f"error openai: {e}")
            return None

def ejecutar_herramienta(phone_id, item, phone):
    args = json.loads(item.arguments)
    n = item.name
    
    match n:
        case 'mostrar_menu_botones':
            enviar_botones_dinamicos(phone_id, phone, args['texto_cuerpo'], args['botones'])
            return {"status": "ok"}, None
            
        case 'agendar_reunion':
            payload = {
                "nombre": args.get('nombre'),
                "email": args.get('email'),
                "fecha_hora": args.get('fecha_hora'),
                "resumen": args.get('resumen', 'consulta desde chatbot'),
                "tipo": "callbotia"
            }
            try:
                r = requests.post("https://callbotia.site/reuniones/agendar.php", json=payload, timeout=10)
                res = r.json()
                
                if res.get("status") == "success":
                    link_meet = res.get('meet_link', 'vincule el link manualmente')
                    fecha_raw = res.get('fecha_confirmada', args['fecha_hora'])
                    
                    try:
                        dt = datetime.datetime.fromisoformat(fecha_raw)
                        fecha_linda = dt.strftime('%d/%m/%Y a las %H:%M')
                    except:
                        fecha_linda = fecha_raw
                    
                    msg = (f"✅ ¡Reunion confirmada, {args.get('nombre', 'cliente')}!\n\n"
                           f"📅 *Fecha:* {fecha_linda} hs\n"
                           f"🔗 *Link:* {link_meet}\n\n"
                           "Te enviamos un mail con los detalles. ¡nos vemos! 🚀")
                    
                    return res, msg
                
                # manejo de errores (horario ocupado, fin de semana..)
                return res, f"no pude agendar: {res.get('message')}"
                
            except Exception as e:
                return {"status": "error"}, f"hubo un problema con el servidor de agenda: {str(e)}"

        case 'enviar_email':
            if enviar_mail_resend(args['email_destino'], args['asunto'], args['cuerpo']):
                return {"status": "success"}, f"📩 ¡listo! info enviada a *{args['email_destino']}*."
            return {"status": "error"}, "fallo el envio del mail. ¿queres que intente de nuevo?"

        case _:
            return {"error": "herramienta no encontrada"}, None