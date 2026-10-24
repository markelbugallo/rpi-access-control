import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(PACKAGE_DIR))
DATA_DIR = os.path.join(PROJECT_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'accesos.db')
