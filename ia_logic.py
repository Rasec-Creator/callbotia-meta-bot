import json, datetime, time, os
from threading import Lock
from openai import OpenAI
from database import get_db_connection, guardar_contacto_lead
from services.calendar_service import agendar_reunion
from services.whatsapp_service import enviar_mensaje, enviar_botones_dinamicos
from services.mail_service import enviar_mail_resend
import datetime
import json
from logger import get_logger

logger = get_logger()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PROMPT_ID = os.getenv("PROMPT_ID")
locks = {}

def consultar_ia(phone_id,texto, conv_id, phone, imagen_b64=None):
    logger.info(f"consultar_ia - phone_id: {phone_id}, texto: {texto}, conv_id: {conv_id}, phone: {phone}, tiene_imagen: {imagen_b64 is not None}")
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
    headers = {
        "Content-Type": "application/json",
        "Referer": "https://callbotia.site" # Debe coincidir con tu whitelist en PHP
    }
    
    match n:
        case 'mostrar_menu_botones':
            enviar_botones_dinamicos(phone_id, phone, args['texto_cuerpo'], args['botones'])
            return {"status": "ok"}, None
        case 'guardar_contacto':
            nombre = args.get('nombre')
            empresa = args.get('empresa', '-')
            telefono_cliente = phone  # la variable que ya usas para capturar el numero del webhook

            # llamamos a la funcion limpia de database.py
            res = guardar_contacto_lead(
                nombre=nombre,
                telefono=telefono_cliente,
                email=args.get('email'),
                empresa=empresa,
                puesto=args.get('puesto', '-'),
                interes=args.get('interes', '-')
            )
            
            if res.get("status") == "success":
                msg = (f"¡Excelente, {nombre}! Ya registré tus datos de **{empresa}**. "
                       "Un asesor se va a estar contactando con vos pronto. ¿Te puedo ayudar con algo más?")
                return res, msg
            else:
                msg_error = f"tuvimos un problema al guardar los datos: {res.get('message')}"
                return res, msg_error

        case 'agendar_reunion':
            # extraemos los datos que nos envia openai
            fecha_hora = args.get('fecha_hora')
            nombre = args.get('nombre', 'cliente')
            telefono_cliente = phone 
            email_cliente = args.get('email')
            resumen_consulta = args.get('resumen', 'Consulta general')

            res = agendar_reunion(
                fecha_iso=fecha_hora,
                nombre_cliente=nombre,
                telefono=telefono_cliente,
                email=email_cliente,
                resumen=resumen_consulta
            )
            
            if res.get("status") == "success":
                fecha_raw = res.get('fecha_confirmada', fecha_hora)
                link_meet = res.get('meet_link', 'vincule el link manualmente')
                
                try:
                    dt = datetime.datetime.fromisoformat(fecha_raw)
                    fecha_linda = dt.strftime('%d/%m/%Y a las %H:%M')
                except:
                    fecha_linda = fecha_raw
                
                msg = (f"✅ ¡Reunion confirmada, {nombre}!\n\n"
                       f"📅 *Fecha:* {fecha_linda} hs\n"
                       f"🔗 *Link:* {link_meet}\n\n"
                       "Te enviamos un mail con los detalles. ¡nos vemos! 🚀")
                
                return res, msg
            
            else:
                # si fallo por horario ocupado, fin de semana o fuera de rango,
                # res['message'] trae la explicacion exacta que armamos antes
                msg_error = f"no pude agendar: {res.get('message', 'error desconocido')}"
                return res, msg_error

        case 'enviar_email':
            if enviar_mail_resend(args['email_destino'], args['asunto'], args['cuerpo']):
                return {"status": "success"}, f"📩 ¡listo! info enviada a *{args['email_destino']}*."
            return {"status": "error"}, "fallo el envio del mail. ¿queres que intente de nuevo?"

        case _:
            return {"error": "herramienta no encontrada"}, None