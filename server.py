import os
import asyncio
import sqlite3
import requests
from typing import Optional, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

BOT_TOKEN = "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0"  # Токен бота
ADMIN_ID = 5581941983                                 # Telegram ID админа

DB_NAME = "eco_khujand.db"
UPLOAD_DIR = "uploads"
STATIC_DIR = "static"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# --- Расчёт рангов ---
def calculate_rank(points: int):
    if points < 50:
        return {
            "title": "Эко-Новичок",
            "rank_code": "РАНГ I",
            "current_points": points,
            "max_points": 50,
            "progress_pct": min(100, int((points / 50) * 100)),
            "icon": "/static/rank_1.png"
        }
    elif points < 200:
        return {
            "title": "Эко-Защитник",
            "rank_code": "РАНГ II",
            "current_points": points - 50,
            "max_points": 150,
            "progress_pct": min(100, int(((points - 50) / 150) * 100)),
            "icon": "/static/rank_2.png"
        }
    else:
        return {
            "title": "Эко-Активист",
            "rank_code": "РАНГ III",
            "current_points": points,
            "max_points": 500,
            "progress_pct": 100 if points >= 500 else int((points / 500) * 100),
            "icon": "/static/rank_3.png"
        }

# --- Инициализация и миграция БД ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            avatar_url TEXT DEFAULT '',
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

init_db()

# --- Фоновый опрос кнопок Telegram ---
async def process_telegram_updates():
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
            print(f"Ошибка polling: {e}")
        await asyncio.sleep(1)

async def handle_callback_query(callback):
    callback_id = callback["id"]
    data = callback.get("data", "")
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    if data.startswith("approve_medal_") or data.startswith("reject_medal_"):
        parts = data.split("_")
        action = parts[0]
        medal_db_id = int(parts[2])

        cursor.execute("SELECT user_id, medal_key, status FROM medals WHERE id = ?", (medal_db_id,))
        m = cursor.fetchone()
        if m and m[2] == "pending":
            u_id, m_key, _ = m
            if action == "approve":
                cursor.execute("UPDATE medals SET status = 'approved' WHERE id = ?", (medal_db_id,))
                msg_user = f"🏅 Поздравляем! Ваша медаль «{m_key}» была одобрена!"
                status_lbl = "✅ <b>МЕДАЛЬ ОДОБРЕНА</b>"
            else:
                cursor.execute("UPDATE medals SET status = 'rejected' WHERE id = ?", (medal_db_id,))
                msg_user = f"❌ Заявка на медаль «{m_key}» была отклонена."
                status_lbl = "❌ <b>МЕДАЛЬ ОТКЛОНЕНА</b>"
            conn.commit()

            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": callback_id})
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                "chat_id": chat_id,
                "text": f"Решение по медали #{medal_db_id}: {status_lbl}",
                "parse_mode": "HTML"
            })
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                "chat_id": u_id,
                "text": msg_user
            })
        conn.close()
        return

    if data.startswith("approve_") or data.startswith("reject_"):
        action, report_id = data.split("_", 1)
        report_id = int(report_id)

        cursor.execute("SELECT user_id, action_type, points, status FROM reports WHERE id = ?", (report_id,))
        report = cursor.fetchone()

        if report and report[3] == "pending":
            user_id, action_type, points, status = report
            if action == "approve":
                cursor.execute("UPDATE reports SET status = 'approved' WHERE id = ?", (report_id,))
                cursor.execute("""
                    INSERT INTO users (user_id, points) VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET points = points + ?
                """, (user_id, points, points))
                conn.commit()
                status_text = f"✅ <b>ОДОБРЕНО</b> (+{points} баллов)"
                user_msg = f"🎉 Ваш отчёт «{action_type}» одобрен! Вам начислено +{points} баллов."
            else:
                cursor.execute("UPDATE reports SET status = 'rejected' WHERE id = ?", (report_id,))
                conn.commit()
                status_text = "❌ <b>ОТКЛОНЕНО</b>"
                user_msg = f"❌ Ваш отчёт «{action_type}» был отклонён."

            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": callback_id})
            old_caption = callback["message"].get("caption", "")
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageCaption", json={
                "chat_id": chat_id,
                "message_id": message_id,
                "caption": f"{old_caption}\n\n<b>Статус:</b> {status_text}",
                "parse_mode": "HTML"
            })
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                "chat_id": user_id,
                "text": user_msg
            })

    conn.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
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
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- Endpoints ---

