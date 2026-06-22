import sqlite3

DB_NAME = "database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        balance REAL DEFAULT 0.0,
        invited_by INTEGER,
        join_date TEXT,
        role TEXT DEFAULT 'user'
    )""")
    
    # Таблица товаров (img будет хранить путь к локальному файлу)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        price REAL NOT NULL,
        img TEXT
    )""")
    
    # Таблица заказов (с отслеживанием статуса)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        user_id INTEGER,
        total_amount REAL,
        payment_method TEXT,
        status TEXT DEFAULT 'pending',
        timestamp TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

init_db()
