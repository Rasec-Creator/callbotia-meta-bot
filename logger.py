import logging
import os

def get_logger(name="KatIA"):
    """
    configura y devuelve un logger centralizado para todo el proyecto.
    """
    logger = logging.getLogger(name)
    
    # si el logger ya tiene handlers configurados, no agregamos mas
    # esto evita que se dupliquen los mensajes en la consola
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        file_handler = logging.FileHandler("app.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.error(f"no se pudo crear el archivo de log: {e}")
    return logger