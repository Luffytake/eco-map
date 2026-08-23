import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

BOT_TOKEN = "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0"  # Вставьте ваш токен

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

WEBAPP_MAP_URL = "https://khujand-eco-bot.onrender.com/index.html?v=1.2"
WEBAPP_PROFILE_URL = "https://khujand-eco-bot.onrender.com/profile.html?v=1.2"

def get_main_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открыть карту 🗺️", web_app=WebAppInfo(url=WEBAPP_MAP_URL))],
            [KeyboardButton(text="Сообщить о проблеме ⚠️")],
            [KeyboardButton(text="Профиль 👤", web_app=WebAppInfo(url=WEBAPP_PROFILE_URL))]
        ],
        resize_keyboard=True
    )

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я eco-khujand-bot.\n\n"
        "🟢 — Мусорные баки\n"
        "🔵 — Урны\n\n"
        "Используй кнопки ниже, чтобы открыть карту, профиль или сообщить о переполненном баке!",
        reply_markup=get_main_reply_keyboard()
    )

# Обработка текстовой кнопки "Сообщить о проблеме"
@dp.message(F.text == "Сообщить о проблеме ⚠️")
async def handle_report(message: types.Message):
    await message.answer("Пришлите фото переполненного бака или геолокацию, чтобы мы передали информацию службы очистки!")

# Веб-сервер: раздача статических HTML-файлов из текущей папки
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/ping", handle_ping)
    # Раздача HTML/CSS/JS файлов из корня проекта
    app.router.add_static("/", path=".", show_index=True)
    
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