import threading
import time
import queue

try:
    import RPi.GPIO as GPIO
except Exception:
    class _GPIOMock:
        BCM = 'BCM'
        HIGH = 1
        LOW = 0
        PUD_DOWN = 'PUD_DOWN'

        def __init__(self):
            self._pins = {}

        def setmode(self, mode):
            print('[GPIO Stub] setmode', mode)

        def setup(self, pin, mode, pull_up_down=None):
            self._pins[pin] = self.LOW
            print(f'[GPIO Stub] setup pin {pin} mode {mode} pull {pull_up_down}')

        def input(self, pin):
            return self._pins.get(pin, self.LOW)

        def output(self, pin, value):
            self._pins[pin] = value

        def cleanup(self):
            print('[GPIO Stub] cleanup')

    GPIO = _GPIOMock()

# --- CONFIGURACIÓN DE PINES (GPIO) ---
PIN_LED_ROJO = 17
PIN_LED_VERDE = 27
PIN_BOTON = 22
PIN_ZUMBADOR = 23   
PIN_PIR = 24        # Sensor Mini PIR v1.0 (Pin físico 18)
PIN_LED_AZUL = 25   # LED Azul de presencia (Pin físico 22)

# --- ESTADOS DEL SISTEMA ---
ESTADO_BLOQUEADO = 0
ESTADO_ABIERTO = 1
ESTADO_ALARMA = 2


def proceso_hardware(memoria_estado, cola_comandos):
    """
    Controla LEDs, Botón físico, Zumbador y Sensor PIR.
    """
    GPIO.setmode(GPIO.BCM)
    # Salidas
    GPIO.setup(PIN_LED_ROJO, GPIO.OUT)
    GPIO.setup(PIN_LED_VERDE, GPIO.OUT)
    GPIO.setup(PIN_ZUMBADOR, GPIO.OUT)
    GPIO.setup(PIN_LED_AZUL, GPIO.OUT) # Nuevo LED Azul
    
    # Entradas
    GPIO.setup(PIN_BOTON, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(PIN_PIR, GPIO.IN)       # El PIR envía señal HIGH/LOW

    # --- HILO 1: LECTURA DEL BOTÓN ---
    def hilo_escuchar_boton():
        while True:
            if GPIO.input(PIN_BOTON) == GPIO.HIGH:
                start_time = time.time()
                boton_soltado = False

                while GPIO.input(PIN_BOTON) == GPIO.HIGH:
                    if time.time() - start_time > 2.0:
                        print("[Hardware] ¡Pulsación Larga! -> ALARMA MANUAL")
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

    # --- HILO 2: CONTROL DE LUCES (ROJO/VERDE/ZUMBADOR) ---
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
                # Alarma visual (Rojo) y sonora
                GPIO.output(PIN_LED_ROJO, GPIO.HIGH)
                GPIO.output(PIN_ZUMBADOR, GPIO.HIGH)
                time.sleep(0.2)
                GPIO.output(PIN_LED_ROJO, GPIO.LOW)
                GPIO.output(PIN_ZUMBADOR, GPIO.LOW)
                GPIO.output(PIN_LED_VERDE, GPIO.LOW)
                time.sleep(0.2)

    # --- HILO 3: VIGILANCIA PIR (NUEVO) ---
    def hilo_sensor_pir():
        print("[Sensor] Iniciando vigilancia con Mini PIR...")
        while True:
            # El Mini PIR pone el pin en HIGH cuando detecta movimiento
            if GPIO.input(PIN_PIR) == 1:
                # Feedback visual: Encender LED Azul
                GPIO.output(PIN_LED_AZUL, GPIO.HIGH)
                
                # LÓGICA DE SEGURIDAD:
                # Si el sistema está BLOQUEADO y hay movimiento -> ALARMA
                if memoria_estado.value == ESTADO_BLOQUEADO:
                    print("[Sensor] ¡MOVIMIENTO DETECTADO EN ZONA BLOQUEADA! -> ALARMA")
                    memoria_estado.value = ESTADO_ALARMA
                
                # Mantenemos el LED azul encendido un poco para que se vea bien
                time.sleep(1.0) 
            else:
                GPIO.output(PIN_LED_AZUL, GPIO.LOW)
            
            time.sleep(0.1) # Pequeña pausa para no saturar CPU

    # Iniciar hilos
    t1 = threading.Thread(target=hilo_escuchar_boton)
    t2 = threading.Thread(target=hilo_control_leds)
    t3 = threading.Thread(target=hilo_sensor_pir) # Nuevo hilo del PIR
    
    t1.daemon = True
    t2.daemon = True
    t3.daemon = True
    
    t1.start()
    t2.start()
    t3.start()

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