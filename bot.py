import asyncio
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN", "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0")
DB_NAME = "eco_khujand.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

WEBAPP_MAP_URL = "https://khujand-eco-bot.onrender.com/index.html?v=1.2"
WEBAPP_PROFILE_URL = "https://khujand-eco-bot.onrender.com/profile.html?v=1.3"

def get_main_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Открыть карту 🗺️", web_app=WebAppInfo(url=WEBAPP_MAP_URL))],
            [KeyboardButton(text="Сообщить о проблеме ⚠️")],
            [KeyboardButton(text="Профиль 👤", web_app=WebAppInfo(url=WEBAPP_PROFILE_URL))]
        ],
        resize_keyboard=True
    )

# --- ОБРАБОТКА /start ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    welcome_text = (
        f"👋 <b>Привет, {message.from_user.first_name}! Добро пожаловать в Eco Khujand!</b> 🌿\n\n"
        "Мы создаём чистое будущее Худжанда вместе! Вот что ты можешь делать с помощью этого бота:\n\n"
        "🗺️ <b>Карта эко-точек:</b> находи близлежащие контейнеры и урны.\n"
        "📸 <b>Эко-отчёты:</b> убирай территорию или сдавай пластик/стекло, отправляй фото и получай баллы!\n"
        "🏆 <b>Ранги и достижения:</b> зарабатывай очки и расти от <i>Новичка</i> до <i>Эко-Героя</i>!\n"
        "⚠️ <b>Проблемы:</b> сообщай о переполненных баках прямо из бота.\n\n"
        "Используй меню ниже, чтобы начать! 👇"
    )
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_reply_keyboard())

@dp.message(F.text == "Сообщить о проблеме ⚠️")
async def handle_report(message: types.Message):
    await message.answer("Пришлите фото переполненного бака или геолокацию, чтобы мы передали информацию в службы очистки!")


# --- ОБРАБОТКА КНОПОК МОДЕРАЦИИ ДЛЯ АДМИНА (Одобрить / Отклонить) ---

@dp.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_") | F.data.startswith("approve_report:") | F.data.startswith("reject_report:"))
async def handle_report_moderation(callback: types.CallbackQuery):
    data = callback.data
    
    # Парсим ID отчёта и действие
    if ":" in data:
        action, report_id = data.split(":")
    else:
        parts = data.split("_")
        action = parts[0]
        report_id = parts[1]
        
    report_id = int(report_id)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Получаем данные об отчёте
    cursor.execute("SELECT user_id, points, status FROM reports WHERE id = ?", (report_id,))
    report = cursor.fetchone()

    if not report:
        await callback.answer("❌ Отчёт не найден в базе данных!", show_alert=True)
        conn.close()
        return

    user_id, points, status = report

    if status != "pending":
        await callback.answer(f"⚠️ этот отчёт уже обработан (статус: {status})", show_alert=True)
        conn.close()
        return

    if action in ["approve", "approve_report"]:
        # 1. Обновляем статус отчёта
        cursor.execute("UPDATE reports SET status = 'approved' WHERE id = ?", (report_id,))
        
        # 2. Начисляем баллы пользователю
        cursor.execute("""
            INSERT INTO users (user_id, points) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET points = points + ?
        """, (user_id, points, points))
        
        conn.commit()
        conn.close()

        # 3. Обновляем подпись к фото у админа
        new_caption = callback.message.caption + f"\n\n<b>✅ ОДОБРЕНО! Зачислено +{points} баллов.</b>"
        await callback.message.edit_caption(caption=new_caption, parse_mode="HTML", reply_markup=None)
        await callback.answer("✅ Отчёт одобрен, баллы успешно зачислены!")

        # 4. Уведомляем пользователя
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"🎉 <b>Ваш эко-отчёт #{report_id} одобрен!</b>\nВам зачислено <b>+{points} баллов</b>. Посмотреть свой статус можно в Профиле! 🏆",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

    elif action in ["reject", "reject_report"]:
        # Обновляем статус на rejected
        cursor.execute("UPDATE reports SET status = 'rejected' WHERE id = ?", (report_id,))
        conn.commit()
        conn.close()

        new_caption = callback.message.caption + "\n\n<b>❌ ОТКЛОНЕНО.</b>"
        await callback.message.edit_caption(caption=new_caption, parse_mode="HTML", reply_markup=None)
        await callback.answer("❌ Отчёт отклонён.")

        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"❌ <b>Ваш эко-отчёт #{report_id} был отклонён модератором.</b>\nПопробуйте отправить более чёткое фото.",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Не удалось отправить сообщение пользователю {user_id}: {e}")


async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())   
