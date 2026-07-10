import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, ReplyKeyboardMarkup, KeyboardButton

# Вставь сюда свой токен от BotFather в кавычках
BOT_TOKEN = "8701787724:AAGv8UdRywycyahHO0CVd2Q5O6di0s6hdWQ"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    # Твоя рабочая ссылка на карту Худжанда
    web_app_url = "https://luffytake.github.io/eco-map/" 
    
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открыть карту 🗺️", web_app=WebAppInfo(url=web_app_url))]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n"
        f"Я бот проекта Eco-Khujand.\n"
        f"Нажми на кнопку ниже, чтобы увидеть карту урн и баков нашего города!"
        f"🟢 - Мусорные баки    "
        f"🔵 - Мусорная урна",
        reply_markup=kb
    )

async def main():
    print("Бот успешно запущен и готов к тестам...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
