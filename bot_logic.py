from database import if_primer_contacto, create_or_update_conv
from services.whatsapp_service import enviar_botones_bienvenida, enviar_mensaje, obtener_media_url, descargar_y_codificar, transcribir_audio
from ia_logic import consultar_ia, client

def procesar_seguro(to, nombre_wa, texto, boton_id, media_id, tipo):
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

def extraer_contenido(mensaje):
    txt, b_id, m_id, tipo = "", None, None, mensaje.get('type')
    if tipo == 'text': txt = mensaje['text']['body']
    elif tipo == 'interactive':
        txt = mensaje['interactive']['button_reply']['title']
        b_id = mensaje['interactive']['button_reply']['id']
    elif tipo == 'image':
        m_id, txt = mensaje['image']['id'], mensaje['image'].get('caption', '')
    elif tipo == 'audio': m_id = mensaje['audio']['id']
    return txt, b_id, m_id, tipo