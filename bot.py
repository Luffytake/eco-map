import os
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

MY_TEMP_TOKEN = "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0"
ADMIN_ID = 1631981047

bot = Bot(token=MY_TEMP_TOKEN)
dp = Dispatcher()

class ReportState(StatesGroup):
    waiting_for_report = State()

# ЕДИНСТВЕННАЯ ИСПРАВЛЕННАЯ КЛАВИАТУРА
def get_main_keyboard():
    web_app_url = "https://luffytake.github.io/eco-map/"
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открыть карту 🗺️", web_app=WebAppInfo(url=web_app_url))],
            [KeyboardButton(text="Сообщить о проблеме ⚠️")],
            [KeyboardButton(text="Профиль 👤")]
        ],
        resize_keyboard=True
    )
    return keyboard

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я eco-khujand-bot.\n\n"
        "🟢 — Мусорные баки\n"
        "🔵 — Урны\n\n"
        "Используй кнопки ниже, чтобы открыть карту, профиль или сообщить о переполненном баке!",
        reply_markup=get_main_keyboard()
    )

# Обработчик профиля
@dp.message(F.text == "Профиль 👤")
async def process_profile(message: types.Message):
    user_name = message.from_user.first_name
    user_id = message.from_user.id
    
    eco_points = 0
    reports_count = 0
    rank = "Эко-новичок 🌱"
    
    profile_text = (
        f"👤 **Личный кабинет**\n\n"
        f"Имя: **{user_name}** (ID: `{user_id}`)\n"
        f"Статус: **{rank}**\n"
        f"🏆 Эко-баллы: **{eco_points}**\n"
        f"📬 Отправлено отчетов: **{reports_count}**\n\n"
        f"💡 *Зарабатывай баллы, отправляя фото переполненных баков и участвуя в субботниках Худжанда!*"
    )
    
    await message.answer(profile_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(F.text == "Сообщить о проблеме ⚠️")
async def process_report_start(message: types.Message, state: FSMContext):
    await state.set_state(ReportState.waiting_for_report)
    
    cancel_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )
    
    await message.answer(
        "Отправь фото переполненного бака, описание проблемы или геопозицию.\n\n"
        "Чтобы вернуться назад, нажми ❌ Отмена.",
        reply_markup=cancel_keyboard
    )

@dp.message(F.text == "❌ Отмена")
async def cancel_report(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Отправка отменена.", reply_markup=get_main_keyboard())

@dp.message(ReportState.waiting_for_report)
async def process_report_send(message: types.Message, state: FSMContext):
    username = message.from_user.username
    user_str = f"@{username}" if username else message.from_user.first_name
    
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🚨 НОВОЕ СООБЩЕНИЕ О ПРОБЛЕМЕ!\n👤 От: {user_str} (ID: {message.from_user.id})"
        )
        await message.copy_to(chat_id=ADMIN_ID)
        await message.answer("Спасибо! Твоё сообщение отправлено администрации города.", reply_markup=get_main_keyboard())
    except Exception as e:
        print(f"Ошибка пересылки: {e}")
        await message.answer("Произошла ошибка при отправке.", reply_markup=get_main_keyboard())
    
    await state.clear()

@dp.message()
async def default_handler(message: types.Message):
    await message.answer("Пожалуйста, используй кнопки ниже для навигации 👇", reply_markup=get_main_keyboard())

async def handle(request):
    return web.Response(text="Бот работает!")

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
