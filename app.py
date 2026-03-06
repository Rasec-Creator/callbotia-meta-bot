import os, threading, time
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from database import init_db, get_db_connection, check_if_processed
from bot_logic import procesar_seguro, extraer_contenido
from ia_logic import locks

load_dotenv()
app = Flask(__name__)
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

# inicializacion db
threading.Thread(target=init_db).start()

# pool de hilos
executor = ThreadPoolExecutor(max_workers=10)

def limpiar_locks_viejos():
    while True:
        time.sleep(3600)
        ahora = time.time()
        for phone in list(locks.keys()):
            if ahora - locks[phone]['last_seen'] > 3600:
                if not locks[phone]['lock'].locked():
                    del locks[phone]
                    print(f"limpieza: lock eliminado para {phone}")

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
    print(f"DEBUG: Mensaje recibido en phone_id {phone_id_receptor}")

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

# Rutas de dashboard
@app.route('/dashboard')
@login_requerido
def ver_dashboard():
    conn = get_db_connection()
    if not conn: return "error db connection"
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM leads ORDER BY fecha_actualizacion DESC")
        leads = cur.fetchall()
        
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
                .card { border: none; box-shadow: 0 0.5rem 1rem rgba(0, 0, 0, 0.15); }
            </style>
        </head>
        <body>
            <nav class="navbar navbar-dark shadow"><div class="container"><span class="navbar-brand mb-0 h1">Kat-IA | Lead Manager</span></div></nav>

            <div class="container">
                <form id="formBorrado" action="/eliminar_lote" method="POST">
                    <div class="card p-4">
                        <div class="d-flex justify-content-between align-items-center mb-4">
                            <h2 class="m-0">Leads</h2>
                            <button type="submit" class="btn btn-danger" onclick="return confirm('¿borrar seleccionados?')">Borrar Seleccionados</button>
                        </div>
                        
                        <div class="table-responsive">
                            <table class="table table-hover align-middle">
                                <thead class="table-dark">
                                    <tr>
                                        <th><input type="checkbox" id="selectAll" class="form-check-input"></th>
                                        <th>Telefono</th>
                                        <th>Nombre</th>
                                        <th>Email</th>
                                        <th>Acciones</th>
                                    </tr>
                                </thead>
                                <tbody>
        """
        for l in leads:
            html += f"""
                <tr>
                    <td><input type="checkbox" name="ids" value="{l['id']}" class="form-check-input lead-check"></td>
                    <td><strong>{l['telefono']}</strong></td>
                    <td>{l['nombre'] or '-'}</td>
                    <td>{l['email'] or '-'}</td>
                    <td><a href='/eliminar/{l['id']}' class='btn btn-sm btn-outline-danger' onclick="return confirm('seguro?')">Borrar</a></td>
                </tr>
            """
        
        html += """
                                </tbody>
                            </table>
                        </div>
                    </div>
                </form>
            </div>

            <script>
                // logica para seleccionar todos
                document.getElementById('selectAll').onclick = function() {
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
    finally: conn.close()

@app.route('/eliminar_lote', methods=['POST'])
@login_requerido
def eliminar_lote():
    ids = request.form.getlist('ids')
    if ids:
        conn = get_db_connection()
        cur = conn.cursor()
        format_strings = ','.join(['%s'] * len(ids))
        cur.execute(f"DELETE FROM leads WHERE id IN ({format_strings})", tuple(ids))
        conn.commit()
        conn.close()
    return "<script>window.location.href='/dashboard';</script>"

@app.route('/eliminar/<int:id>')
@login_requerido # tambien protegido para que no borren por url
def eliminar(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM leads WHERE id = %s", (id,))
    conn.commit()
    conn.close()
    return "<script>window.location.href='/dashboard';</script>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))