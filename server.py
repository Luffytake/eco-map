import os
import sqlite3
import requests
from typing import Optional
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Eco Khujand API")

# --- Настройки Telegram-бота и администратора ---
BOT_TOKEN = "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0"  # Укажите токен вашего бота
ADMIN_ID = 5581941983                # Укажите ваш Telegram ID

# --- 1. Настройка CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Папка для загрузки фото отчётов
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

DB_NAME = "eco_khujand.db"

# --- 2. Инициализация и полная миграция базы данных SQLite ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            points INTEGER DEFAULT 0
        )
    """)
    
    # Таблица отчётов (создание, если таблицы ещё нет)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action_type TEXT,
            points INTEGER DEFAULT 0,
            comment TEXT,
            latitude REAL,
            longitude REAL,
            photo_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Проверка существующих колонок и добавление всех недостающих
    cursor.execute("PRAGMA table_info(reports)")
    existing_columns = [column[1] for column in cursor.fetchall()]
    
    required_columns = {
        "points": "INTEGER DEFAULT 0",
        "comment": "TEXT",
        "latitude": "REAL",
        "longitude": "REAL",
        "photo_path": "TEXT"
    }
    
    for col_name, col_type in required_columns.items():
        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE reports ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()

init_db()

# --- 3. Вспомогательная функция отправки фото админу ---
def send_telegram_notification(photo_path: str, caption_text: str):
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("BOT_TOKEN не указан, уведомление в Telegram пропущено.")
        return
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as photo_file:
            payload = {"chat_id": ADMIN_ID, "caption": caption_text, "parse_mode": "HTML"}
            files = {"photo": photo_file}
            requests.post(url, data=payload, files=files, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки уведомления в Telegram: {e}")

# --- 4. Эндпоинты API ---

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Eco Khujand Server is running"}

@app.get("/api/user/{user_id}")
def get_user_profile(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT INTO users (user_id, points) VALUES (?, 0)", (user_id,))
        conn.commit()
        points = 0
    else:
        points = row[0]
        
    conn.close()
    return {"user_id": user_id, "points": points}

@app.post("/api/report")
async def receive_report(
    user_id: int = Form(...),
    action_type: str = Form(...),
    points: int = Form(...),
    comment: Optional[str] = Form(""),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    photo: UploadFile = File(...)
):
    try:
        # Сохранение файла
        photo_filename = f"{user_id}_{photo.filename}"
        photo_path = os.path.join(UPLOAD_DIR, photo_filename)
        
        with open(photo_path, "wb") as buffer:
            content = await photo.read()
            buffer.write(content)

        # Сохранение отчёта и начисление баллов в БД
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO reports (user_id, action_type, points, comment, latitude, longitude, photo_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, action_type, points, comment, latitude, longitude, photo_path))

        cursor.execute("""
            INSERT INTO users (user_id, points) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET points = points + ?
        """, (user_id, points, points))

        conn.commit()
        conn.close()

        # Отправка уведомления администратору
        loc_str = f"{latitude}, {longitude}" if latitude and longitude else "Не указаны"
        caption = (
            f"📥 <b>Новый эко-отчёт!</b>\n\n"
            f"👤 <b>ID пользователя:</b> <code>{user_id}</code>\n"
            f"🎯 <b>Действие:</b> {action_type} (+{points} баллов)\n"
            f"💬 <b>Комментарий:</b> {comment or 'Отсутствует'}\n"
            f"📍 <b>Координаты:</b> {loc_str}"
        )
        send_telegram_notification(photo_path, caption)

        return {"status": "success", "message": "Отчёт успешно сохранён!", "added_points": points}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}") 
