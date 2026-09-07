import asyncio
import json
import os
import sqlite3
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

DB_NAME = "eco_khujand.db"
BOT_TOKEN = os.getenv(
    "BOT_TOKEN", "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0"
)
ADMIN_ID = os.getenv("ADMIN_ID", "5581941983")

WEBAPP_MAP_URL = "https://khujand-eco-bot.onrender.com/index.html?v=1.2"
WEBAPP_PROFILE_URL = "https://khujand-eco-bot.onrender.com/profile.html?v=1.3"

# --- Инициализация Bot и Dispatcher ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def get_main_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Открыть карту 🗺️",
                    web_app=WebAppInfo(url=WEBAPP_MAP_URL),
                )
            ],
            [KeyboardButton(text="Сообщить о проблеме ⚠️")],
            [
                KeyboardButton(
                    text="Профиль 👤",
                    web_app=WebAppInfo(url=WEBAPP_PROFILE_URL),
                )
            ],
        ],
        resize_keyboard=True,
    )


# --- ХЕНДЛЕРЫ ТЕЛЕГРАМ БОТА ---


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    welcome_text = (
        f"👋 <b>Привет, {message.from_user.first_name}! Добро пожаловать в Eco"
        " Khujand!</b> 🌿\n\nМы создаём чистое будущее Худжанда вместе! Вот"
        " что ты можешь делать с помощью этого бота:\n\n🗺️ <b>Карта"
        " эко-точек:</b> находи близлежащие контейнеры и урны.\n📸 <b>Эко-отчёты:</b>"
        " убирай территорию или сдавай пластик/стекло, отправляй фото и получай"
        " баллы!\n🏆 <b>Ранги и достижения:</b> зарабатывай очки и расти от"
        " <i>Новичка</i> до <i>Эко-Героя</i>!\n⚠️ <b>Проблемы:</b> сообщай о"
        " переполненных баках прямо из бота.\n\nИспользуй меню ниже, чтобы"
        " начать! 👇"
    )
    await message.answer(
        welcome_text, parse_mode="HTML", reply_markup=get_main_reply_keyboard()
    )


@dp.message(F.text == "Сообщить о проблеме ⚠️")
async def handle_report_problem(message: types.Message):
    await message.answer(
        "Пришлите фото переполненного бака или геолокацию, чтобы мы передали"
        " информацию в службы очистки!"
    )


@dp.callback_query(
    F.data.startswith("approve_")
    | F.data.startswith("reject_")
    | F.data.startswith("approve_report:")
    | F.data.startswith("reject_report:")
)
async def handle_report_moderation(callback: types.CallbackQuery):
    data = callback.data

    if ":" in data:
        action, report_id = data.split(":")
    else:
        parts = data.split("_")
        action = parts[0]
        report_id = parts[1]

    report_id = int(report_id)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT user_id, points, status FROM reports WHERE id = ?", (report_id,)
    )
    report = cursor.fetchone()

    if not report:
        await callback.answer("❌ Отчёт не найден в базе данных!", show_alert=True)
        conn.close()
        return

    user_id, points, status = report

    if status != "pending":
        await callback.answer(
            f"⚠️ Этот отчёт уже обработан (статус: {status})", show_alert=True
        )
        conn.close()
        return

    if action in ["approve", "approve_report"]:
        cursor.execute(
            "UPDATE reports SET status = 'approved' WHERE id = ?", (report_id,)
        )
        cursor.execute(
            """
                INSERT INTO users (user_id, points) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET points = points + ?
            """,
            (user_id, points, points),
        )
        conn.commit()
        conn.close()

        new_caption = (
            callback.message.caption
            + f"\n\n<b>✅ ОДОБРЕНО! Зачислено +{points} баллов.</b>"
        )
        await callback.message.edit_caption(
            caption=new_caption, parse_mode="HTML", reply_markup=None
        )
        await callback.answer("✅ Отчёт одобрен, баллы зачислены!")

        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎉 <b>Ваш эко-отчёт #{report_id} одобрен!</b>\nВам"
                    f" зачислено <b>+{points} баллов</b>. Посмотреть свой"
                    " статус можно в Профиле! 🏆"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            print(f"Ошибка отправки пользователю: {e}")

    elif action in ["reject", "reject_report"]:
        cursor.execute(
            "UPDATE reports SET status = 'rejected' WHERE id = ?", (report_id,)
        )
        conn.commit()
        conn.close()

        new_caption = callback.message.caption + "\n\n<b>❌ ОТКЛОНЕНО.</b>"
        await callback.message.edit_caption(
            caption=new_caption, parse_mode="HTML", reply_markup=None
        )
        await callback.answer("❌ Отчёт отклонён.")

        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"❌ <b>Ваш эко-отчёт #{report_id} был отклонён"
                    " модератором.</b>\nПопробуйте отправить более чёткое фото."
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            print(f"Ошибка отправки пользователю: {e}")


