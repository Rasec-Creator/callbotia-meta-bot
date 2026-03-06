import json, datetime, time, os
from threading import Lock
from openai import OpenAI
from services.whatsapp_service import enviar_mensaje, enviar_botones_dinamicos
from services.calendar_service import agendar_reunion
from services.mail_service import enviar_mail_resend

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
PROMPT_ID = os.getenv("PROMPT_ID")
locks = {}

def consultar_ia(phone_id,texto, conv_id, phone, imagen_b64=None):
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
                input_ia = f"\n{res_v.message.content}]\n Caption: {texto}"
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
            print(f"error openai: {e}")
            return None

def ejecutar_herramienta(phone_id,item, phone):
    args = json.loads(item.arguments)
    n = item.name
    
    if n == 'mostrar_menu_botones':
        enviar_botones_dinamicos(phone_id,phone, args['texto_cuerpo'], args['botones'])
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
        if enviar_mail_resend(args['email_destino'], args['asunto'], args['cuerpo']):
            return {"status": "success"}, f"📩 ¡Listo! Info enviada a *{args['email_destino']}*."
        return {"status": "error"}, "Fallo el envio del mail. Queres que intente de nuevo o tenes otra consulta?"

    return {"error": "no encontrada"}, None