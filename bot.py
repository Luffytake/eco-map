import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = os.getenv("8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0")

if not BOT_TOKEN:
    raise ValueError("Переменная BOT_TOKEN не задана в настройках Render!")

bot = Bot(token=BOT_TOKEN)
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

async def handle(request):
    return web.Response(text="Бот работает!")

async def main():
    # 1. Удаляем возможный старый webhook и сбрасываем зависшие сообщения
    await bot.delete_webhook(drop_pending_updates=True)
    print("Старый webhook сброшен...")

    # 2. Запускаем polling в фоновом режиме
    asyncio.create_task(dp.start_polling(bot))
    print("Бот успешно запущен и готов к тестам...")

    # 3. Настраиваем и запускаем веб-сервер для Render
    app = web.Application()
    app.router.add_get('/', handle)
    
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    # Держим процесс активным
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
