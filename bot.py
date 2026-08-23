import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Токен вашего бота
BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Ссылка на ваш WebApp на Render с добавлением версии для сброса кэша Telegram
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

async def main():
    logging.basicConfig(level=logging.INFO)
    # Удаляем вебхуки перед запуском polling, чтобы избежать конфликтов
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main()) 