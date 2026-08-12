import os
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# ==========================================================
# КОД ДЛЯ ПРЕЗЕНТАЦИИ С КНОПКОЙ ОБРАТНОЙ СВЯЗИ
# ==========================================================

MY_TEMP_TOKEN = "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0"

# ⚠️ ВСТАВЬ СЮДА СВОЙ TELEGRAM ID (получи у @userinfobot)
ADMIN_ID = 1631981047

bot = Bot(token=MY_TEMP_TOKEN)
dp = Dispatcher()

# Состояния для отправки жалобы
class ReportState(StatesGroup):
    waiting_for_report = State()

# Главная клавиатура
def get_main_keyboard():
    web_app_url = "https://luffytake.github.io/eco-map/"
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открыть карту 🗺️", web_app=WebAppInfo(url=web_app_url))],
            [KeyboardButton(text="Сообщить о проблеме ⚠️")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Старт
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я **eco-khujand-bot**.\n\n"
        "🟢 — Мусорные баки\n"
        "🔵 — Урны\n\n"
        "Используй кнопки ниже, чтобы открыть карту или сообщить о переполненном баке!",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

# Нажатие на "Сообщить о проблеме ⚠️"
@dp.message(F.text == "Сообщить о проблеме ⚠️")
async def process_report_start(message: types.Message, state: FSMContext):
    await state.set_state(ReportState.waiting_for_report)
    
    cancel_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )
    
    await message.answer(
        "Отправь фото переполненного бака, описание проблемы или геопозицию.\n\n"
        "Чтобы вернуться назад, нажми **❌ Отмена**.",
        reply_markup=cancel_keyboard,
        parse_mode="Markdown"
    )

# Отмена отправки
@dp.message(F.text == "❌ Отмена")
async def cancel_report(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Отправка отменена.", reply_markup=get_main_keyboard())

# Прием отчета (фото, текст или геопозиция)
@dp.message(ReportState.waiting_for_report)
async def process_report_send(message: types.Message, state: FSMContext):
    user_info = f"👤 От: @{message.from_user.username or message.from_user.first_name} (ID: `{message.from_user.id}`)"
    
    # Пересылаем сообщение администратору
    try:
        await bot.send_message(ADMIN_ID, f"🚨 **НОВОЕ СООБЩЕНИЕ О ПРОБЛЕМЕ!**\n{user_info}", parse_mode="Markdown")
        await message.forward(chat_id=ADMIN_ID)
        await message.answer("Спасибо! Твоё сообщение отправлено администрации города.", reply_markup=get_main_keyboard())
    except Exception as e:
        await message.answer("Произошла ошибка при отправке. Убедись, что администратор запустил бота.", reply_markup=get_main_keyboard())
    
    await state.clear()

# Ответ на любые другие сообщения
@dp.message()
async def default_handler(message: types.Message):
    await message.answer("Пожалуйста, используй кнопки ниже для навигации 👇", reply_markup=get_main_keyboard())

# Веб-сервер Render
async def handle(request):
    return web.Response(text="Бот и функционал жалоб работают!")

async def main():
    app = web.Application()
    app.router.add_get('/', handle)
    
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(dp.start_polling(bot))
    await site.start()
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
