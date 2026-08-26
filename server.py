import os
import sqlite3
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Токен бота и Telegram ID
BOT_TOKEN = "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0"
ADMIN_ID =  5581941983

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_NAME = "eco_khujand.db"

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
            points INTEGER,
            comment TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.get("/api/user/{user_id}")
async def get_user(user_id: int):
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
async def create_report(
    user_id: int = Form(...),
    action_type: str = Form(...),
    points: int = Form(...),
    comment: str = Form(None),
    latitude: float = Form(None),
    longitude: float = Form(None),
    photo: UploadFile = File(...)
):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO reports (user_id, action_type, points, comment, status) VALUES (?, ?, ?, ?, 'pending')",
        (user_id, action_type, points, comment)
    )
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Формируем клавиатуру модерации для админа
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"approve_{report_id}")
    builder.button(text="❌ Отклонить", callback_data=f"reject_{report_id}")
    builder.adjust(2)

    caption = (
        f"📩 <b>Новый эко-отчёт #{report_id}</b>\n\n"
        f"<b>ID пользователя:</b> <code>{user_id}</code>\n"
        f"<b>Действие:</b> {action_type} (+{points} баллов)\n"
        f"<b>Комментарий:</b> {comment if comment else 'Отсутствует'}\n"
        f"<b>Координаты:</b> {latitude or 'N/A'}, {longitude or 'N/A'}"
    )

    photo_bytes = await photo.read()
    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=types.BufferedInputFile(photo_bytes, filename=photo.filename),
        caption=caption,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

    return {"status": "success", "report_id": report_id}

# Обработка решений админа
@dp.callback_query(lambda c: c.data.startswith(("approve_", "reject_")))
async def handle_moderation(callback_query: types.CallbackQuery):
    action, report_id_str = callback_query.data.split("_")
    report_id = int(report_id_str)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, action_type, points, status FROM reports WHERE id = ?", (report_id,))
    report = cursor.fetchone()

    if not report or report[3] != "pending":
        await callback_query.answer("Отчёт уже обработан!", show_alert=True)
        conn.close()
        return

    user_id, action_type, points, _ = report

    if action == "approve":
        cursor.execute("UPDATE reports SET status = 'approved' WHERE id = ?", (report_id,))
        cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (points, user_id))
        conn.commit()
        
        await callback_query.message.edit_caption(
            caption=callback_query.message.caption + "\n\n<b>Статус:</b> ✅ Одобрено",
            parse_mode="HTML"
        )
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"🎉 Ваш отчёт «{action_type}» одобрен! Вам начислено +{points} эко-баллов."
            )
        except Exception:
            pass

    elif action == "reject":
        cursor.execute("UPDATE reports SET status = 'rejected' WHERE id = ?", (report_id,))
        conn.commit()
        
        await callback_query.message.edit_caption(
            caption=callback_query.message.caption + "\n\n<b>Статус:</b> ❌ Отклонено",
            parse_mode="HTML"
        )
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"❌ Ваш отчёт «{action_type}» был отклонён при модерации."
            )
        except Exception:
            pass

    conn.close()
    await callback_query.answer()
