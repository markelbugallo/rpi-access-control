import sqlite3
import datetime
from flask import Flask, jsonify, render_template, request, session, redirect, url_for

app = Flask(__name__)
app.secret_key = "clave_super_secreta_proyecto" 

web_memoria_estado = None
web_cola_comandos = None
DB_NAME = "accesos.db"

# --- RUTAS DE FLASK ---
@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    
    # Si no, mostramos el formulario de login
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    return render_template('dashboard.html', user=session['user'])

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    email = data.get('email')
    password = data.get('password')
    if not email or not password:
        return jsonify({"status": "error", "message": "Faltan credenciales"}), 400

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE email=? AND password=?", (email, password))
        usuario = cursor.fetchone()
        conn.close()
    except Exception as e:
        print(f"[BD Error] {e}")
        return jsonify({"status": "error", "message": "Error de base de datos"}), 500

    if usuario:
        session['user'] = email
        session['permiso'] = usuario[2]
        return jsonify({"status": "ok", "user": email})
    else:
        # Activar alarma en caso de intento fallido
        try:
            if web_cola_comandos is not None:
                web_cola_comandos.put("ALARMA")
        except Exception as e:
            print(f"[Web Error] No se pudo activar la alarma: {e}")
        return jsonify({"status": "error", "message": "Credenciales incorrectas"}), 401


@app.route('/api/whoami')
def api_whoami():
    if 'user' in session:
        return jsonify({"user": session['user']})
    return jsonify({"user": ""})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/estado')
def get_estado():
    if 'user' not in session: return jsonify({"estado": 0}), 401
    if web_memoria_estado: return jsonify({"estado": web_memoria_estado.value})
    return jsonify({"estado": 0})

@app.route('/api/control/<accion>')
def control(accion):
    if 'user' not in session: 
        return jsonify({"status": "error", "message": "No logueado"}), 401

    if accion == "abrir":
        if session.get('permiso') == 1:
            web_cola_comandos.put("ABRIR")
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                fecha_hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("UPDATE usuarios SET ultimo_acceso = ? WHERE email = ?", (fecha_hora, session['user']))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"[BD Error] {e}")
            return jsonify({"status": "ok"})
        else:
            return jsonify({"status": "denied"})
    
    elif accion == "cerrar":
        web_cola_comandos.put("CERRAR")
    elif accion == "alarma":
        web_cola_comandos.put("ALARMA")
        
    return jsonify({"status": "ok"})

def iniciar_servidor_web(memoria, cola):
    global web_memoria_estado, web_cola_comandos
    web_memoria_estado = memoria
    web_cola_comandos = cola
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)