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


def proceso_hardware(memoria_estado, cola_comandos):

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
            # Opcional: Imprimir también en consola para debug
            print(f"[BD Guardado] Acción: {accion}")
        except Exception as e:
            print(f"[ERROR BD] No se pudo guardar historial: {e}")

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
    
    print("[Hardware] Iniciado correctamente en Raspberry Pi.")

    # =========================================================
    # FUNCIÓN AUXILIAR: Lógica del Código Morse (15 segundos)
    # =========================================================
    def ejecutar_lectura_morse():
        secuencia = []
        tiempo_inicio = time.time()
        
        while True:
            # 1. Verificar si se acabó el tiempo (15s)
            if time.time() - tiempo_inicio > 15.0:
                print("[Código] ¡Tiempo agotado! -> ALARMA")
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
                    print(f" -> Corta ({duracion:.2f}s)")
                    secuencia.append('C')
                elif 2.0 <= duracion <= 3.0:
                    print(f" -> Larga ({duracion:.2f}s)")
                    secuencia.append('L')
                else:
                    print(f" -> Inválida ({duracion:.2f}s)")
                    secuencia.append('X')
                
                # 4. Comprobar si ganaste
                if len(secuencia) == 3:
                    if secuencia == ['C', 'C', 'L']:
                        print("[Código] ¡COMBINACIÓN CORRECTA! -> Abriendo puerta")
                        memoria_estado.value = ESTADO_ABIERTO
                        registrar_evento("APERTURA: Código correcto")
                    else:
                        print(f"[Código] Fallaste ({secuencia}) -> ALARMA")
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
                            print("[Botón] Mantenido 2s -> Iniciando secuencia...")
                            memoria_estado.value = ESTADO_ESPERANDO_CODIGO
                            
                            # Esperamos a que sueltes para empezar a leer
                            while GPIO.input(PIN_BOTON) == GPIO.HIGH: time.sleep(0.1)
                            
                            # Llamamos a la función del morse
                            ejecutar_lectura_morse()
                            break
                        time.sleep(0.05)
                
                # CASO: La puerta está ABIERTA, si pulsas el boton se cierra
                elif memoria_estado.value == ESTADO_ABIERTO:
                    while GPIO.input(PIN_BOTON) == GPIO.HIGH: time.sleep(0.1)
                    memoria_estado.value = ESTADO_BLOQUEADO
                    print("[Botón] Puerta cerrada manualmente.")
                    registrar_evento("CIERRE: Botón manual")

            time.sleep(0.05)

    # =================================
    # HILO 2: SENSOR PIR (Día vs Noche)
    # =================================
    def hilo_sensor_pir():
        contador_ciclos_dia = 0
        print("[PIR] Vigilancia activa.")
        
        while True:
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
                        print("[PIR Noche] ¡INTRUSO! Alarma inmediata.")
                        memoria_estado.value = ESTADO_ALARMA
                        registrar_evento("ALARMA: Intruso detectado")
                    
                    # --- SITUACIÓN B: (Empresa Abierta) ---
                    else:
                        contador_ciclos_dia += 1
                        print(f"[PIR Día] Movimiento detectado: {contador_ciclos_dia}/3 veces.")
                        
                        if contador_ciclos_dia >= 3:
                            print("[PIR Día] ¡Demasiado tiempo, sospechoso! -> ALARMA")
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
                orden = cola_comandos.get(timeout=0.5)
                
                if orden == "SALIR": break
                
                elif orden == "ALARMA_OFF": 
                    memoria_estado.value = ESTADO_BLOQUEADO
                    # IMPORTANTE: Guardamos la hora actual para activar la pausa de 5s
                    estado_interno["ultimo_reset"] = time.time()
                    print(" -> Alarma OFF (Pausa de 5s).")

                elif orden == "MODO_DIA": 
                    configuracion["empresa_abierta"] = True
                    # IMPORTANTE: Avisar a la web del cambio
                    memoria_estado.value = 1 
                    print(" -> Modo DÍA.")

                elif orden == "MODO_NOCHE": 
                    configuracion["empresa_abierta"] = False
                    # IMPORTANTE: Avisar a la web del cambio
                    memoria_estado.value = 0 
                    print(" -> Modo NOCHE.")

                elif orden == "ABRIR": 
                    memoria_estado.value = ESTADO_ABIERTO
                    
                elif orden == "CERRAR": 
                    memoria_estado.value = ESTADO_BLOQUEADO

            except queue.Empty: pass
    except KeyboardInterrupt:
        print("\nApagando sistema...")
    finally:
        GPIO.cleanup()