import os
import mysql.connector
from mysql.connector import Error
import time

def get_db_connection():
    # Railway te da estas variables separadas para MySQL
    try:
        conn = mysql.connector.connect(
            host=os.getenv("MYSQLHOST"),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=os.getenv("MYSQLDATABASE"),
            port=int(os.getenv("MYSQLPORT", 3306)), # Forzalo a INT
            connect_timeout=5 # Bajá el timeout para que no cuelgue el build
        )
        return conn
    except Error as e:
        print(f"❌ ERROR de conexión MySQL: {e}")
        return None

def init_db():
    print("DEBUG: Intentando inicializar MySQL...")
    conn = get_db_connection()
    if conn is None:
        print("⚠️ Saltando inicialización de DB (Conexión fallida), pero sigo con el build...")
        return

    try:
        cur = conn.cursor()
        # Tabla de Leads (Sintaxis MySQL)
        cur.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nombre TEXT,
                telefono VARCHAR(255) UNIQUE NOT NULL,
                conversation_id VARCHAR(255),
                ultimo_mensaje TEXT,
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        # Tabla de mensajes procesados
        cur.execute('''
            CREATE TABLE IF NOT EXISTS mensajes_procesados (
                msg_id VARCHAR(255) PRIMARY KEY,
                fecha_recepcion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        conn.commit()
        print("✅ DEBUG: MySQL inicializado correctamente.")
    except Error as e:
        print(f"❌ ERROR al crear tablas: {e}")
    finally:
        cur.close()
        conn.close()

def check_if_processed(msg_id):
    conn = get_db_connection()
    if not conn: return False
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO mensajes_procesados (msg_id) VALUES (%s)", (msg_id,))
        conn.commit()
        return False 
    except Error:
        return True
    finally:
        if conn.is_connected():
            cur.close()
            conn.close()

def create_or_update_conv(phone_number, nombre, texto_usuario, client_openai):
    conn = get_db_connection()
    if not conn: return None
    try:
        cur = conn.cursor(dictionary=True) # Similar al DictCursor de Postgres
        cur.execute("SELECT conversation_id FROM leads WHERE telefono = %s", (phone_number,))
        result = cur.fetchone()
        
        if result and result['conversation_id']:
            conv_id = result['conversation_id']
            cur.execute("UPDATE leads SET ultimo_mensaje = %s WHERE telefono = %s", (texto_usuario, phone_number))
        else:
            conv = client_openai.conversations.create()
            conv_id = conv.id
            cur.execute("INSERT INTO leads (telefono, nombre, conversation_id, ultimo_mensaje) VALUES (%s, %s, %s, %s)", 
                        (phone_number, nombre, conv_id, texto_usuario))
        
        conn.commit()
        return conv_id
    except Error as e:
        print(f"❌ ERROR en create_or_update_conv: {e}")
        return None
    finally:
        if conn.is_connected():
            cur.close()
            conn.close()

def if_primer_contacto(phone_number):
    conn = get_db_connection()
    if not conn: return False
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM leads WHERE telefono = %s", (phone_number,))
        existe = cur.fetchone()
        return existe is None
    except Error:
        return False
    finally:
        if conn.is_connected():
            cur.close()
            conn.close()