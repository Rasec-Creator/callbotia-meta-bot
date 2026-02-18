import os
import psycopg2
from psycopg2.extras import DictCursor

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            nombre TEXT,
            telefono TEXT UNIQUE NOT NULL,
            conversation_id TEXT,
            ultimo_mensaje TEXT,
            fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS mensajes_procesados (
            msg_id TEXT PRIMARY KEY,
            fecha_recepcion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()

def check_if_processed(msg_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO mensajes_procesados (msg_id) VALUES (%s)", (msg_id,))
        conn.commit()
        return False 
    except psycopg2.IntegrityError:
        conn.rollback()
        return True
    finally:
        cur.close()
        conn.close()

def create_or_update_conv(phone_number, nombre, texto_usuario, client_openai):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT conversation_id FROM leads WHERE telefono = %s", (phone_number,))
    result = cur.fetchone()
    
    if result and result['conversation_id']:
        conv_id = result['conversation_id']
        cur.execute("UPDATE leads SET ultimo_mensaje = %s, fecha_actualizacion = CURRENT_TIMESTAMP WHERE telefono = %s", (texto_usuario, phone_number))
    else:
        conv = client_openai.conversations.create()
        conv_id = conv.id
        cur.execute("INSERT INTO leads (telefono, nombre, conversation_id, ultimo_mensaje) VALUES (%s, %s, %s, %s)", (phone_number, nombre, conv_id, texto_usuario))
    
    conn.commit()
    cur.close()
    conn.close()
    return conv_id
def if_primer_contacto(phone_number):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM leads WHERE telefono = %s", (phone_number,))
    existe = cur.fetchone()
    cur.close()
    conn.close()
    
    return existe is None