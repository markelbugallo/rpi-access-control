import sqlite3
import threading
import time
import queue
import os
import RPi.GPIO as GPIO

# ==========================================
# 1. CONFIGURACIÓN DE PINES (BCM)
# ==========================================
PIN_LED_ROJO = 17
PIN_LED_VERDE = 27
PIN_LED_AZUL = 22
PIN_BOTON = 23
PIN_PIR = 25

# ======================
# 2. ESTADOS DEL SISTEMA
# ======================
ESTADO_BLOQUEADO = 0
ESTADO_ABIERTO = 1
ESTADO_ALARMA = 2
ESTADO_ESPERANDO_CODIGO = 3

# definimos id hardware, siempre es 2
ID_USUARIO_HARDWARE = 2


def proceso_hardware(memoria_estado, memoria_pir, memoria_modo, cola_comunicacion):

    CARPETA_ACTUAL = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(CARPETA_ACTUAL, 'data', 'accesos.db')

    configuracion = {"empresa_abierta": True}
    estado_interno = {"ultimo_reset": 0}

    def registrar_evento(accion):
        """Abre conexión, inserta evento y cierra conexión."""
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            query = "INSERT INTO historial (usuario_id, accion) VALUES (?, ?)"
            cur.execute(query, (ID_USUARIO_HARDWARE, accion))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[BD] No se pudo guardar historial: {e}")

    # --- CONFIGURACIÓN GPIO ---
    GPIO.setmode(GPIO.BCM)
    
    # Salidas
    GPIO.setup(PIN_LED_ROJO, GPIO.OUT)
    GPIO.setup(PIN_LED_VERDE, GPIO.OUT)
    GPIO.setup(PIN_LED_AZUL, GPIO.OUT)
    
    # Entradas
    GPIO.setup(PIN_BOTON, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(PIN_PIR, GPIO.IN)

    # Estado inicial: Bloqueado y luces apagadas
    memoria_estado.value = ESTADO_BLOQUEADO
    GPIO.output(PIN_LED_ROJO, GPIO.LOW)
    GPIO.output(PIN_LED_VERDE, GPIO.LOW)
    GPIO.output(PIN_LED_AZUL, GPIO.LOW)
    
    print("[SISTEMA] Hardware iniciado correctamente. Puerta bloqueada.")

    # ===================================
    # FUNCIÓN AUXILIAR: Lógica del Código 
    # ===================================
    def ejecutar_lectura_codigo():
        secuencia = []
        tiempo_inicio = time.time()
        print("[PUERTA-SEGURIDAD] Esperando secuencia manual...")
        
        while True:
            # 1. Verificar si se acabó el tiempo (15s)
            if time.time() - tiempo_inicio > 15.0:
                print("[CODIGO] Tiempo agotado --> ¡ALARMA!")
                memoria_estado.value = ESTADO_ALARMA
                registrar_evento("ALARMA: Tiempo de código agotado")
                return

            # 2. Detectar pulsación
            if GPIO.input(PIN_BOTON) == GPIO.HIGH:
                t_presion = time.time()
                
                # Esperar a que sueltes el botón
                while GPIO.input(PIN_BOTON) == GPIO.HIGH:
                    # Si mientras pulsas se acaban los 15s, salimos
                    if time.time() - tiempo_inicio > 15.0: break
                    time.sleep(0.05)
                
                duracion = time.time() - t_presion
                
                # 3. Clasificar la pulsación
                if 0.1 < duracion < 1.0:
                    print(f"[CODIGO] Pulsación corta ({duracion:.2f}s)")
                    secuencia.append('C')
                elif 2.0 <= duracion <= 3.0:
                    print(f"[CODIGO] Pulsación larga ({duracion:.2f}s)")
                    secuencia.append('L')
                else:
                    print(f"[CODIGO] Pulsación inválida ({duracion:.2f}s)")
                    secuencia.append('X')
                
                # 4. Comprobar si ganaste
                if len(secuencia) == 3:
                    if secuencia == ['C', 'C', 'L']:
                        print("[PUERTA-SEGURIDAD] Combinación CORRECTA --> Abriendo puerta")
                        memoria_estado.value = ESTADO_ABIERTO
                        registrar_evento("APERTURA: Código correcto")
                    else:
                        print(f"[PUERTA-SEGURIDAD] Combinación INCORRECTA ({secuencia}) --> ALARMA")
                        memoria_estado.value = ESTADO_ALARMA
                        registrar_evento(f"ALARMA: Código incorrecto {secuencia}")
                    return

            time.sleep(0.05)

    # =========================
    # HILO 1: GESTIÓN DEL BOTÓN
    # =========================
    def hilo_boton():
        while True:
            # Si hay alarma, el botón NO funciona (regla de seguridad)
            if memoria_estado.value == ESTADO_ALARMA:
                time.sleep(0.5)
                continue

            # Si detectamos que se pulsa el botón...
            if GPIO.input(PIN_BOTON) == GPIO.HIGH:
                
                # CASO: La puerta está BLOQUEADA
                if memoria_estado.value == ESTADO_BLOQUEADO:
                    start_time = time.time()
                    
                    # Esperamos mientras mantienes el dedo
                    while GPIO.input(PIN_BOTON) == GPIO.HIGH:
                        # Si aguantas más de 2 segundos -> MODO CÓDIGO
                        if time.time() - start_time >= 2.0:
                            memoria_estado.value = ESTADO_ESPERANDO_CODIGO
                            
                            # Esperamos a que sueltes para empezar a leer
                            while GPIO.input(PIN_BOTON) == GPIO.HIGH: time.sleep(0.1)
                            
                            # Llamamos a la función del lectura del codigo
                            ejecutar_lectura_codigo()
                            break
                        time.sleep(0.05)
                
                # CASO: La puerta está ABIERTA, si pulsas el boton se cierra
                elif memoria_estado.value == ESTADO_ABIERTO:
                    while GPIO.input(PIN_BOTON) == GPIO.HIGH: time.sleep(0.1)
                    memoria_estado.value = ESTADO_BLOQUEADO
                    print("[PUERTA-SEGURIDAD] Puerta cerrada manualmente con botón.")
                    registrar_evento("CIERRE: Botón manual")

            time.sleep(0.05)

    # =================================
    # HILO 2: SENSOR PIR (Día vs Noche)
    # =================================
    def hilo_sensor_pir():
        contador_ciclos_dia = 0
        print("[PIR] Vigilancia activa.")
        
        while True:
            memoria_pir.value = GPIO.input(PIN_PIR)
            # Si estamos introduciendo el código, el sensor no cuenta los ciclos que estamos ahi.
            if memoria_estado.value == ESTADO_ESPERANDO_CODIGO:
                contador_ciclos_dia = 0
                time.sleep(0.5)
                continue


            if time.time() - estado_interno["ultimo_reset"] < 5.0:
                contador_ciclos_dia = 0
                time.sleep(0.5)
                continue

            # El sensor solo nos importa si la puerta está BLOQUEADA
            if memoria_estado.value == ESTADO_BLOQUEADO:
                
                # Leemos sensor (1 = Movimiento, 0 = Quieto)
                hay_movimiento = GPIO.input(PIN_PIR)
                
                if hay_movimiento == 1:
                    
                    # --- SITUACIÓN A: (Empresa Cerrada) ---
                    if configuracion["empresa_abierta"] == False:
                        print("[SENSOR-PIR-NOCHE] ¡Intruso detectado! --> ALARMA")
                        memoria_estado.value = ESTADO_ALARMA
                        registrar_evento("ALARMA: Intruso detectado")
                    
                    # --- SITUACIÓN B: (Empresa Abierta) ---
                    else:
                        contador_ciclos_dia += 1
                        print(f"[PIR Día] Movimiento detectado: {contador_ciclos_dia}/3 veces.")
                        
                        if contador_ciclos_dia >= 3:
                            print(f"[SENSOR-PIR-DIA] Movimiento detectado: {contador_ciclos_dia}/3 avisos.")
                            memoria_estado.value = ESTADO_ALARMA
                            registrar_evento("ALARMA: Movimiento persistente")
                        else:
                            time.sleep(8.0)
                else:
                    contador_ciclos_dia = 0
            
            # Revisamos cada medio segundo
            time.sleep(0.5)

    # ============
    # HILO 3: LEDS
    # ============
    def hilo_luces():
        while True:
            estado = memoria_estado.value
            
            # 1. BLOQUEADO: Rojo Fijo
            if estado == ESTADO_BLOQUEADO:
                GPIO.output(PIN_LED_ROJO, GPIO.HIGH)
                GPIO.output(PIN_LED_VERDE, GPIO.LOW)
                GPIO.output(PIN_LED_AZUL, GPIO.LOW)
                time.sleep(0.1)

            # 2. ABIERTO: Verde Fijo
            elif estado == ESTADO_ABIERTO:
                GPIO.output(PIN_LED_ROJO, GPIO.LOW)
                GPIO.output(PIN_LED_VERDE, GPIO.HIGH)
                GPIO.output(PIN_LED_AZUL, GPIO.LOW)
                time.sleep(0.1)

            # 3. ESPERANDO CÓDIGO: Rojo Fijo + Azul Parpadeando
            elif estado == ESTADO_ESPERANDO_CODIGO:
                GPIO.output(PIN_LED_ROJO, GPIO.HIGH)
                GPIO.output(PIN_LED_VERDE, GPIO.LOW)
                
                # Azul parpadea
                GPIO.output(PIN_LED_AZUL, GPIO.HIGH)
                time.sleep(0.3)
                GPIO.output(PIN_LED_AZUL, GPIO.LOW)
                time.sleep(0.3)

            # 4. ALARMA: Rojo Parpadeando
            elif estado == ESTADO_ALARMA:
                GPIO.output(PIN_LED_VERDE, GPIO.LOW)
                GPIO.output(PIN_LED_AZUL, GPIO.LOW)
                
                GPIO.output(PIN_LED_ROJO, GPIO.HIGH)
                time.sleep(0.2)
                GPIO.output(PIN_LED_ROJO, GPIO.LOW)
                time.sleep(0.2)

    # --- INICIO DE LOS HILOS ---
    t1 = threading.Thread(target=hilo_boton, daemon=True)
    t2 = threading.Thread(target=hilo_sensor_pir, daemon=True)
    t3 = threading.Thread(target=hilo_luces, daemon=True)
    
    t1.start()
    t2.start()
    t3.start()

    # ===============
    # BUCLE PRINCIPAL
    # ===============
    try:
        while True:
            try:
                orden = cola_comunicacion.get(timeout=0.5)
                
                if orden == "SALIR":
                    print("[SISTEMA] Recibida orden de apagado. Deteniendo hilos...")
                    time.sleep(1.0)
                    break
                
                elif orden == "ALARMA_OFF": 
                    memoria_estado.value = ESTADO_BLOQUEADO
                    # IMPORTANTE: Guardamos la hora actual para activar la pausa de 5s
                    estado_interno["ultimo_reset"] = time.time()
                    print("[WEB] Alarma silenciada. Pausa de sensor (5s).")

                elif orden == "MODO_DIA": 
                    configuracion["empresa_abierta"] = True
                    # IMPORTANTE: Avisar a la web del cambio
                    memoria_modo.value = 1 
                    print("[WEB] Sensor cambiado a modo DÍA.")

                elif orden == "MODO_NOCHE": 
                    configuracion["empresa_abierta"] = False
                    # IMPORTANTE: Avisar a la web del cambio
                    memoria_modo.value = 0 
                    print("[WEB] Sensor cambiado a modo NOCHE.")

                elif orden == "ABRIR": 
                    memoria_estado.value = ESTADO_ABIERTO
                    print("[WEB] Abriendo puerta remotamente.")
                    
                elif orden == "CERRAR": 
                    memoria_estado.value = ESTADO_BLOQUEADO
                    print("[WEB] Cerrando puerta remotamente.")

            except queue.Empty: pass
    except KeyboardInterrupt:
        print("\n[SISTEMA] Interrupción de teclado detectada.")
    finally:
        GPIO.cleanup()
        print("[SISTEMA] Pines liberados. Apagado completo.")