@app.get("/api/user/{user_id}")
def get_user_profile(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT points, username, avatar_url FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT INTO users (user_id, points) VALUES (?, 0)", (user_id,))
        conn.commit()
        points, username, avatar_url = 0, "", ""
    else:
        points, username, avatar_url = row

    cursor.execute("SELECT COUNT(*) FROM reports WHERE user_id = ? AND status = 'approved'", (user_id,))
    approved_reports = cursor.fetchone()[0]

    cursor.execute("SELECT medal_key, status FROM medals WHERE user_id = ?", (user_id,))
    user_medals = {m[0]: m[1] for m in cursor.fetchall()}

    conn.close()

    rank_info = calculate_rank(points)

    return {
        "user_id": user_id,
        "username": username or "Пользователь",
        "avatar_url": avatar_url or "/static/default_avatar.png",
        "points": points,
        "reports_count": approved_reports,
        "rank": rank_info,
        "medals": {
            "plastic": user_medals.get("plastic", "locked"),
            "tree": user_medals.get("tree", "locked")
        }
    }

# --- ОСНОВНОЙ ЭНДПОИНТ ОТПРАВКИ ЭКО-ОТЧЁТОВ ---
@app.post("/api/report")
async def create_general_report(
    user_id: int = Form(...),
    action_type: str = Form("Эко-активность"),
    points: int = Form(0),
    comment: Optional[str] = Form(""),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    photo: Optional[UploadFile] = File(None)
):
    try:
        photo_path = ""
        if photo:
            photo_filename = f"report_{user_id}_{photo.filename}"
            photo_path = os.path.join(UPLOAD_DIR, photo_filename)
            with open(photo_path, "wb") as f:
                f.write(await photo.read())

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO reports (user_id, action_type, points, comment, latitude, longitude, photo_path, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (user_id, action_type, points, comment, latitude, longitude, photo_path))
        
        report_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Отправка уведомления администратору в Telegram
        if BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
            caption = (
                f"🌱 <b>Новый эко-отчёт #{report_id}</b>\n"
                f"<b>ID пользователя:</b> {user_id}\n"
                f"<b>Тип:</b> {action_type}\n"
                f"<b>Баллы:</b> +{points}\n"
                f"<b>Комментарий:</b> {comment or 'Нет'}"
            )
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Одобрить", "callback_data": f"approve_{report_id}"},
                        {"text": "❌ Отклонить", "callback_data": f"reject_{report_id}"}
                    ]
                ]
            }

            if photo_path and os.path.exists(photo_path):
                url_photo = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                with open(photo_path, "rb") as f:
                    requests.post(url_photo, data={
                        "chat_id": ADMIN_ID,
                        "caption": caption,
                        "parse_mode": "HTML",
                        "reply_markup": str(keyboard).replace("'", '"')
                    }, files={"photo": f})
            else:
                url_msg = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                requests.post(url_msg, json={
                    "chat_id": ADMIN_ID,
                    "text": caption,
                    "parse_mode": "HTML",
                    "reply_markup": keyboard
                })

        return {"status": "success", "message": "Отчёт успешно отправлен на модерацию!"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/report/medal")
async def receive_medal_report(
    user_id: int = Form(...),
    medal_key: str = Form(...),
    photo_before: UploadFile = File(...),
    photo_after: UploadFile = File(...)
):
    try:
        path_before = os.path.join(UPLOAD_DIR, f"medal_{user_id}_{medal_key}_before_{photo_before.filename}")
        path_after = os.path.join(UPLOAD_DIR, f"medal_{user_id}_{medal_key}_after_{photo_after.filename}")

        with open(path_before, "wb") as f:
            f.write(await photo_before.read())
        with open(path_after, "wb") as f:
            f.write(await photo_after.read())

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO medals (user_id, medal_key, photo_before, photo_after, status)
            VALUES (?, ?, ?, ?, 'pending')
            ON CONFLICT(user_id, medal_key) DO UPDATE SET
                photo_before = excluded.photo_before,
                photo_after = excluded.photo_after,
                status = 'pending'
        """, (user_id, medal_key, path_before, path_after))

        medal_db_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Отправляем админу сообщение с кнопками модерации медали
        if BOT_TOKEN != "YOUR_BOT_TOKEN_HERE":
            medal_names = {"plastic": "Сбор пластика", "tree": "Посадка дерева"}
            title = medal_names.get(medal_key, medal_key)
            
            # 1. Отправка 2 фото альбомом
            url_media = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
            files = {
                "p1": open(path_before, "rb"),
                "p2": open(path_after, "rb")
            }
            media_data = [
                {"type": "photo", "media": "attach://p1", "caption": f"🏅 <b>Заявка на медаль: {title}</b>\nUser ID: {user_id}\n\nСлева: ДО | Справа: ПОСЛЕ", "parse_mode": "HTML"},
                {"type": "photo", "media": "attach://p2"}
            ]
            requests.post(url_media, data={"chat_id": ADMIN_ID, "media": str(media_data).replace("'", '"')}, files=files)

            # 2. Отправка кнопок модерации
            url_btn = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Подтвердить медаль", "callback_data": f"approve_medal_{medal_db_id}"},
                        {"text": "❌ Отклонить", "callback_data": f"reject_medal_{medal_db_id}"}
                    ]
                ]
            }
            requests.post(url_btn, json={
                "chat_id": ADMIN_ID,
                "text": f"Принять решение по медали «{title}» для пользователя {user_id}:",
                "reply_markup": keyboard
            })

        return {"status": "success", "message": "Заявка на медаль отправлена!"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))