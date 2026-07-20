import logging
import os
import datetime
import pytz

def get_logger(name="KatIA"):
    """
    configura y devuelve un logger centralizado para todo el proyecto.
    """
    logger = logging.getLogger(name)
    
    # si el logger ya tiene handlers configurados, no agregamos mas
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )

    def timect_ar(*args):
        tz_arg = pytz.timezone('America/Argentina/Buenos_Aires')
        return datetime.datetime.now(tz_arg).timetuple()
        
    formatter.converter = timect_ar # le pisamos el conversor por defecto al formateador

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        file_handler = logging.FileHandler("app.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        # aca usamos el stream handler que ya se configuro arriba para mostrar el error
        console_handler.setFormatter(formatter)
        print(f"no se pudo crear el archivo de log: {e}")
        
    return logger