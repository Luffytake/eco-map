import os
import asyncio
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

# --- НАСТРОЙКИ И ИНИЦИАЛИЗАЦИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "5581941983")  # ID чата модерации

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

app = FastAPI(title="Eco Khujand API")

# 1. Настройка CORS для Telegram WebApp
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ИВЕНТЫ ЗАПУСКА ---
@app.on_event("startup")
async def startup_event():
    # Запускаем поллинг бота в фоновом режиме вместе с FastAPI
    asyncio.create_task(dp.start_polling(bot))

# --- ЭНДПОИНТЫ API ---
@app.get("/")
async def read_root():
    return {"status": "ok", "message": "Eco Khujand Server is running"}

@app.post("/api/report")
async def send_report(
    user_id: int = Form(...),
    username: Optional[str] = Form(None),
    action_type: str = Form(...),
    points: int = Form(...),
    comment: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    photo: UploadFile = File(...)
):
    try:
        # Чтение загруженного файла в память
        photo_bytes = await photo.read()
        input_file = BufferedInputFile(photo_bytes, filename=photo.filename)

        # Формирование текста сообщения для админов
        user_info = f"@{username}" if username else f"ID: {user_id}"
        caption_text = (
            f"🌱 <b>Новый эко-отчёт!</b>\n\n"
            f"👤 <b>Пользователь:</b> {user_info}\n"
            f"🎯 <b>Действие:</b> {action_type}\n"
            f"⭐ <b>Баллы:</b> +{points}\n"
        )
        if comment:
            caption_text += f"💬 <b>Комментарий:</b> {comment}\n"
        if latitude and longitude:
            caption_text += f"📍 <b>Геолокация:</b> {latitude:.5f}, {longitude:.5f}\n"

        # Клавиатура модерации
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{user_id}_{points}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{user_id}")
            ]
        ])

        # Отправка фото в чат модератора
        await bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=input_file,
            caption=caption_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )

        return {"status": "success", "message": "Report submitted successfully"}

    except Exception as e:
        print(f"Error processing report: {e}")
        raise HTTPException(status_code=500, detail=str(e))