# --- ИНИЦИАЛИЗА БД И FASTAPI ---


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
            comment TEXT,
            latitude REAL,
            longitude REAL,
            photo_path TEXT,
            points INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

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

app = FastAPI(title="Eco Khujand API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))


# --- API ENDPOINTS ---


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Eco Khujand API & Bot running"}


@app.get("/api/user/{user_id}")
def get_user(user_id: int):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # 1. Получаем данные из таблицы users
        cursor.execute(
            "SELECT points, username, avatar_url FROM users WHERE user_id = ?",
            (user_id,),
        )
        user_row = cursor.fetchone()

        # 2. Подсчитываем количество одобренных отчётов
        cursor.execute(
            "SELECT COUNT(*) FROM reports WHERE user_id = ? AND status = 'approved'",
            (user_id,),
        )
        reports_count_row = cursor.fetchone()
        reports_count = reports_count_row[0] if reports_count_row else 0

        # 3. Суммируем баллы за одобренные отчёты
        cursor.execute(
            "SELECT SUM(points) FROM reports WHERE user_id = ? AND status = 'approved'",
            (user_id,),
        )
        sum_row = cursor.fetchone()
        approved_points_sum = sum_row[0] if (sum_row and sum_row[0] is not None) else 0

        # 4. Получаем одобренные медали
        cursor.execute(
            "SELECT medal_key FROM medals WHERE user_id = ? AND status = 'approved'",
            (user_id,),
        )
        medals = [row[0] for row in cursor.fetchall()]

        conn.close()

        user_db_points = user_row[0] if (user_row and user_row[0] is not None) else 0
        username = user_row[1] if (user_row and user_row[1]) else "Пользователь"
        avatar_url = user_row[2] if (user_row and user_row[2]) else ""

        # Берем максимальные баллы
        final_points = max(user_db_points, approved_points_sum)

        return {
            "user_id": user_id,
            "points": final_points,
            "username": username,
            "avatar_url": avatar_url,
            "reports_count": reports_count,
            "medals": medals,
        }
    except Exception as e:
        print(f"Ошибка в get_user для user_id {user_id}: {e}")
        return {
            "user_id": user_id,
            "points": 0,
            "username": "Пользователь",
            "avatar_url": "",
            "reports_count": 0,
            "medals": [],
            "error": str(e),
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

        cursor.execute(
            """
                INSERT INTO reports (user_id, action_type, comment, latitude, longitude, photo_path, points, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                user_id,
                action_type,
                comment,
                latitude,
                longitude,
                "telegram_media",
                points,
            ),
        )

        report_id = cursor.lastrowid
        conn.commit()
        conn.close()

        caption = (
            f"<b>🌱 Новый эко-отчёт #{report_id}</b>\n\n👤 <b>User ID:</b>"
            f" <code>{user_id}</code>\n🏷 <b>Действие:</b> {action_type}\n⭐"
            f" <b>Баллы:</b> +{points}\n💬 <b>Комментарий:</b>"
            f" {comment if comment else 'Отсутствует'}\n"
        )
        if latitude and longitude:
            caption += f"📍 <b>Координаты:</b> {latitude:.5f}, {longitude:.5f}\n"

        reply_markup = {
            "inline_keyboard": [[
                {"text": "✅ Одобрить", "callback_data": f"approve_{report_id}"},
                {"text": "❌ Отклонить", "callback_data": f"reject_{report_id}"},
            ]]
        }

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        data = aiohttp.FormData()
        data.add_field("chat_id", str(ADMIN_ID))
        data.add_field("caption", caption)
        data.add_field("parse_mode", "HTML")
        data.add_field("reply_markup", json.dumps(reply_markup))
        data.add_field(
            "photo", photo_bytes, filename="report.jpg", content_type="image/jpeg"
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as resp:
                if resp.status != 200:
                    print("Ошибка отправки в Telegram:", await resp.text())

        return {
            "status": "success",
            "message": "Отчёт успешно отправлен!",
            "report_id": report_id,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Ошибка обработки отчёта: {str(e)}"
        )