from flask import cli
import sqlite3
import logging
from flask import Flask, jsonify, render_template, request, session, redirect, url_for

from .config import DB_PATH as DB_NAME

app = Flask(__name__)
app.secret_key = "clave_super_secreta_proyecto" 

# VARIABLES COMPARTIDAS (Conectan con hardware.py)
web_memoria_estado = None
web_memoria_pir = None
web_memoria_modo = None
web_cola_comandos = None

# FUNCIONES AUXILIARES
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def registrar_evento(usuario_id, accion):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO historial (usuario_id, accion) VALUES (?, ?)", (usuario_id, accion))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Log Error] {e}")


# RUTAS DE FLASK
@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('index'))
    
    # Si no esta logeado, mostramos el formulario de login
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({"status": "error", "message": "Faltan credenciales"}), 400

    conn = get_db_connection()
    usuario = conn.execute("SELECT * FROM usuarios WHERE email=? AND password=?", (email, password)).fetchone()
    conn.close()

    if usuario:
        session['user_id'] = usuario['id']
        session['user'] = usuario['email']
        session['permiso'] = usuario['permiso']

        registrar_evento(usuario['id'], "LOGIN_EXITOSO")
        print(f"[WEB] Login exitoso: {email}")
        return jsonify({"status": "ok", "user": email})
    else:
        return jsonify({"status": "error", "message": "Credenciales incorrectas"}), 401

@app.route('/logout')
def logout():
    if 'user' in session:
        registrar_evento(session.get('user'), "LOGOUT")
    session.clear()
    return redirect(url_for('login'))

# PAGINA PRINCIPAL (index)
@app.route('/index')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    es_admin = (session.get('permiso') == 1)
    return render_template('index.html', user=session['user'], es_admin=es_admin)


# RUTAS ADMIN
@app.route('/admin/usuarios', methods=['GET', 'POST'])
def admin_usuarios():
    # Protección: Solo admin (permiso 1)
    if session.get('permiso') != 1: return redirect(url_for('index'))

    conn = get_db_connection()
    
    # CREAR USUARIO
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'crear':
            email = request.form.get('email')
            pwd = request.form.get('password')
            try:
                # Todos los usuarios que no sean admin, permiso 0
                conn.execute("INSERT INTO usuarios (email, password, permiso) VALUES (?, ?, 0)", (email, pwd))
                conn.commit()
                registrar_evento(session['user_id'], f"CREAR_USUARIO: {email}")
                print(f"[WEB] Admin ha creado el usuario: {email}")
            except sqlite3.IntegrityError:
                print(f"[WEB] Error: Intento de crear email duplicado ({email})")
                pass

        elif action == 'borrar':
            user_id = request.form.get('user_id')
            # Evitar borrarse a sí mismo o al admin principal (ID 1)
            if str(user_id) != '1' and str(user_id) != str(session['user_id']):
                conn.execute("DELETE FROM usuarios WHERE id=?", (user_id,))
                conn.commit()
                registrar_evento(session['user_id'], f"BORRAR_USUARIO_ID: {user_id}")
                print(f"[WEB] Admin ha eliminado al usuario ID: {user_id}")

    # LEER USUARIOS
    usuarios = conn.execute("SELECT * FROM usuarios").fetchall()
    conn.close()
    return render_template('admin_usuarios.html', usuarios=usuarios)

@app.route('/admin/historial')
def admin_historial():
    if session.get('permiso') != 1: return redirect(url_for('index'))

    conn = get_db_connection()

    query = """
        SELECT h.id, h.fecha, h.accion, u.email 
        FROM historial h 
        LEFT JOIN usuarios u ON h.usuario_id = u.id 
        ORDER BY h.fecha DESC LIMIT 100
    """
    logs = conn.execute(query).fetchall()
    conn.close()
    return render_template('admin_historial.html', logs=logs)


# API PARA VER ESTADO
@app.route('/api/estado')
def get_estado():
    if 'user' not in session: return jsonify({"estado": 0}), 401

    # Leemos los valores compartidos
    estado_actual = web_memoria_estado.value if web_memoria_estado else 0
    sensor_activo = web_memoria_pir.value if web_memoria_pir else 0
    modo_dia = web_memoria_modo.value if web_memoria_modo else 1

    return jsonify({
        "estado": estado_actual,
        "sensor": sensor_activo,
        "modo_dia": modo_dia
    })  

@app.route('/api/control/<accion>')
def control(accion):
    if 'user' not in session: 
        return jsonify({"status": "error", "message": "No logueado"}), 401

    id = session['user_id']

    # log visual
    print(f"[WEB] Enviando comando: {accion.upper()}")

    if accion == "abrir":
        web_cola_comandos.put("ABRIR")
        registrar_evento(id, "APERTURA: Remoto")
    elif accion == "cerrar":
        web_cola_comandos.put("CERRAR")
        registrar_evento(id, "CIERRE: Remoto")
    elif accion == "alarma_off":
        web_cola_comandos.put("ALARMA_OFF")
        registrar_evento(id, "DESACTIVAR_ALARMA")
    elif accion == "modo_dia":
        web_cola_comandos.put("MODO_DIA")
        registrar_evento(id, "CAMBIO_MODO_DIA")

    elif accion == "modo_noche":
        web_cola_comandos.put("MODO_NOCHE")
        registrar_evento(id, "CAMBIO_MODO_NOCHE")

        
    return jsonify({"status": "ok"})

def iniciar_servidor_web(memoria_estado, memoria_pir, memoria_modo, cola):
    global web_memoria_estado, web_memoria_pir, web_memoria_modo, web_cola_comandos

    web_memoria_estado = memoria_estado
    web_memoria_pir = memoria_pir
    web_memoria_modo = memoria_modo
    web_cola_comandos = cola

    # silencia logs de peticiones de la terminal
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    # silencia banner de arranque flask
    cli.show_server_banner = lambda *_: None
    
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)