import asyncio
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

BOT_TOKEN = os.getenv("BOT_TOKEN", "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0")
ADMIN_ID = int(os.getenv("ADMIN_ID", "1631981047"))  # ID администратора для модерации
DB_NAME = "eco_khujand_v2.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализация FastAPI для приема запросов из мини-приложения
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Функция для создания базы данных и таблиц
def init_db():
    conn = sqlite3.connect(DB_NAME, timeout=20.0)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
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
            photo_path TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()


# --- ОБРАБОТКА /start ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    welcome_text = (
        f"👋 <b>Привет, {message.from_user.first_name}! Добро пожаловать в Eco Khujand!</b> 🌿\n\n"
        "Мы создаём чистое будущее Худжанда вместе! Вот что ты можешь делать с помощью этого бота:\n\n"
        "🗺️ <b>Карта эко-точек:</b> находи близлежащие контейнеры и урны.\n"
        "📸 <b>Эко-отчёты:</b> убирай территорию или сдавай пластик/стекло, отправляй фото и получай баллы!\n"
        "🏆 <b>Ранги и достижения:</b> зарабатывай очки и расти от <i>Новичка</i> до <i>Эко-Героя</i>!\n\n"
        "Открывай мини-приложение через меню, чтобы начать! 👇"
    )
    await message.answer(welcome_text, parse_mode="HTML")

@dp.message(F.text == "Сообщить о проблеме ⚠️")
async def handle_report(message: types.Message):
    await message.answer("Пришлите фото переполненного бака или геолокацию, чтобы мы передали информацию в службы очистки!")

# --- API ДЛЯ ВЕБ-ПРИЛОЖЕНИЯ (Фронтенда) ---

@app.post("/api/report")
async def api_receive_report(
    user_id: int = Form(...),
    username: str = Form("Эко Активист"),
    action_type: str = Form(...),
    points: int = Form(...),
    comment: str = Form(""),
    photo: UploadFile = File(...)
):
    os.makedirs("uploads", exist_ok=True)
    file_path = os.path.join("uploads", photo.filename)
    
    with open(file_path, "wb") as buffer:
        buffer.write(await photo.read())

    conn = sqlite3.connect(DB_NAME, timeout=20.0)
    cursor = conn.cursor()
    try:
        # Сохраняем или обновляем имя пользователя в таблице users
        cursor.execute("""
            INSERT INTO users (user_id, username, points) VALUES (?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET username = ?
        """, (user_id, username, username))

        cursor.execute(
            "INSERT INTO reports (user_id, action_type, points, comment, photo_path, status) VALUES (?, ?, ?, ?, ?, 'pending')",
            (user_id, action_type, points, comment, file_path)
        )
        report_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    # Отправка уведомления администратору для модерации
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_report:{report_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_report:{report_id}")
            ]
        ])
        
        caption_text = (
            f"📥 <b>Новый эко-отчёт #{report_id}</b>\n\n"
            f"👤 <b>Пользователь:</b> {username} (ID: <code>{user_id}</code>)\n"
            f"📌 <b>Действие:</b> {action_type}\n"
            f"🏅 <b>Баллы:</b> +{points}\n"
            f"💬 <b>Комментарий:</b> {comment or 'Отсутствует'}"
        )
        
        photo_file = FSInputFile(file_path)
        await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_file,
            caption=caption_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Ошибка при отправке отчёта администратору: {e}")

    return {"status": "success", "report_id": report_id}

@app.get("/api/user/{user_id}")
async def api_get_user(user_id: int):
    conn = sqlite3.connect(DB_NAME, timeout=20.0)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
        user_row = cursor.fetchone()
        points = user_row[0] if user_row else 0

        cursor.execute("SELECT COUNT(*) FROM reports WHERE user_id = ? AND status = 'approved'", (user_id,))
        reports_row = cursor.fetchone()
        reports_count = reports_row[0] if reports_row else 0
    finally:
        conn.close()

    return {"points": points, "reports_count": reports_count}

# --- ЭНДПОИНТ ДЛЯ ЛИДЕРБОРДА ---
@app.get("/api/leaderboard")
async def api_get_leaderboard():
    conn = sqlite3.connect(DB_NAME, timeout=20.0)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT user_id, username, points FROM users ORDER BY points DESC LIMIT 10")
        rows = cursor.fetchall()
    finally:
        conn.close()
    
    leaderboard = []
    for rank, (user_id, username, points) in enumerate(rows, start=1):
        leaderboard.append({
            "rank": rank,
            "username": username or f"Активист #{user_id}",
            "points": points
        })
    return leaderboard


# --- МОДЕРАЦИЯ ОТЧЕТОВ АДМИНОМ ---
@dp.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_") | F.data.startswith("approve_report:") | F.data.startswith("reject_report:"))
async def handle_report_moderation(callback: types.CallbackQuery):
    data = callback.data
    
    if ":" in data:
        action, report_id = data.split(":")
    else:
        parts = data.split("_")
        action = parts[0]
        report_id = parts[1]
        
    report_id = int(report_id)

    conn = sqlite3.connect(DB_NAME, timeout=20.0)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT user_id, points, status FROM reports WHERE id = ?", (report_id,))
        report = cursor.fetchone()

        if not report:
            await callback.answer("❌ Отчёт не найден в базе данных!", show_alert=True)
            return

        user_id, points, status = report

        if status != "pending":
            await callback.answer(f"⚠️ Этот отчёт уже обработан (статус: {status})", show_alert=True)
            return

        if action in ["approve", "approve_report"]:
            cursor.execute("UPDATE reports SET status = 'approved' WHERE id = ?", (report_id,))
            cursor.execute("""
                INSERT INTO users (user_id, points) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET points = points + ?
            """, (user_id, points, points))
            conn.commit()

            new_caption = (callback.message.caption or "") + f"\n\n<b>✅ ОДОБРЕНО! Зачислено +{points} баллов.</b>"
            await callback.message.edit_caption(caption=new_caption, parse_mode="HTML", reply_markup=None)
            await callback.answer("✅ Отчёт одобрен, баллы успешно зачислены!")

            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=f"🎉 <b>Ваш эко-отчёт #{report_id} одобрен!</b>\nВам зачислено <b>+{points} баллов</b>. Посмотреть свой статус можно в Профиле! 🏆",
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

        elif action in ["reject", "reject_report"]:
            cursor.execute("UPDATE reports SET status = 'rejected' WHERE id = ?", (report_id,))
            conn.commit()

            new_caption = (callback.message.caption or "") + "\n\n<b>❌ ОТКЛОНЕНО.</b>"
            await callback.message.edit_caption(caption=new_caption, parse_mode="HTML", reply_markup=None)
            await callback.answer("❌ Отчёт отклонён.")

            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=f"❌ <b>Ваш эко-отчёт #{report_id} был отклонён модератором.</b>\nПопробуйте отправить более чёткое фото.",
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
    finally:
        conn.close()


async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    
    port = int(os.getenv("PORT", 8080))
    
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    
    await asyncio.gather(
        dp.start_polling(bot),
        server.serve()
    )

if __name__ == "__main__":
    asyncio.run(main())
