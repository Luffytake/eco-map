import asyncio
import json
import os
import sqlite3
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardRemove
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

DB_NAME = "eco_khujand.db"
BOT_TOKEN = os.getenv(
    "BOT_TOKEN", "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0"
)
ADMIN_ID = os.getenv("ADMIN_ID", "5581941983")

# --- Инициализация Bot и Dispatcher ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# --- ХЕНДЛЕРЫ ТЕЛЕГРАМ БОТА ---


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
  welcome_text = (
      f"👋 <b>Привет, {message.from_user.first_name}! Добро пожаловать в Eco"
      " Khujand!</b> 🌿\n\nМы создаём чистое будущее Худжанда вместе! Нажми на"
      " кнопку <b>Eco App</b> внизу слева, чтобы открыть карту и профиль."
  )
  # Удаляем старые Reply-кнопки снизу
  await message.answer(
      welcome_text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove()
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

    cursor.execute(
        "SELECT points, username, avatar_url FROM users WHERE user_id = ?",
        (user_id,),
    )
    user_row = cursor.fetchone()

    cursor.execute(
        "SELECT COUNT(*) FROM reports WHERE user_id = ? AND status = 'approved'",
        (user_id,),
    )
    reports_count_row = cursor.fetchone()
    reports_count = reports_count_row[0] if reports_count_row else 0

    cursor.execute(
        "SELECT SUM(points) FROM reports WHERE user_id = ? AND status ="
        " 'approved'",
        (user_id,),
    )
    sum_row = cursor.fetchone()
    approved_points_sum = sum_row[0] if (sum_row and sum_row[0] is not None) else 0

    conn.close()

    user_db_points = user_row[0] if (user_row and user_row[0] is not None) else 0
    username = user_row[1] if (user_row and user_row[1]) else "Пользователь"
    avatar_url = user_row[2] if (user_row and user_row[2]) else ""

    final_points = max(user_db_points, approved_points_sum)

    return {
        "user_id": user_id,
        "points": final_points,
        "username": username,
        "avatar_url": avatar_url,
        "reports_count": reports_count,
    }
  except Exception as e:
    return {
        "user_id": user_id,
        "points": 0,
        "username": "Пользователь",
        "avatar_url": "",
        "reports_count": 0,
        "error": str(e),
    }


@app.post("/api/report")
async def create_report(
    user_id: int = Form(...),
    action_type: str = Form(...),
    comment: Optional[str] = Form(""),
    points: int = Form(20),
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


# --- ЗАПУСК ---
if __name__ == "__main__":
  import uvicorn

  port = int(os.environ.get("PORT", 10000))
  uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)