import os
import sqlite3
import aiohttp
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import json

DB_NAME = "eco_khujand.db"
BOT_TOKEN = os.getenv("BOT_TOKEN", "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0")
ADMIN_ID = os.getenv("ADMIN_ID", "5581941983")

app = FastAPI(title="Eco Khujand API")

# --- Настройка CORS для работы с Telegram WebApp ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Инициализация и ПОЛНАЯ автомиграция БД ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            avatar_url TEXT DEFAULT '',
            points INTEGER DEFAULT 0
        )
    """)

    # Базовая таблица отчётов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action_type TEXT,
            comment TEXT,
            latitude REAL,
            longitude REAL,
            photo_path TEXT,
            points INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Автоматическая проверка и добавление ЛЮБЫХ отсутствующих колонок в reports
    cursor.execute("PRAGMA table_info(reports)")
    existing_columns = [column[1] for column in cursor.fetchall()]

    required_columns = {
        "points": "INTEGER DEFAULT 0",
        "comment": "TEXT DEFAULT ''",
        "latitude": "REAL DEFAULT 0.0",
        "longitude": "REAL DEFAULT 0.0",
        "photo_path": "TEXT DEFAULT ''",
        "action_type": "TEXT DEFAULT ''",
        "status": "TEXT DEFAULT 'pending'",
    }

    for col_name, col_type in required_columns.items():
        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE reports ADD COLUMN {col_name} {col_type}")

    # Таблица медалей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS medals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            medal_key TEXT,
            photo_before TEXT,
            photo_after TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, medal_key)
        )
    """)

    conn.commit()
    conn.close()


# Запускаем миграцию при старте сервера
init_db()


# --- Отправка уведомлений в Telegram админу ---
async def send_telegram_photo_with_buttons(photo_bytes: bytes, caption: str, report_id: int):
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("BOT_TOKEN не настроен!")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Одобрить", "callback_data": f"approve_{report_id}"},
                {"text": "❌ Отклонить", "callback_data": f"reject_{report_id}"},
            ]
        ]
    }

    data = aiohttp.FormData()
    data.add_field("chat_id", str(ADMIN_ID))
    data.add_field("caption", caption)
    data.add_field("parse_mode", "HTML")
    data.add_field("reply_markup", json.dumps(reply_markup))
    data.add_field("photo", photo_bytes, filename="report.jpg", content_type="image/jpeg")

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as resp:
            if resp.status != 200:
                print("Ошибка отправки в Telegram:", await resp.text())


# --- API ENDPOINTS ---

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Eco Khujand API is running"}


@app.get("/api/user/{user_id}")
def get_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT points, username, avatar_url FROM users WHERE user_id = ?", (user_id,))
    user_row = cursor.fetchone()

    cursor.execute("SELECT COUNT(*) FROM reports WHERE user_id = ? AND status = 'approved'", (user_id,))
    reports_count = cursor.fetchone()[0]

    cursor.execute("SELECT medal_key FROM medals WHERE user_id = ? AND status = 'approved'", (user_id,))
    medals = [row[0] for row in cursor.fetchall()]

    conn.close()

    if not user_row:
        return {
            "user_id": user_id,
            "points": 0,
            "username": "Пользователь",
            "avatar_url": "",
            "reports_count": 0,
            "medals": [],
        }

    return {
        "user_id": user_id,
        "points": user_row[0],
        "username": user_row[1] or "Пользователь",
        "avatar_url": user_row[2] or "",
        "reports_count": reports_count,
        "medals": medals,
    }


@app.post("/api/report")
async def create_report(
    user_id: int = Form(...),
    action_type: str = Form(...),
    comment: Optional[str] = Form(""),
    points: int = Form(0),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    photo: UploadFile = File(...),
):
    try:
        photo_bytes = await photo.read()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO reports (user_id, action_type, comment, latitude, longitude, photo_path, points, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (user_id, action_type, comment, latitude, longitude, "telegram_media", points))

        report_id = cursor.lastrowid
        conn.commit()
        conn.close()

        caption = (
            f"<b>🌱 Новый эко-отчёт #{report_id}</b>\n\n"
            f"👤 <b>User ID:</b> <code>{user_id}</code>\n"
            f"🏷 <b>Действие:</b> {action_type}\n"
            f"⭐ <b>Баллы:</b> +{points}\n"
            f"💬 <b>Комментарий:</b> {comment if comment else 'Отсутствует'}\n"
        )
        if latitude and longitude:
            caption += f"📍 <b>Координаты:</b> {latitude:.5f}, {longitude:.5f}\n"

        await send_telegram_photo_with_buttons(photo_bytes, caption, report_id)

        return {
            "status": "success",
            "message": "Отчёт успешно отправлен!",
            "report_id": report_id,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки отчёта: {str(e)}")
