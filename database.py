import os, mysql.connector
import re
from mysql.connector import Error

def get_db_connection():
    # conexion a mysql con variables de entorno
    try:
        return mysql.connector.connect(
            host=os.getenv("MYSQLHOST"),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=os.getenv("MYSQLDATABASE"),
            port=int(os.getenv("MYSQLPORT", 3306)),
            connect_timeout=10
        )
    except Error as e:
        print(f"error mysql connection: {e}")
        return None

def init_db():
    # creacion de tablas si no existen
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        # tabla de leads
        cur.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nombre TEXT,
                telefono VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255),
                conversation_id VARCHAR(255),
                ultimo_mensaje TEXT,
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        # tabla de de-duplicacion
        cur.execute('''
            CREATE TABLE IF NOT EXISTS mensajes_procesados (
                msg_id VARCHAR(255) PRIMARY KEY,
                fecha_recepcion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        conn.commit()
    except Error as e:
        print(f"error init_db: {e}")
    finally:
        cur.close()
        conn.close()

def check_if_processed(msg_id):
    # evita procesar el mismo mensaje dos veces y limpia viejos
    conn = get_db_connection()
    if not conn: return False
    try:
        cur = conn.cursor()
        
        # limpieza ids de mas de 1 hora antes de chequear
        cur.execute("DELETE FROM mensajes_procesados WHERE fecha_recepcion < NOW() - INTERVAL 1 HOUR")
        
        # intentar insertar el nuevo id
        cur.execute("INSERT INTO mensajes_procesados (msg_id) VALUES (%s)", (msg_id,))
        conn.commit()
        return False 
    except Error:
        return True # si falla es porque ya existe
    finally:
        cur.close()
        conn.close()

def extraer_email(texto):
    # busca un patron basico de email en el texto
    patron = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    resultado = re.search(patron, texto)
    return resultado.group(0) if resultado else None

def create_or_update_conv(phone, nombre, texto, client_openai):
    # gestiona la conversacion de openai vinculada al lead
    conn = get_db_connection()
    if not conn: return None
    try:
        cur = conn.cursor(dictionary=True)
        mail_detectado = extraer_email(texto)# intentamos extraer un mail del texto
        cur.execute("SELECT conversation_id FROM leads WHERE telefono = %s", (phone,))
        res = cur.fetchone()
        
        if res and res['conversation_id']:
            c_id = res['conversation_id']
            if mail_detectado:
                cur.execute("UPDATE leads SET ultimo_mensaje = %s, email = %s WHERE telefono = %s", 
                           (texto, mail_detectado, phone))
            else:
                cur.execute("UPDATE leads SET ultimo_mensaje = %s WHERE telefono = %s", (texto, phone))
        else:# creamos el registro
            c_id = client_openai.conversations.create().id
            cur.execute("""
                INSERT INTO leads (telefono, nombre, conversation_id, ultimo_mensaje, email) 
                VALUES (%s, %s, %s, %s, %s)
            """, (phone, nombre, c_id, texto, mail_detectado))
        
        conn.commit()
        return c_id
    except Error as e:
        print(f"error conv_db: {e}")
        return None
    finally:
        cur.close()
        conn.close()

def if_primer_contacto(phone):
    # verifica si es la primera vez que escribe
    conn = get_db_connection()
    if not conn: return False
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM leads WHERE telefono = %s", (phone,))
        return cur.fetchone() is None
    except Error:
        return False
    finally:
        cur.close()
        conn.close()