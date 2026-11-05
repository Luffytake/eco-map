import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, closing
from typing import Optional
from urllib.parse import parse_qsl

import uvicorn
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------- настройки
BOT_TOKEN = os.environ["BOT_TOKEN"].strip()          # только из переменных Railway
ADMIN_ID = int(os.environ["ADMIN_ID"])
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()     # адрес index.html (необязательно)

# Для Railway: подключите Volume и укажите пути на него, например /data/...
DB_NAME = os.getenv("DB_PATH", "eco_khujand_v2.db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]
# Когда index.html начнёт слать init_data, поставьте REQUIRE_INIT_DATA=1
REQUIRE_INIT_DATA = os.getenv("REQUIRE_INIT_DATA", "0") == "1"

MAX_POINTS = 100
MAX_PHOTO_SIZE = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("eco_bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ---------------------------------------------------------------- база данных
def db() -> sqlite3.Connection:
    return sqlite3.connect(DB_NAME, timeout=20.0)


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_NAME) or ".", exist_ok=True)
    with closing(db()) as conn, conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                points INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action_type TEXT,
                points INTEGER,
                comment TEXT,
                photo_path TEXT,
                latitude REAL,
                longitude REAL,
                status TEXT DEFAULT 'pending'
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_user ON reports(user_id, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_points ON users(points DESC)")


def db_create_report(user_id, username, action_type, points, comment, photo_path, lat, lon) -> int:
    with closing(db()) as conn, conn:
        conn.execute(
            """
            INSERT INTO users (user_id, username, points) VALUES (?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
            """,
            (user_id, username, ),
        )
        cur = conn.execute(
            """
            INSERT INTO reports (user_id, action_type, points, comment, photo_path,
                                 latitude, longitude, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (user_id, action_type, points, comment, photo_path, lat, lon),
        )
        return cur.lastrowid


def db_moderate(report_id: int, approve: bool):
    """Возвращает (результат, user_id, points).
    результат: 'ok' | 'not_found' | 'processed'."""
    new_status = "approved" if approve else "rejected"
    with closing(db()) as conn, conn:
        row = conn.execute(
            "SELECT user_id, points FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        if not row:
            return "not_found", None, None
        user_id, points = row

        # атомарно: сработает только если отчёт ещё pending (защита от двойного клика)
        cur = conn.execute(
            "UPDATE reports SET status = ? WHERE id = ? AND status = 'pending'",
            (new_status, report_id),
        )
        if cur.rowcount == 0:
            return "processed", user_id, points

        if approve:
            conn.execute(
                """
                INSERT INTO users (user_id, points) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET points = points + excluded.points
                """,
                (user_id, points),
            )
        return "ok", user_id, points


def db_get_user(user_id: int):
    with closing(db()) as conn:
        row = conn.execute("SELECT points FROM users WHERE user_id = ?", (user_id,)).fetchone()
        cnt = conn.execute(
            "SELECT COUNT(*) FROM reports WHERE user_id = ? AND status = 'approved'",
            (user_id,),
        ).fetchone()
    return {"points": row[0] if row else 0, "reports_count": cnt[0] if cnt else 0}


def db_leaderboard():
    with closing(db()) as conn:
        return conn.execute(
            "SELECT user_id, username, points FROM users ORDER BY points DESC LIMIT 10"
        ).fetchall()


def db_total_users() -> int:
    with closing(db()) as conn:
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    return row[0] if row else 0


# ---------------------------------------------------------------- Telegram initData
def verify_init_data(init_data: str) -> Optional[dict]:
    """Проверка подписи Telegram WebApp. Возвращает данные пользователя или None."""
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash")
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc_hash = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc_hash, received_hash):
            log.warning("initData: подпись не совпала (приложение открыто из другого бота или токен другой?)")
            return None
        if time.time() - int(parsed.get("auth_date", 0)) > 24 * 3600:
            log.warning("initData: данные устарели, откройте приложение заново")
            return None
        return json.loads(parsed["user"])
    except Exception as e:
        log.warning("initData: ошибка разбора: %r", e)
        return None


# ---------------------------------------------------------------- FastAPI
@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    polling_task = asyncio.create_task(start_telegram_bot())
    yield
    polling_task.cancel()
    await bot.session.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # "*" вместе с credentials=True недопустимо
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


async def start_telegram_bot() -> None:
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("Telegram-бот запущен (polling).")
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("Ошибка polling")


# ---------------------------------------------------------------- команды бота
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    name = html.escape(message.from_user.first_name or "друг")
    text = (
        f"👋 <b>Привет, {name}! Добро пожаловать в Eco Khujand!</b> 🌿\n\n"
        "Мы создаём чистое будущее Худжанда вместе! Вот что ты можешь делать с помощью этого бота:\n\n"
        "🗺️ <b>Карта эко-точек:</b> находи близлежащие контейнеры и урны.\n"
        "📸 <b>Эко-отчёты:</b> убирай территорию или сдавай пластик/стекло, отправляй фото и получай баллы!\n"
        "🏆 <b>Ранги и достижения:</b> зарабатывай очки и расти от <i>Новичка</i> до <i>Эко-Героя</i>!\n\n"
        "Открывай мини-приложение через меню, чтобы начать! 👇"
    )
    markup = None
    if WEBAPP_URL.startswith("https://"):
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🌿 Открыть Eco Khujand", web_app=WebAppInfo(url=WEBAPP_URL))]]
        )
    elif WEBAPP_URL:
        log.warning("WEBAPP_URL должен начинаться с https://, сейчас: %r", WEBAPP_URL)
    try:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        log.exception("Не удалось отправить /start с кнопкой")
        await message.answer(text, parse_mode="HTML")


# ---------------------------------------------------------------- API
@app.post("/api/report")
async def api_receive_report(
    user_id: Optional[int] = Form(None),
    username: str = Form("Эко Активист"),
    action_type: str = Form(...),
    points: int = Form(...),
    comment: str = Form(""),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    init_data: str = Form(""),
    photo: UploadFile = File(...),
):
    # --- кто отправитель
    if init_data:
        tg_user = verify_init_data(init_data)
        if not tg_user:
            raise HTTPException(401, "Неверные данные Telegram")
        user_id = int(tg_user["id"])
        username = tg_user.get("username") or tg_user.get("first_name") or username
    elif REQUIRE_INIT_DATA or user_id is None:
        raise HTTPException(401, "Нужна авторизация через Telegram")

    # --- валидация
    action_type = action_type.strip()[:64]
    comment = comment.strip()[:500]
    points = max(0, min(points, MAX_POINTS))
    if latitude is not None and not -90 <= latitude <= 90:
        latitude = None
    if longitude is not None and not -180 <= longitude <= 180:
        longitude = None
    if latitude is None or longitude is None:
        latitude = longitude = None

    username = username.strip()[:64]
    if username and not username.startswith(("@", "Активист", "Эко")):
        username = f"@{username}"

    # --- фото
    ext = ALLOWED_IMAGE_TYPES.get(photo.content_type)
    if not ext:
        raise HTTPException(400, "Разрешены только JPG, PNG, WEBP")
    content = await photo.read()
    if len(content) > MAX_PHOTO_SIZE:
        raise HTTPException(413, "Фото больше 10 МБ")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{ext}")
    with open(file_path, "wb") as f:
        f.write(content)

    report_id = await asyncio.to_thread(
        db_create_report, user_id, username, action_type, points, comment,
        file_path, latitude, longitude,
    )

    # --- уведомление админу
    try:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_report:{report_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_report:{report_id}"),
            ]]
        )
        geo = (
            f"{latitude}, {longitude}" if latitude is not None else "Не указаны"
        )
        caption = (
            f"📥 <b>Новый эко-отчёт #{report_id}</b>\n\n"
            f"👤 <b>Пользователь:</b> {html.escape(username)} (ID: <code>{user_id}</code>)\n"
            f"📌 <b>Действие:</b> {html.escape(action_type)}\n"
            f"🏅 <b>Баллы:</b> +{points}\n"
            f"💬 <b>Комментарий:</b> {html.escape(comment) or 'Отсутствует'}\n"
            f"📍 <b>Координаты:</b> {geo}"
        )
        await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=FSInputFile(file_path),
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception:
        log.exception("Не удалось отправить отчёт администратору")

    return {"status": "success", "report_id": report_id}


@app.get("/api/user/{user_id}")
async def api_get_user(user_id: int):
    return await asyncio.to_thread(db_get_user, user_id)


@app.get("/api/leaderboard")
async def api_get_leaderboard():
    rows = await asyncio.to_thread(db_leaderboard)
    result = []
    for rank, (user_id, username, points) in enumerate(rows, start=1):
        if not username:
            username = f"Активист #{user_id}"
        elif not username.startswith(("@", "Активист", "Эко")):
            username = f"@{username}"
        result.append({"rank": rank, "username": username, "points": points})
    return result


@app.get("/api/stats")
async def api_get_stats():
    return {"total_users": await asyncio.to_thread(db_total_users)}


# ---------------------------------------------------------------- модерация
@dp.callback_query(F.data.regexp(r"^(approve|reject)_report:\d+$"))
async def handle_report_moderation(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    prefix, report_id_str = callback.data.split(":")
    approve = prefix.startswith("approve")
    report_id = int(report_id_str)

    result, user_id, points = await asyncio.to_thread(db_moderate, report_id, approve)

    if result == "not_found":
        await callback.answer("❌ Отчёт не найден в базе данных!", show_alert=True)
        return
    if result == "processed":
        await callback.answer("⚠️ Этот отчёт уже обработан", show_alert=True)
        return

    if approve:
        note = f"\n\n<b>✅ ОДОБРЕНО! Зачислено +{points} баллов.</b>"
        user_text = (
            f"🎉 <b>Ваш эко-отчёт #{report_id} одобрен!</b>\n"
            f"Вам зачислено <b>+{points} баллов</b>. Посмотреть свой статус можно в Профиле! 🏆"
        )
        await callback.answer("✅ Отчёт одобрен, баллы зачислены!")
    else:
        note = "\n\n<b>❌ ОТКЛОНЕНО.</b>"
        user_text = (
            f"❌ <b>Ваш эко-отчёт #{report_id} был отклонён модератором.</b>\n"
            "Попробуйте отправить более чёткое фото."
        )
        await callback.answer("❌ Отчёт отклонён.")

    try:
        # html_text сохраняет форматирование исходной подписи
        base = callback.message.html_text if callback.message.caption else ""
        await callback.message.edit_caption(caption=base + note, parse_mode="HTML", reply_markup=None)
    except Exception:
        log.exception("Не удалось обновить подпись сообщения")

    try:
        await bot.send_message(chat_id=user_id, text=user_text, parse_mode="HTML")
    except Exception as e:
        log.warning("Не удалось написать пользователю %s: %s", user_id, e)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080))) 
