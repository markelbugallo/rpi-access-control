import sqlite3
import os
import getpass

def main():
    print("========================================")
    print("   CONFIGURACIÓN INICIAL DEL SISTEMA    ")
    print("========================================")

    # CONFIGURACION DE RUTAS
    CARPETA_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
    CARPETA_PROYECTO = os.path.dirname(CARPETA_SCRIPTS)
    DATA_DIR = os.path.join(CARPETA_PROYECTO, 'data')
    DB_PATH = os.path.join(DATA_DIR, 'accesos.db')

    # COMPROBAR SI YA EXISTE LA BD (en ese caso se detiene)
    if os.path.exists(DB_PATH):
        print(f"\n[AVISO] La base de datos YA EXISTE en:")
        print(f" -> {DB_PATH}")
        return

    # SI NO EXISTE LA BD, PREGUNTAMOS DATOS PARA CREAR LA BD CON UN USUARIO ADMIN
    # Crear carpeta data si no existe
    if not os.path.exists(DATA_DIR):
        try:
            os.makedirs(DATA_DIR)
            print(f"[INFO] Carpeta 'data' creada.")
        except OSError as e:
            print(f"[ERROR] No se pudo crear la carpeta data: {e}")
            return

    # Pedir datos al usuario
    print("\n--- CREACIÓN DEL ADMINISTRADOR ---")
    while True:
        email = input("Introduce el email para el Admin: ").strip()
        if email: 
            break
        print("El email no puede estar vacío.")

    while True:
        p1 = getpass.getpass("Introduce la contraseña: ")
        p2 = getpass.getpass("Repite la contraseña: ")
        
        if p1 == p2 and len(p1) > 0:
            password_final = p1
            break
        print("Error: Las contraseñas no coinciden o están vacías. Inténtalo de nuevo.")

    # CREAR TABLAS Y INSERTAR  
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # Tabla Usuarios
        cur.execute('''
        CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            permiso INTEGER DEFAULT 0
        )
        ''')

        # Tabla Historial
        cur.execute('''
        CREATE TABLE historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            accion TEXT,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
        )
        ''')

        # Insertar el Admin con los datos que acabamos de pedir
        cur.execute("INSERT OR IGNORE INTO usuarios (email, password, permiso) VALUES (?, ?, ?)", (email, password_final, 1))

        # Insertar un usuario hardware para registrar los movimientos que se hacen desde el boton fisico
        cur.execute("INSERT OR IGNORE INTO usuarios (id, email, password, permiso) VALUES (?, ?, ?, ?)", (2, 'sistema@hardware', 'SYSTEM_INTERNAL_USER_DO_NOT_LOGIN', 0))

        conn.commit()
        conn.close()
        
        print("\n[ÉXITO] Instalación completada correctamente.")
    except Exception as e:
        print(f"\n[ERROR] Fallo al crear la base de datos: {e}")
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)

if __name__ == '__main__':
    main()