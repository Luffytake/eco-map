import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

BOT_TOKEN = "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0"  # Вставьте сюда ваш токен от BotFather

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# URL вашего WebApp
WEBAPP_MAP_URL = "https://khujand-eco-bot.onrender.com/index.html?v=1.1"
WEBAPP_PROFILE_URL = "https://khujand-eco-bot.onrender.com/profile.html?v=1.1"

# Функция создания нижних меню-кнопок
def get_main_reply_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Открыть карту 🗺️", web_app=WebAppInfo(url=WEBAPP_MAP_URL))
            ],
            [
                KeyboardButton(text="Сообщить о проблеме ⚠️")
            ],
            [
                KeyboardButton(text="Профиль 👤", web_app=WebAppInfo(url=WEBAPP_PROFILE_URL))
            ]
        ],
        resize_keyboard=True
    )
    return keyboard

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я eco-khujand-bot.\n\n"
        "🟢 — Мусорные баки\n"
        "🔵 — Урны\n\n"
        "Используй кнопки ниже, чтобы открыть карту, профиль или сообщить о переполненном баке!",
        reply_markup=get_main_reply_keyboard()
    )

# Легкий веб-сервер для проходимости Health Check на Render
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
    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())