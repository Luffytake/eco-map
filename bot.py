import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, ReplyKeyboardMarkup, KeyboardButton

# Наш токен
bot = Bot(token="8701787724:AAGv8UdRywycyahHO0CVd2Q5O6di0s6hdWQ")
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    web_app_url = "https://luffytake.github.io/eco-map/"
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открыть карту 🗺️", web_app=WebAppInfo(url=web_app_url))]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "Привет! Я бот эко-карты Худжанда. Нажми на кнопку ниже, чтобы увидеть карту мусорных баков и урн.",
        reply_markup=keyboard
    )

# Простейший веб-сервер, чтобы Render был доволен
async def handle(request):
    return web.Response(text="Бот работает!")

async def main():
    print("Бот успешно запущен и готов к тестам...")
    
    # Запускаем опрос Telegram в фоновом режиме
    asyncio.create_task(dp.start_polling(bot))
    
    # Настраиваем веб-сервер на порт, который дает Render
    app = web.Application()
    app.router.add_get('/', handle)
    
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    # Держим сервер запущенным бесконечно
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
