import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0"  

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

WEBAPP_URL = "https://khujand-eco-bot.onrender.com/profile.html?v=1.1"

def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Открыть профиль 🌿",
        web_app=WebAppInfo(url=WEBAPP_URL)
    )
    return builder.as_markup()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        f"Привет, {message.from_user.first_name}! Добро пожаловать в Khujand Eco Bot.\n"
        "Нажмите на кнопку ниже, чтобы открыть ваш профиль:",
        reply_markup=get_main_keyboard()
    )

# Минимальный HTTP-хэндлер для Render Health Check
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    logging.basicConfig(level=logging.INFO)
    await start_web_server()  # Запускаем фоновый веб-сервер для порта
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())