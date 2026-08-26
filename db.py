import sqlite3

DB_NAME = "eco_khujand.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            points INTEGER DEFAULT 0
        )
    ''')
    
    # Таблица отчётов пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action_type TEXT,
            points_awarded INTEGER,
            status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
            photo_url TEXT,
            latitude REAL,
            longitude REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_user_profile(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, full_name, points FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"user_id": row[0], "username": row[1], "full_name": row[2], "points": row[3]}
    return None

def register_user_if_not_exists(user_id: int, username: str, full_name: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (user_id, username, full_name, points)
        VALUES (?, ?, ?, 0)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            full_name = excluded.full_name
    ''', (user_id, username, full_name))
    conn.commit()
    conn.close()

def add_points(user_id: int, points: int, action_type: str, photo_url: str = None, lat: float = None, lon: float = None):
    """Начисляет баллы пользователю и сохраняет запись об отчёте."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Обновляем баланс баллов пользователя
    cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (points, user_id))
    
    # 2. Логируем отчёт в историю
    cursor.execute('''
        INSERT INTO reports (user_id, action_type, points_awarded, status, photo_url, latitude, longitude)
        VALUES (?, ?, ?, 'approved', ?, ?, ?)
    ''', (user_id, action_type, points, photo_url, lat, lon))
    
    conn.commit()
    conn.close()
    
    # Возвращаем обновлённый профиль
    return get_user_profile(user_id)