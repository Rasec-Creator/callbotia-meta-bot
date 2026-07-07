import datetime
import os
import re
import sqlite3
import time
from logger import get_logger

logger = get_logger()

DB_PATH = os.path.join(os.path.dirname(__file__), "WhatsappBot.db")

def get_db_connection():
    try:
        conn = sqlite3.connect("katia.db", timeout=30.0)
        conn.row_factory = sqlite3.Row
        
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        
        return conn
    except Exception as e:
        logger.error(f"error de conexion a la base de datos: {e}")
        return None
def init_db():
    """inicializa las tablas necesarias si no existen."""
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        
        # tabla de leads
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
        
        # tabla de mensajes procesados para evitar duplicados
        cur.execute('''
            CREATE TABLE IF NOT EXISTS mensajes_procesados (
                msg_id TEXT PRIMARY KEY,
                fecha_recepcion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        # tabla de reuniones
        cur.execute('''
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telefono TEXT NOT NULL,
                fecha_hora DATETIME NOT NULL,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"error init_db: {e}")
    finally:
        if 'cur' in locals(): cur.close()
        conn.close()

def check_if_processed(msg_id):
    """evita duplicados usando la excepcion de integridad nativa de sqlite."""
    conn = get_db_connection()
    if not conn: return False
    
    es_duplicado = False  # variable de control
    try:
        cur = conn.cursor()
        # usamos los modificadores de tiempo de sqlite en lugar de interval
        cur.execute("DELETE FROM mensajes_procesados WHERE fecha_recepcion < datetime('now', '-1 hour')")
        cur.execute("INSERT INTO mensajes_procesados (msg_id) VALUES (?)", (msg_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        # si el msg_id ya existe salta esta excepcion por la clave primaria
        es_duplicado = True
    except sqlite3.Error as e:
        logger.error(f"error en query check_if_processed: {e}")
        es_duplicado = False
    finally:
        if 'cur' in locals(): cur.close()
        conn.close() # aseguramos que se cierre pase lo que pase
        
    return es_duplicado

def extraer_email(texto):
    patron = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    resultado = re.search(patron, texto)
    return resultado.group(0) if resultado else None

def create_or_update_conv(phone, nombre, texto, client_openai):
    conn = get_db_connection()
    if not conn: return None
    
    c_id_resultado = None  # variable de control
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
            c_id_resultado = c_id
        else:
            # caso de usuario nuevo
            c_id = client_openai.conversations.create().id
            cur.execute("""
                INSERT INTO leads (telefono, nombre, conversation_id, ultimo_mensaje) 
                VALUES (?, ?, ?, ?)
            """, (phone, nombre, c_id, texto))
            c_id_resultado = c_id
        
        conn.commit()
    except Exception as e:
        logger.error(f"error en gestion de hilos: {e}")
        c_id_resultado = None
    finally:
        if 'cur' in locals(): cur.close()
        conn.close() # liberamos el archivo de la db de inmediato
        
    return c_id_resultado

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
        logger.error(f"error en if_primer_contacto: {e}")
        return False
    finally:
        if 'cur' in locals(): cur.close()
        conn.close()

def guardar_contacto_lead(nombre, telefono, email, empresa='-', puesto='-', interes='-'):
    """
    guarda o actualiza los datos de perfil corporativo de un lead usando un upsert sobre el telefono.
    """
    conn = get_db_connection()
    if not conn:
        logger.error("No se pudo establecer conexion para guardar_contacto_lead")
        return {"status": "error", "message": "error de conexion con la base de datos"}
    
    try:
        cur = conn.cursor()
        
        # empaquetamos los datos corporativos extras en el campo de ultimo mensaje
        nota_datos = f"Empresa: {empresa} | Puesto: {puesto} | Interes: {interes}"

        # query para sqlite basada en el telefono como clave unica
        sql_upsert = """
            INSERT INTO leads (nombre, telefono, email, ultimo_mensaje) 
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telefono) DO UPDATE SET
                nombre = excluded.nombre,
                email = excluded.email,
                ultimo_mensaje = excluded.ultimo_mensaje,
                fecha_actualizacion = datetime('now')
        """
        
        cur.execute(sql_upsert, (nombre, telefono, email, nota_datos))
        conn.commit()
        
        logger.info(f"Lead {telefono} registrado/actualizado con exito en sqlite")
        return {"status": "success", "message": "Lead registrado correctamente"}

    except sqlite3.Error as e:
        logger.error(f"Error ejecucion en guardar_contacto_lead: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()