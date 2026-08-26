import os
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

import db

# Укажите токен бота прямо здесь для локального теста, если нет переменной окружения
TOKEN = os.getenv("BOT_TOKEN", "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-app.onrender.com")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Lifespan: Управление фоновыми процессами ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация БД при старте
    db.init_db()
    print("Database connected. FastAPI server started successfully.")
    
    # Запуск поллинга бота в фоновом режиме
    polling_task = asyncio.create_task(dp.start_polling(bot))
    print("Bot polling started...")
    
    yield  # Сервер FastAPI работает
    
    # Остановка бота при завершении работы сервера
    polling_task.cancel()
    await bot.session.close()
    print("Bot polling stopped.")

# Инициализация приложения FastAPI с lifespan
app = FastAPI(title="Eco Khujand API", lifespan=lifespan)

# Настройки CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Схемы ---
class ReportData(BaseModel):
    user_id: int
    action_type: str
    points: int
    photo_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

# --- FastAPI Эндпоинты ---
@app.get("/api/user/{user_id}")
async def get_user(user_id: int):
    profile = db.get_user_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile

@app.post("/api/report")
async def submit_report(data: ReportData):
    """Принимает отчёт из WebApp и начисляет эко-баллы."""
    user = db.get_user_profile(data.user_id)
    
    if not user:
        db.register_user_if_not_exists(data.user_id, "user", "Эко Пользователь")
    
    updated_profile = db.add_points(
        user_id=data.user_id,
        points=data.points,
        action_type=data.action_type,
        photo_url=data.photo_url,
        lat=data.latitude,
        lon=data.longitude
    )
    
    try:
        await bot.send_message(
            chat_id=data.user_id,
            text=f"🌱 **Отчёт принят!**\n\nВам начислено: **+{data.points} эко-баллов**.\nВаш текущий баланс: **{updated_profile['points']} баллов**."
        )
    except Exception as e:
        print(f"Ошибка отправки уведомления в Telegram: {e}")

    return {"status": "success", "profile": updated_profile}

# --- Telegram Bot Обработчики ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    db.register_user_if_not_exists(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=message.from_user.full_name or ""
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Открыть Eco App", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(
        f"Привет, {message.from_user.first_name}! 🌿\nДобро пожаловать в **Eco Khujand**.\nСобирай мусор, сдавай пластик и получай эко-баллы!",
        reply_markup=kb
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)