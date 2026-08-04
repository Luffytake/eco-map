import os
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, ReplyKeyboardMarkup, KeyboardButton

# ==========================================================
# НЕБЕЗОПАСНЫЙ КОД ТОЛЬКО ДЛЯ ОДНОДНЕВНОЙ ПРЕЗЕНТАЦИИ!
# Сразу после презентации этот токен будет украден.
# ==========================================================

# 1. ВСТАВЬ СЮДА СВОЙ ТОКЕН В КАВЫЧКИ:
MY_TEMP_TOKEN = "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0"

# Инициализация бота напрямую через токен в коде
bot = Bot(token=MY_TEMP_TOKEN)
dp = Dispatcher()

# Обработка команды /start
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    # Ссылка на твое WebApp (твою карту)
    web_app_url = "https://luffytake.github.io/eco-map/"
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открыть карту 🗺️", web_app=WebAppInfo(url=web_app_url))]
        ],
        resize_keyboard=True
    )
    
    await message.answer("Привет! Я eco-khujand-bot. Нажми на кнопку ниже, чтобы увидеть карту мусорных баков(🟢) и урн(🔵).",
        reply_markup=keyboard
    )

# Минимальный веб-сервер для Render, чтобы он не усыплял бота
async def handle(request):
    return web.Response(text="Бот запущен для презентации! (защита отключена)")

async def main():
    # Настраиваем веб-сервер на порт 10000 (стандарт для Render)
    app = web.Application()
    app.router.add_get('/', handle)
    
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    # 2. Удаляем старые вебхуки, чтобы бот точно проснулся
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем опрос сообщений в фоновом режиме
    asyncio.create_task(dp.start_polling(bot))
    
    # Запускаем веб-сервер и держим его активным
    await site.start()
    
    # Вечный цикл, чтобы процесс не завершался
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
