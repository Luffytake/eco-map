import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, ReplyKeyboardMarkup, KeyboardButton

# Наш проверенный токен команды "Тихо, не спеша, без суеты"
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

async def main():
    print("Бот успешно запущен и готов к тестам...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
