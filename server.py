import os
import asyncio
import sqlite3
import requests
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# --- Настройки Telegram-бота и администратора ---
BOT_TOKEN = "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0"  # Укажи токен бота от BotFather
ADMIN_ID = 5581941983                # Укажи свой Telegram ID

DB_NAME = "eco_khujand.db"
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- 1. Инициализация и миграция базы данных ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            points INTEGER DEFAULT 0
        )
    """)
    
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
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Миграция колонок
    cursor.execute("PRAGMA table_info(reports)")
    existing_columns = [column[1] for column in cursor.fetchall()]
    
    required_columns = {
        "points": "INTEGER DEFAULT 0",
        "comment": "TEXT",
        "latitude": "REAL",
        "longitude": "REAL",
        "photo_path": "TEXT",
        "status": "TEXT DEFAULT 'pending'"
    }
    
    for col_name, col_type in required_columns.items():
        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE reports ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()

init_db()

# --- 2. Управление фоновым обработчиком кнопок (Long Polling) ---
async def process_telegram_updates():
    """Фоновый процесс для приема нажатий inline-кнопок админом"""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        return

    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=10"
            res = await asyncio.to_thread(requests.get, url, timeout=15)
            data = res.json()

            if data.get("ok"):
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    if "callback_query" in update:
                        await handle_callback_query(update["callback_query"])
        except Exception as e:
            print(f"Ошибка polling Telegram: {e}")
        await asyncio.sleep(1)

async def handle_callback_query(callback):
    callback_id = callback["id"]
    data = callback.get("data", "")
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]

    if not data.startswith("approve_") and not data.startswith("reject_"):
        return

    action, report_id = data.split("_", 1)
    report_id = int(report_id)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, action_type, points, status FROM reports WHERE id = ?", (report_id,))
    report = cursor.fetchone()

    if not report:
        conn.close()
        return

    user_id, action_type, points, status = report

    if status != "pending":
        # Если отчет уже был обработан
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery", json={
            "callback_query_id": callback_id,
            "text": "Этот отчёт уже был обработан!"
        })
        conn.close()
        return

    if action == "approve":
        # Обновляем статус отчёта и начисляем баллы
        cursor.execute("UPDATE reports SET status = 'approved' WHERE id = ?", (report_id,))
        cursor.execute("""
            INSERT INTO users (user_id, points) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET points = points + ?
        """, (user_id, points, points))
        conn.commit()

        status_text = f"✅ <b>ОДОБРЕНО</b> (+{points} баллов)"
        user_msg = f"🎉 Ваш отчёт «{action_type}» одобрен! Вам начислено +{points} баллов."

    else:
        # Отклоняем отчёт
        cursor.execute("UPDATE reports SET status = 'rejected' WHERE id = ?", (report_id,))
        conn.commit()

        status_text = "❌ <b>ОТКЛОНЕНО</b>"
        user_msg = f"❌ Ваш отчёт «{action_type}» был отклонён модератором."

    conn.close()

    # 1. Ответ на нажатие кнопки
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": callback_id})

    # 2. Обновляем текст сообщения у админа (убираем кнопки)
    old_caption = callback["message"].get("caption", "")
    new_caption = f"{old_caption}\n\n<b>Статус:</b> {status_text}"
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageCaption", json={
        "chat_id": chat_id,
        "message_id": message_id,
        "caption": new_caption,
        "parse_mode": "HTML"
    })

    # 3. Отправляем уведомление пользователю
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
        "chat_id": user_id,
        "text": user_msg
    })

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Запуск фонового процесса при старте FastAPI
    polling_task = asyncio.create_task(process_telegram_updates())
    yield
    polling_task.cancel()

app = FastAPI(title="Eco Khujand API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# --- 3. Вспомогательная функция отправки фото админу с кнопками ---
def send_admin_approval_request(report_id: int, photo_path: str, caption_text: str):
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Принять", "callback_data": f"approve_{report_id}"},
                {"text": "❌ Отклонить", "callback_data": f"reject_{report_id}"}
            ]
        ]
    }
    
    try:
        with open(photo_path, "rb") as photo_file:
            payload = {
                "chat_id": ADMIN_ID,
                "caption": caption_text,
                "parse_mode": "HTML",
                "reply_markup": str(keyboard).replace("'", '"')
            }
            files = {"photo": photo_file}
            requests.post(url, data=payload, files=files, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки сообщения админу: {e}")

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
        photo_filename = f"{user_id}_{photo.filename}"
        photo_path = os.path.join(UPLOAD_DIR, photo_filename)
        
        with open(photo_path, "wb") as buffer:
            content = await photo.read()
            buffer.write(content)

        # Записываем отчёт со статусом 'pending' (баллы пока НЕ начисляем)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO reports (user_id, action_type, points, comment, latitude, longitude, photo_path, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (user_id, action_type, points, comment, latitude, longitude, photo_path))

        report_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Отправляем карточку отчёта с кнопками администратору
        loc_str = f"{latitude}, {longitude}" if latitude and longitude else "Не указаны"
        caption = (
            f"📥 <b>Новый отчёт на модерацию! (№{report_id})</b>\n\n"
            f"👤 <b>ID пользователя:</b> <code>{user_id}</code>\n"
            f"🎯 <b>Действие:</b> {action_type} (+{points} баллов)\n"
            f"💬 <b>Комментарий:</b> {comment or 'Отсутствует'}\n"
            f"📍 <b>Координаты:</b> {loc_str}"
        )
        send_admin_approval_request(report_id, photo_path, caption)

        return {"status": "success", "message": "Отчёт отправлен на модерацию!", "report_id": report_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")
