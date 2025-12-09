import multiprocessing
import os
import subprocess
import sys
from hardware import proceso_hardware, ESTADO_BLOQUEADO
from web import iniciar_servidor_web

def comprobar_e_instalar_bd():
    # CONFIGURAR RUTAS
    CARPETA_PROYECTO = os.path.dirname(os.path.abspath(__file__))
    RUTA_DB = os.path.join(CARPETA_PROYECTO, 'data', 'accesos.db')
    RUTA_SETUP = os.path.join(CARPETA_PROYECTO, 'scripts', 'setup-db.py')

    # Comprobar si existe la BD
    existe = os.path.exists(RUTA_DB)
    tamano_valido = False

    if existe:
        if os.path.getsize(RUTA_DB) > 0:
            tamano_valido = True

    if not tamano_valido:
        print("[AVISO] La base de datos no existe o está vacía/corrupta.")
        
        # Verificar que existe el script de setup
        if not os.path.exists(RUTA_SETUP):
            print(f"[ERROR CRÍTICO] No encuentro el archivo de instalación en: {RUTA_SETUP}")
            sys.exit(1)

        try:
            if existe: 
                os.remove(RUTA_DB)

            # Ejecutar el setup como un subproceso
            subprocess.run([sys.executable, RUTA_SETUP], check=True)
            print("\n[Main] Instalación completada. Continuando arranque...\n")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] El setup falló con código {e.returncode}.")
            sys.exit(1)
        except Exception as e:
            print(f"[ERROR] Fallo inesperado al lanzar setup: {e}")
            sys.exit(1)
    else:
        print("[Main] Base de datos encontrada. Todo correcto.")

if __name__ == '__main__':
    comprobar_e_instalar_bd()

    # MEMORIAS COMPARTIDAS
    memoria_estado = multiprocessing.Value('i', ESTADO_BLOQUEADO)
    memoria_pir = multiprocessing.Value('i', 0)
    memoria_modo = multiprocessing.Value('i', 1)

    cola_comunicacion = multiprocessing.Queue()

    proc_hw = multiprocessing.Process(target=proceso_hardware, args=(memoria_estado, memoria_pir, memoria_modo, cola_comunicacion))
    proc_web = multiprocessing.Process(target=iniciar_servidor_web, args=(memoria_estado, memoria_pir, memoria_modo, cola_comunicacion))

    proc_hw.start()
    proc_web.start()

    try:
        proc_hw.join()
        proc_web.join()
    except KeyboardInterrupt:
        cola_comunicacion.put("SALIR")
        proc_hw.join(timeout=2)

        if proc_hw.is_alive():
            print("[Main] El hardware tardaba mucho, forzando cierre...")
            proc_hw.terminate()

        proc_web.terminate()

        print("[Main] Sistema apagado completamente.")