import os, threading, time
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from logger import get_logger

load_dotenv()
app = Flask(__name__)
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

# pool de hilos
executor = ThreadPoolExecutor(max_workers=10)

logger = get_logger()

from database import init_db, get_db_connection, check_if_processed
from bot_logic import procesar_seguro, extraer_contenido
from ia_logic import locks

# inicializacion db
threading.Thread(target=init_db).start()


def limpiar_locks_viejos():
    while True:
        time.sleep(3600)
        ahora = time.time()
        for phone in list(locks.keys()):
            if ahora - locks[phone]['last_seen'] > 3600:
                if not locks[phone]['lock'].locked():
                    del locks[phone]
                    logger.info(f"limpieza: lock eliminado para {phone}")

threading.Thread(target=limpiar_locks_viejos, daemon=True).start()

@app.route('/webhook', methods=['POST'])
def recibir_mensajes():
    entry = request.get_json().get('entry', [{}])[0]
    changes = entry.get('changes', [{}])[0]
    v = changes.get('value', {})
    
    if 'messages' not in v: 
        return jsonify({"status": "ignored"}), 200

    # CAPTURAMOS EL ID DEL TELÉFONO QUE RECIBIÓ EL MENSAJE
    phone_id_receptor = v.get('metadata', {}).get('phone_number_id')

    msg = v['messages'][0]
    if check_if_processed(msg.get('id')): 
        return jsonify({"status": "skipped"}), 200

    contacto = v.get('contacts', [{}])[0]
    nombre = contacto.get('profile', {}).get('name', 'Usuario')
    num = msg['from']
    
    txt, b_id, m_id, tipo = extraer_contenido(msg)

    # PASAMOS EL phone_id_receptor A PROCESAR_SEGURO
    executor.submit(procesar_seguro, phone_id_receptor, num, nombre, txt, b_id, m_id, tipo)
    
    return jsonify({"status": "received"}), 200


@app.route('/webhook', methods=['GET'])
def verificar():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge'), 200
    return "error", 403


