import multiprocessing
import threading
import time
import queue
import sqlite3
import datetime
from flask import Flask, jsonify, render_template_string, request, session, redirect, url_for
import RPi.GPIO as GPIO

# --- CONFIGURACIÓN DE PINES (GPIO) ---
PIN_LED_ROJO = 17
PIN_LED_VERDE = 27
PIN_BOTON = 22
PIN_ZUMBADOR = 23   # Opcional si tienes zumbador

# --- ESTADOS DEL SISTEMA ---
ESTADO_BLOQUEADO = 0
ESTADO_ABIERTO = 1
ESTADO_ALARMA = 2

# ==========================================
# PROCESO 1: GESTIÓN DE HARDWARE
# ==========================================
def proceso_hardware(memoria_estado, cola_comandos):
    """
    Controla LEDs y Botón físico.
    """
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIN_LED_ROJO, GPIO.OUT)
    GPIO.setup(PIN_LED_VERDE, GPIO.OUT)
    GPIO.setup(PIN_ZUMBADOR, GPIO.OUT) # Si tienes zumbador
    GPIO.setup(PIN_BOTON, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    # --- HILO 1: LECTURA DEL BOTÓN ---
    def hilo_escuchar_boton():
        while True:
            if GPIO.input(PIN_BOTON) == GPIO.HIGH:
                start_time = time.time()
                boton_soltado = False

                while GPIO.input(PIN_BOTON) == GPIO.HIGH:
                    if time.time() - start_time > 2.0:
                        print("[Hardware] ¡Pulsación Larga! -> ALARMA")
                        memoria_estado.value = ESTADO_ALARMA
                        while GPIO.input(PIN_BOTON) == GPIO.HIGH:
                            time.sleep(0.1)
                        boton_soltado = True
                        break 
                    time.sleep(0.05)
                
                if not boton_soltado:
                    print("[Hardware] Pulsación Corta")
                    if memoria_estado.value == ESTADO_BLOQUEADO or memoria_estado.value == ESTADO_ALARMA:
                        memoria_estado.value = ESTADO_ABIERTO
                    else:
                        memoria_estado.value = ESTADO_BLOQUEADO
                
                time.sleep(0.3)
            time.sleep(0.05)

    # --- HILO 2: CONTROL DE LUCES ---
    def hilo_control_leds():
        while True:
            estado_actual = memoria_estado.value
            
            if estado_actual == ESTADO_BLOQUEADO:
                GPIO.output(PIN_LED_ROJO, GPIO.HIGH)
                GPIO.output(PIN_LED_VERDE, GPIO.LOW)
                GPIO.output(PIN_ZUMBADOR, GPIO.LOW)
                time.sleep(0.1)
                
            elif estado_actual == ESTADO_ABIERTO:
                GPIO.output(PIN_LED_ROJO, GPIO.LOW)
                GPIO.output(PIN_LED_VERDE, GPIO.HIGH)
                GPIO.output(PIN_ZUMBADOR, GPIO.LOW)
                time.sleep(0.1)
                
            elif estado_actual == ESTADO_ALARMA:
                # Alarma visual y sonora
                GPIO.output(PIN_LED_ROJO, GPIO.HIGH)
                GPIO.output(PIN_ZUMBADOR, GPIO.HIGH) # Sonido
                time.sleep(0.2)
                GPIO.output(PIN_LED_ROJO, GPIO.LOW)
                GPIO.output(PIN_ZUMBADOR, GPIO.LOW)
                GPIO.output(PIN_LED_VERDE, GPIO.LOW)
                time.sleep(0.2)

    # Iniciar hilos
    t1 = threading.Thread(target=hilo_escuchar_boton)
    t2 = threading.Thread(target=hilo_control_leds)
    t1.daemon = True
    t2.daemon = True
    t1.start()
    t2.start()

    # Bucle principal
    print("[Hardware] Hardware listo.")
    try:
        while True:
            try:
                orden = cola_comandos.get(timeout=0.5)
                if orden == "ABRIR": memoria_estado.value = ESTADO_ABIERTO
                elif orden == "CERRAR": memoria_estado.value = ESTADO_BLOQUEADO
                elif orden == "ALARMA": memoria_estado.value = ESTADO_ALARMA
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()

# ==========================================
# PROCESO 2: SERVIDOR WEB (CON LOGIN Y BASE DE DATOS)
# ==========================================
app = Flask(__name__)
app.secret_key = "clave_super_secreta_proyecto" # Necesario para sesiones

web_memoria_estado = None
web_cola_comandos = None
DB_NAME = "accesos.db"

# --- HTML DEL LOGIN ---
HTML_LOGIN = """
<!DOCTYPE html>
<html>
<head>
    <title>Login RPi</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; text-align: center; padding: 50px; background: #2c3e50; color: white;}
        input { padding: 10px; margin: 10px; width: 80%; max-width: 300px; border-radius: 5px; border: none;}
        button { padding: 10px 20px; background: #2ecc71; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px;}
        .error { color: #e74c3c; font-weight: bold; }
    </style>
</head>
<body>
    <h2>Acceso Seguro</h2>
    {% if error %}
        <p class="error">{{ error }}</p>
    {% endif %}
    <form method="post">
        <input type="email" name="email" placeholder="Gmail" required><br>
        <input type="password" name="password" placeholder="Contraseña" required><br>
        <button type="submit">Entrar</button>
    </form>
</body>
</html>
"""

# --- HTML DEL DASHBOARD (PANEL DE CONTROL) ---
HTML_DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
    <title>Panel de Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; text-align: center; padding: 20px; background: #f4f4f9; }
        .status-box { padding: 20px; border-radius: 10px; color: white; margin: 20px auto; max-width: 300px;}
        .red { background-color: #e74c3c; }
        .green { background-color: #2ecc71; }
        .orange { background-color: #f39c12; animation: blink 0.5s infinite; }
        button { padding: 15px 30px; font-size: 18px; margin: 10px; cursor: pointer; }
        .logout { margin-top: 50px; display: inline-block; color: #7f8c8d; text-decoration: none;}
        @keyframes blink { 50% { opacity: 0.5; } }
    </style>
    <audio id="alarma-audio" loop>
        <source src="https://assets.mixkit.co/sfx/preview/mixkit-security-facility-breach-alarm-994.mp3" type="audio/mpeg">
    </audio>
    <script>
        var audio = document.getElementById("alarma-audio");
        
        function actualizarEstado() {
            fetch('/api/estado')
                .then(response => response.json())
                .then(data => {
                    const box = document.getElementById('status-box');
                    const text = document.getElementById('status-text');
                    
                    if (data.estado == 0) {
                        box.className = 'status-box red';
                        text.innerText = 'BLOQUEADO';
                        audio.pause();
                        audio.currentTime = 0;
                    } else if (data.estado == 1) {
                        box.className = 'status-box green';
                        text.innerText = 'ABIERTO';
                        audio.pause();
                        audio.currentTime = 0;
                    } else {
                        box.className = 'status-box orange';
                        text.innerText = '¡ALARMA!';
                        if (audio.paused) audio.play().catch(e => console.log(e));
                    }
                });
        }
        setInterval(actualizarEstado, 1000);

        function enviarOrden(orden) {
            fetch('/api/control/' + orden)
                .then(response => response.json())
                .then(data => {
                    if(data.status == 'denied') alert("¡No tienes permiso para hacer esto!");
                });
            setTimeout(actualizarEstado, 200); 
        }
    </script>
</head>
<body>
    <h1>Bienvenido, {{ user }}</h1>
    
    <div id="status-box" class="status-box red">
        <h2 id="status-text">Cargando...</h2>
    </div>

    <button onclick="enviarOrden('abrir')">ABRIR PUERTA</button>
    <button onclick="enviarOrden('cerrar')">BLOQUEAR</button>
    <br>
    <button onclick="enviarOrden('alarma')" style="background:black; color:white;">ACTIVAR ALARMA</button>
    
    <br>
    <a href="/logout" class="logout">Cerrar Sesión</a>
</body>
</html>
"""

# --- RUTAS DE FLASK ---

@app.route('/', methods=['GET', 'POST'])
def login():
    # Si ya está logueado, lo mandamos al dashboard
    if 'user' in session:
        return render_template_string(HTML_DASHBOARD, user=session['user'])
    
    error = None
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Conectar a la base de datos para verificar usuario
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Buscamos el usuario por email y contraseña
        cursor.execute("SELECT * FROM usuarios WHERE email=? AND password=?", (email, password))
        usuario = cursor.fetchone() # Devuelve una tupla o None
        conn.close()
        
        if usuario:
            # usuario[0]=email, [1]=pass, [2]=permiso
            session['user'] = email
            session['permiso'] = usuario[2] # Guardamos si tiene permiso (1 o 0)
            return redirect(url_for('login'))
        else:
            error = "Credenciales incorrectas"
            
    return render_template_string(HTML_LOGIN, error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('permiso', None)
    return redirect(url_for('login'))

@app.route('/api/estado')
def get_estado():
    if 'user' not in session: return jsonify({"estado": 0}), 401
    if web_memoria_estado: return jsonify({"estado": web_memoria_estado.value})
    return jsonify({"estado": 0})

@app.route('/api/control/<accion>')
def control(accion):
    # Verificamos si está logueado
    if 'user' not in session: 
        return jsonify({"status": "error", "message": "No logueado"}), 401

    # Verificamos permisos de base de datos para acciones críticas (Abrir)
    if accion == "abrir":
        if session.get('permiso') == 1:
            web_cola_comandos.put("ABRIR")
            
            # --- GUARDAR EN BASE DE DATOS LA FECHA ---
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                fecha_hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("UPDATE usuarios SET ultimo_acceso = ? WHERE email = ?", (fecha_hora, session['user']))
                conn.commit()
                conn.close()
                print(f"[BD] Acceso registrado para {session['user']} a las {fecha_hora}")
            except Exception as e:
                print(f"[BD Error] {e}")

            return jsonify({"status": "ok"})
        else:
            # Si permiso es 0
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

# ==========================================
# MAIN
# ==========================================
if __name__ == '__main__':
    print("--- Sistema de Acceso con Base de Datos ---")
    
    # Crear cola y memoria compartida
    memoria_compartida = multiprocessing.Value('i', ESTADO_BLOQUEADO)
    cola_comunicacion = multiprocessing.Queue()

    # Definir Procesos
    proc_hw = multiprocessing.Process(target=proceso_hardware, args=(memoria_compartida, cola_comunicacion))
    proc_web = multiprocessing.Process(target=iniciar_servidor_web, args=(memoria_compartida, cola_comunicacion))

    # Arrancar
    proc_hw.start()
    proc_web.start()

    try:
        proc_hw.join()
        proc_web.join()
    except KeyboardInterrupt:
        print("Cerrando...")
        proc_hw.terminate()
        proc_web.terminate()
        GPIO.cleanup()