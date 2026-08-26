import os
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardRemove

import db

TOKEN = os.getenv("BOT_TOKEN", "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0")

bot = Bot(token=TOKEN)
dp = Dispatcher()

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    print("Database connected. FastAPI server started successfully.")
    polling_task = asyncio.create_task(dp.start_polling(bot))
    print("Bot polling started...")
    yield
    polling_task.cancel()
    await bot.session.close()

app = FastAPI(title="Eco Khujand API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ReportData(BaseModel):
    user_id: int
    action_type: str
    points: int
    photo_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

@app.get("/api/user/{user_id}")
async def get_user(user_id: int):
    profile = db.get_user_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile

@app.post("/api/report")
async def submit_report(data: ReportData):
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
        print(f"Ошибка отправки сообщения: {e}")

    return {"status": "success", "profile": updated_profile}

# --- Обработка /start с очисткой экрана ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    db.register_user_if_not_exists(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=message.from_user.full_name or ""
    )
    
    # ReplyKeyboardRemove удаляет старые нижние кнопки (Профиль, Карта, Отчёт)
    await message.answer(
        f"Привет, {message.from_user.first_name}! 🌿\n\n"
        f"Добро пожаловать в **Eco Khujand**.\n"
        f"Нажмите на синюю кнопку **«Eco App»** внизу экрана, чтобы открыть карту, профиль и отправку отчётов.",
        reply_markup=ReplyKeyboardRemove()
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)