def login_requerido(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        # chequeo de usuario y contraseña
        if not auth or not (auth.username == "diego" and auth.password == "diego"):
            return ('no autorizado', 401, {
                'WWW-Authenticate': 'Basic realm="Login Requerido"'
            })
        return f(*args, **kwargs)
    return decorated

# --- RUTAS DEL DASHBOARD ---

@app.route('/dashboard')
@login_requerido
def ver_dashboard():
    conn = get_db_connection()
    if not conn: return "error db connection"
    try:
        cur = conn.cursor()
        
        # traemos los leads ordenados
        cur.execute("SELECT * FROM leads ORDER BY fecha_actualizacion DESC")
        leads = cur.fetchall()
        
        # traemos las reuniones ordenadas por fecha de cita
        cur.execute("SELECT * FROM meetings ORDER BY fecha_hora ASC")
        meetings = cur.fetchall()
        
        html = """
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Dashboard Kat-IA</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { background-color: #f8f9fa; font-family: 'Segoe UI', sans-serif; }
                .navbar { background-color: #212529; margin-bottom: 2rem; }
                .card { border: none; box-shadow: 0 0.5rem 1rem rgba(0, 0, 0, 0.15); margin-bottom: 2rem; }
                .badge-info { background-color: #cee9fe; color: #333; }
            </style>
        </head>
        <body>
            <nav class="navbar navbar-dark shadow"><div class="container"><span class="navbar-brand mb-0 h1">Kat-IA | Lead & Agenda Manager</span></div></nav>

            <div class="container">
                
                <form id="formBorradoLeads" action="/eliminar_lote" method="POST">
                    <div class="card p-4">
                        <div class="d-flex justify-content-between align-items-center mb-4">
                            <h2 class="m-0">👥 Leads de WhatsApp</h2>
                            <button type="submit" class="btn btn-danger" onclick="return confirm('¿borrar seleccionados?')">Borrar Seleccionados</button>
                        </div>
                        
                        <div class="table-responsive">
                            <table class="table table-hover align-middle">
                                <thead class="table-dark">
                                    <tr>
                                        <th><input type="checkbox" id="selectAllLeads" class="form-check-input"></th>
                                        <th>Teléfono</th>
                                        <th>Nombre</th>
                                        <th>Email</th>
                                        <th>Último Perfil / Datos</th>
                                        <th>Actualizado</th>
                                        <th>Acciones</th>
                                    </tr>
                                </thead>
                                <tbody>
        """
        for l in leads:
            html += f"""
                                    <tr>
                                        <td><input type="checkbox" name="ids" value="{l['id']}" class="form-check-input lead-check"></td>
                                        <td>
                                            <span class="fw-bold">+{l['telefono']}</span><br>
                                            <div class="mt-1">
                                                <a href="https://wa.me/{str(l['telefono']).replace('+', '')}" target="_blank" class="btn btn-sm btn-success py-0 px-2" style="font-size: 0.75rem; border-radius: 10px;">
                                                    💬 WhatsApp
                                                </a>
                                                <a href="tel:+{str(l['telefono']).replace('+', '')}" class="btn btn-sm btn-primary py-0 px-2" style="font-size: 0.75rem; border-radius: 10px;">
                                                    📞 Llamar
                                                </a>
                                            </div>
                                        </td>
                                        <td>{l['nombre'] or '-'}</td>
                                        <td>{l['email'] or '-'}</td>
                                        <td><small class="text-muted">{l['ultimo_mensaje'] or '-'}</small></td>
                                        <td><small>{l['fecha_actualizacion']}</small></td>
                                        <td><a href='/eliminar/{l['id']}' class='btn btn-sm btn-outline-danger' onclick="return confirm('¿Seguro que querés borrar este lead?')">Borrar</a></td>
                                    </tr>
            """
        
        html += """
                                </tbody>
                            </table>
                        </div>
                    </div>
                </form>

                <div class="card p-4">
                    <div class="d-flex justify-content-between align-items-center mb-4">
                        <h2 class="m-0">📅 Agenda de Meetings (Google Meet)</h2>
                    </div>
                    
                    <div class="table-responsive">
                        <table class="table table-hover align-middle">
                            <thead class="table-dark">
                                <tr>
                                    <th>Teléfono Lead</th>
                                    <th>Fecha y Hora Cita</th>
                                    <th>Creada</th>
                                    <th>Acciones</th>
                                </tr>
                            </thead>
                            <tbody>
        """
        for m in meetings:
            html += f"""
                                <tr>
                                    <td>
                                        <span class="fw-bold">+{l['telefono']}</span><br>
                                        <div class="mt-1">
                                            <a href="https://wa.me/{str(l['telefono']).replace('+', '')}" target="_blank" class="btn btn-sm btn-success py-0 px-2" style="font-size: 0.75rem; border-radius: 10px;">
                                                💬 WhatsApp
                                            </a>
                                            <a href="tel:+{str(l['telefono']).replace('+', '')}" class="btn btn-sm btn-primary py-0 px-2" style="font-size: 0.75rem; border-radius: 10px;">
                                                📞 Llamar
                                            </a>
                                        </div>
                                    </td>
                                    <td><span class="badge bg-primary fs-6">{m['fecha_hora']} hs</span></td>
                                    <td><small class="text-muted">{m['fecha_creacion']}</small></td>
                                    <td><a href='/eliminar_reunion/{m['id']}' class='btn btn-sm btn-danger' onclick="return confirm('¿Seguro que querés cancelar y borrar esta reunión?')">Eliminar</a></td>
                                </tr>
            """
            
        html += """
                                </tbody>
                            </table>
                        </div>
                    </div>

            </div>

            <script>
                // lógica para seleccionar todos los leads
                document.getElementById('selectAllLeads').onclick = function() {
                    let checkboxes = document.getElementsByClassName('lead-check');
                    for (let checkbox of checkboxes) {
                        checkbox.checked = this.checked;
                    }
                }
            </script>
        </body>
        </html>
        """
        return html
    finally: 
        conn.close()

@app.route('/eliminar_lote', methods=['POST'])
@login_requerido
def eliminar_lote():
    ids = request.form.getlist('ids')
    if ids:
        conn = get_db_connection()
        cur = conn.cursor()
        format_strings = ','.join(['?'] * len(ids))
        cur.execute(f"DELETE FROM leads WHERE id IN ({format_strings})", tuple(ids))
        conn.commit()
        conn.close()
    return "<script>window.location.href='/dashboard';</script>"

@app.route('/eliminar/<int:id>')
@login_requerido 
def eliminar(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM leads WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return "<script>window.location.href='/dashboard';</script>"

@app.route('/eliminar_reunion/<int:id>')
@login_requerido 
def eliminar_reunion(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM meetings WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return "<script>window.location.href='/dashboard';</script>"

@app.route('/log')
@login_requerido
def ver_logs():
    try:
        with open("app.log", "r", encoding="utf-8") as f:
            lineas = f.readlines()
            # tomamos las últimas 100 líneas
            ultimas_lineas = lineas[-100:]
            
        logs_formateados = []
        for linea in ultimas_lineas:
            linea_html = linea.replace("<", "&lt;").replace(">", "&gt;")
            
            if " - ERROR - " in linea_html or "CRÍTICO" in linea_html:
                linea_html = f'<span class="error">{linea_html}</span>'
            elif " - INFO - " in linea_html:
                linea_html = f'<span class="info">{linea_html}</span>'
                
            logs_formateados.append(linea_html)
            
        logs_finales = "".join(logs_formateados)
            
        return f"""
        <html>
            <head>
                <title>Logs Kat-IA</title>
                <style>
                    body {{ background: #1e1e1e; color: #d4d4d4; font-family: monospace; padding: 20px; line-height: 1.4; }}
                    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #252526; padding: 15px; border-radius: 5px; }}
                    .info {{ color: #4fc1ff; }}
                    .error {{ color: #f44747; font-weight: bold; }}
                </style>
                <meta http-equiv="refresh" content="5">
            </head>
            <body>
                <h2>📜 Logs del Servidor (Kat-IA)</h2>
                <hr style="border: 0; border-top: 1px solid #333; margin-bottom: 20px;">
                <pre>{logs_finales}</pre>
                <script>window.scrollTo(0,document.body.scrollHeight);</script>
            </body>
        </html>
        """
    except FileNotFoundError:
        return "El archivo de log todavía no se creó o está vacío.", 404

if __name__ == '__main__':
    puerto = int(os.environ.get("PORT", 8000))
    # PRODUCCION
    # app.run(host='0.0.0.0', port=puerto, debug=False)
    # DESARROLLO
    app.run(host='0.0.0.0', port=puerto, debug=True)