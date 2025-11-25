import multiprocessing
import threading
import time
import queue
from flask import Flask, jsonify, render_template_string
import RPi.GPIO as GPIO

# --- CONFIGURACIÓN DE PINES (GPIO) ---
PIN_LED_ROJO = 17
PIN_LED_VERDE = 27
PIN_BOTON = 22      # Pin físico 15 (Entrada del botón)
PIN_ZUMBADOR = 23   # NUEVO: Pin físico 16 (Salida para sonido)

# --- ESTADOS DEL SISTEMA ---
ESTADO_BLOQUEADO = 0
ESTADO_ABIERTO = 1
ESTADO_ALARMA = 2

# ==========================================
# PROCESO 1: GESTIÓN DE HARDWARE
# ==========================================
def proceso_hardware(memoria_estado, cola_comandos):
    """
    Controla LEDs, Botón (pulsación larga) y Zumbador.
    """
    # Configuración GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIN_LED_ROJO, GPIO.OUT)
    GPIO.setup(PIN_LED_VERDE, GPIO.OUT)
    GPIO.setup(PIN_ZUMBADOR, GPIO.OUT) # Configuramos el zumbador como salida
    
    # Tu módulo de botón necesita PUD_DOWN
    GPIO.setup(PIN_BOTON, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    # --- HILO 1: LECTURA DEL BOTÓN ---
    def hilo_escuchar_boton():
        while True:
            if GPIO.input(PIN_BOTON) == GPIO.HIGH:
                start_time = time.time()
                boton_soltado = False

                # Detección de pulsación larga
                while GPIO.input(PIN_BOTON) == GPIO.HIGH:
                    if time.time() - start_time > 2.0:
                        print("[Hardware] ¡Pulsación Larga! -> ALARMA")
                        memoria_estado.value = ESTADO_ALARMA
                        while GPIO.input(PIN_BOTON) == GPIO.HIGH:
                            time.sleep(0.1)
                        boton_soltado = True
                        break 
                    time.sleep(0.05)
                
                # Detección de pulsación corta
                if not boton_soltado:
                    print("[Hardware] Pulsación Corta -> Abrir/Cerrar")
                    if memoria_estado.value == ESTADO_BLOQUEADO or memoria_estado.value == ESTADO_ALARMA:
                        memoria_estado.value = ESTADO_ABIERTO
                    else:
                        memoria_estado.value = ESTADO_BLOQUEADO
                
                time.sleep(0.3)
            time.sleep(0.05)

    # --- HILO 2: CONTROL DE LUCES Y SONIDO ---
    def hilo_control_leds():
        while True:
            estado_actual = memoria_estado.value
            
            if estado_actual == ESTADO_BLOQUEADO:
                # Todo apagado excepto LED Rojo
                GPIO.output(PIN_LED_ROJO, GPIO.HIGH)
                GPIO.output(PIN_LED_VERDE, GPIO.LOW)
                GPIO.output(PIN_ZUMBADOR, GPIO.LOW) # Silencio
                time.sleep(0.1)
                
            elif estado_actual == ESTADO_ABIERTO:
                # Todo apagado excepto LED Verde
                GPIO.output(PIN_LED_ROJO, GPIO.LOW)
                GPIO.output(PIN_LED_VERDE, GPIO.HIGH)
                GPIO.output(PIN_ZUMBADOR, GPIO.LOW) # Silencio
                time.sleep(0.1)
                
            elif estado_actual == ESTADO_ALARMA:
                # --- AQUÍ ESTÁ EL CAMBIO ---
                # Encendemos LED Rojo Y Zumbador a la vez
                GPIO.output(PIN_LED_ROJO, GPIO.HIGH)
                GPIO.output(PIN_ZUMBADOR, GPIO.HIGH) # ¡PIII!
                time.sleep(0.2) # Dura 0.2 segundos sonando
                
                # Apagamos ambos
                GPIO.output(PIN_LED_ROJO, GPIO.LOW)
                GPIO.output(PIN_ZUMBADOR, GPIO.LOW)  # Silencio
                GPIO.output(PIN_LED_VERDE, GPIO.LOW)
                time.sleep(0.2) # Silencio de 0.2 segundos


    # Iniciar hilos
    t1 = threading.Thread(target=hilo_escuchar_boton)
    t2 = threading.Thread(target=hilo_control_leds)
    t1.daemon = True
    t2.daemon = True
    t1.start()
    t2.start()

    # Bucle principal de escucha
    print("[Hardware] Listo. Botón Largo=Alarma con Sonido.")
    try:
        while True:
            try:
                orden = cola_comandos.get(timeout=0.5)
                print(f"[Hardware] Orden Web: {orden}")
                if orden == "ABRIR": memoria_estado.value = ESTADO_ABIERTO
                elif orden == "CERRAR": memoria_estado.value = ESTADO_BLOQUEADO
                elif orden == "ALARMA": memoria_estado.value = ESTADO_ALARMA
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
