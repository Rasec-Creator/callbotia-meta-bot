import datetime
import os
import re
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "WhatsappBot.db")

def get_db_connection():
    """obtiene una conexion limpia a sqlite configurada como diccionario."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"error conexion sqlite: {e}")
        return None

def init_db():
    """inicializa las tablas necesarias si no existen."""
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                telefono TEXT UNIQUE NOT NULL,
                email TEXT,
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
    except sqlite3.Error as e:
        print(f"error init_db: {e}")
    finally:
        if 'cur' in locals(): cur.close()
        conn.close()

def check_if_processed(msg_id):
    """evita duplicados usando la excepcion de integridad nativa de sqlite."""
    conn = get_db_connection()
    if not conn: return False
    try:
        cur = conn.cursor()
        # usamos los modificadores de tiempo de sqlite en lugar de interval
        cur.execute("DELETE FROM mensajes_procesados WHERE fecha_recepcion < datetime('now', '-1 hour')")
        cur.execute("INSERT INTO mensajes_procesados (msg_id) VALUES (?)", (msg_id,))
        conn.commit()
        return False 
    except sqlite3.IntegrityError:
        # si el msg_id ya existe salta esta excepcion por la clave primaria
        return True
    except sqlite3.Error as e:
        print(f"error en query check_if_processed: {e}")
        return False
    finally:
        if 'cur' in locals(): cur.close()
        conn.close()

def extraer_email(texto):
    patron = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    resultado = re.search(patron, texto)
    return resultado.group(0) if resultado else None

def create_or_update_conv(phone, nombre, texto, client_openai):
    conn = get_db_connection()
    if not conn: return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT conversation_id, fecha_actualizacion FROM leads WHERE telefono = ?", (phone,))
        res = cur.fetchone()
        
        ahora = datetime.datetime.utcnow()
        
        if res and res['conversation_id']:
            ultima_vez_str = res['fecha_actualizacion']
            # sqlite guarda las fechas como texto por ende las parseamos a objeto datetime
            if isinstance(ultima_vez_str, str):
                ultima_vez = datetime.datetime.strptime(ultima_vez_str, '%Y-%m-%d %H:%M:%S')
            else:
                ultima_vez = ultima_vez_str
            
            # si la ultima charla fue hace mas de 24 horas...
            if (ahora - ultima_vez).days >= 1:
                c_id = client_openai.conversations.create().id
                # actualizamos manualmente fecha_actualizacion ya que sqlite no tiene on update automatico
                cur.execute("""
                    UPDATE leads 
                    SET conversation_id = ?, ultimo_mensaje = ?, fecha_actualizacion = datetime('now') 
                    WHERE telefono = ?
                """, (c_id, texto, phone))
            else:
                c_id = res['conversation_id']
                cur.execute("""
                    UPDATE leads 
                    SET ultimo_mensaje = ?, fecha_actualizacion = datetime('now') 
                    WHERE telefono = ?
                """, (texto, phone))
        else:
            # caso de usuario nuevo
            c_id = client_openai.conversations.create().id
            cur.execute("""
                INSERT INTO leads (telefono, nombre, conversation_id, ultimo_mensaje) 
                VALUES (?, ?, ?, ?)
            """, (phone, nombre, c_id, texto))
        
        conn.commit()
        return c_id
    except Exception as e:
        print(f"error en gestion de hilos: {e}")
        return None
    finally:
        if 'cur' in locals(): cur.close()
        conn.close()

def if_primer_contacto(phone):
    conn = get_db_connection()
    if not conn: return False
    try:
        cur = conn.cursor()
        # usamos modificadores de fecha de sqlite para calcular el dia anterior
        query = """
            SELECT 1 FROM leads 
            WHERE telefono = ? 
            AND fecha_actualizacion > datetime('now', '-1 day')
        """
        cur.execute(query, (phone,))
        res = cur.fetchone()
        return res is None
        
    except sqlite3.Error as e:
        print(f"error en if_primer_contacto: {e}")
        return False
    finally:
        if 'cur' in locals(): cur.close()
        conn.close()