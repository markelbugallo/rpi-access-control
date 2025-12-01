import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), '..', 'accesos.db')
DB = os.path.abspath(DB)

email = 'grupo14@gmail.com'
password = 'grupo14'
permiso = 1

print(f"Usando base de datos: {DB}")

conn = sqlite3.connect(DB)
cur = conn.cursor()
# Crear la tabla si no existe (esquema mínimo esperado por la aplicación)
cur.execute('''
CREATE TABLE IF NOT EXISTS usuarios (
    email TEXT PRIMARY KEY,
    password TEXT NOT NULL,
    permiso INTEGER DEFAULT 0,
    ultimo_acceso TEXT
)
''')

# Insertar o reemplazar el usuario
cur.execute('''REPLACE INTO usuarios (email, password, permiso) VALUES (?, ?, ?)''', (email, password, permiso))
conn.commit()
print(f"Usuario insertado/actualizado: {email} (permiso={permiso})")
conn.close()
