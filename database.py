import datetime
import os, mysql.connector
import re
from mysql.connector import Error, pooling
import time

# Dejamos el pool como None al inicio para que no explote al bootear el worker
db_pool = None

def crear_pool():
    """Intenta inicializar el pool de conexiones."""
    global db_pool
    try:
        db_pool = mysql.connector.pooling.MySQLConnectionPool(
            pool_name="katia_pool",
            pool_size=5,
            pool_reset_session=True,
            host=os.getenv("MYSQLHOST"),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=os.getenv("MYSQLDATABASE"),
            port=int(os.getenv("MYSQLPORT", 3306)),
            connect_timeout=20  # Tiempo suficiente para que Railway despierte la DB
        )
        return True
    except Error as e:
        print(f"Aun no hay conexion con MySQL: {e}")
        return False

def get_db_connection():
    """Obtiene una conexion del pool, creandolo si no existe."""
    global db_pool
    if db_pool is None:
        if not crear_pool():
            return None
    try:
        return db_pool.get_connection()
    except Error as e:
        print(f"error mysql pool: {e}")
        # Si falla la conexion, reseteamos el pool para forzar re-creacion en el proximo intento
        db_pool = None
        return None

def init_db():
    """Inicializa las tablas necesarias."""
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
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
        if 'cur' in locals(): cur.close()
        conn.close()

def check_if_processed(msg_id):
    """Evita duplicados con sistema de reintentos robusto."""
    reintentos = 5 # Subimos a 5 para mayor seguridad
    for i in range(reintentos):
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM mensajes_procesados WHERE fecha_recepcion < NOW() - INTERVAL 1 HOUR")
                cur.execute("INSERT INTO mensajes_procesados (msg_id) VALUES (%s)", (msg_id,))
                conn.commit()
                return False 
            except Error as e:
                if e.errno == 1062: # Duplicate entry
                    return True
                print(f"Error en query (intento {i+1}): {e}")
            finally:
                if 'cur' in locals(): cur.close()
                conn.close()
        
        print(f"DB dormida, reintentando en 2 segundos... ({i+1}/{reintentos})")
        time.sleep(2)
    return False

def extraer_email(texto):
    patron = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    resultado = re.search(patron, texto)
    return resultado.group(0) if resultado else None

def create_or_update_conv(phone, nombre, texto, client_openai):
    conn = get_db_connection()
    if not conn: return None
    try:
        cur = conn.cursor(dictionary=True)
        # Traemos también la fecha de actualización
        cur.execute("SELECT conversation_id, fecha_actualizacion FROM leads WHERE telefono = %s", (phone,))
        res = cur.fetchone()
        
        ahora = datetime.datetime.now()
        
        # Si existe pero la última charla fue hace más de 24 horas...
        if res and res['conversation_id']:
            ultima_vez = res['fecha_actualizacion']
            # Calculamos la diferencia
            if (ahora - ultima_vez).days >= 1:
                # CREAMOS UN HILO NUEVO para que no arrastre basura vieja
                c_id = client_openai.conversations.create().id
                cur.execute("UPDATE leads SET conversation_id = %s, ultimo_mensaje = %s WHERE telefono = %s", 
                           (c_id, texto, phone))
            else:
                # Es una charla fluida, seguimos con el mismo ID
                c_id = res['conversation_id']
                cur.execute("UPDATE leads SET ultimo_mensaje = %s WHERE telefono = %s", (texto, phone))
        else:
            # Caso de usuario nuevo
            c_id = client_openai.conversations.create().id
            cur.execute("INSERT INTO leads (telefono, nombre, conversation_id, ultimo_mensaje) VALUES (%s, %s, %s, %s)", 
                       (phone, nombre, c_id, texto))
        
        conn.commit()
        return c_id
    except Exception as e:
        print(f"Error en gestion de hilos: {e}")
        return None
    finally:
        if 'cur' in locals(): cur.close()
        conn.close()

def if_primer_contacto(phone):
    conn = get_db_connection()
    if not conn: return False
    try:
        cur = conn.cursor()
        # Buscamos si el numero existe Y si fue actualizado en las ultimas 24 horas
        query = """
            SELECT 1 FROM leads 
            WHERE telefono = %s 
            AND fecha_actualizacion > NOW() - INTERVAL 1 DAY
        """
        cur.execute(query, (phone,))
        res = cur.fetchone()
        
        # Si res es None, significa que:
        # 1. El cliente es totalmente nuevo.
        # 2. O el cliente ya existia pero no escribia hace mas de un dia.
        return res is None
        
    except Error as e:
        print(f"error en if_primer_contacto: {e}")
        return False
    finally:
        if 'cur' in locals(): cur.close()
        conn.close()