import multiprocessing
from hardware import proceso_hardware, ESTADO_BLOQUEADO
from web import iniciar_servidor_web

if __name__ == '__main__':
    print("--- Sistema de Acceso con Base de Datos, PIR y LED Azul ---")
    
    memoria_compartida = multiprocessing.Value('i', ESTADO_BLOQUEADO)
    cola_comunicacion = multiprocessing.Queue()

    proc_hw = multiprocessing.Process(target=proceso_hardware, args=(memoria_compartida, cola_comunicacion))
    proc_web = multiprocessing.Process(target=iniciar_servidor_web, args=(memoria_compartida, cola_comunicacion))

    proc_hw.start()
    proc_web.start()

    try:
        proc_hw.join()
        proc_web.join()
    except KeyboardInterrupt:
        print("Cerrando...")
        proc_hw.terminate()
        proc_web.terminate()