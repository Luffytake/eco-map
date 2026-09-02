import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

BOT_TOKEN = "8701787724:AAHSI0Vw_v6oG3ptuxy2EKWOooKfV6Q-qx0" 

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Данные для хранения пользователей и отчётов (в памяти сервера)
USERS_DB = {}
REPORTS_DB = []

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

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я eco-khujand-bot.\n\n"
        "🟢 — Мусорные баки\n"
        "🔵 — Урны\n\n"
        "Используй кнопки ниже, чтобы открыть карту, профиль или сообщить о переполненном баке!",
        reply_markup=get_main_reply_keyboard()
    )

@dp.message(F.text == "Сообщить о проблеме ⚠️")
async def handle_report(message: types.Message):
    await message.answer("Пришлите фото переполненного бака или геолокацию, чтобы мы передали информацию службы очистки!")

# --- API ENDPOINTS ДЛЯ WEBAPP ---

async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def handle_get_user(request):
    user_id = str(request.match_info.get("user_id", ""))
    user_data = USERS_DB.get(user_id, {"points": 0, "reports_count": 0})
    return web.json_response(user_data)

async def handle_create_report(request):
    try:
        data = await request.post()
        user_id = str(data.get("user_id", "123456"))
        action_type = data.get("action_type", "Эко-активность")
        points = int(data.get("points", 0))
        comment = data.get("comment", "")
        
        if user_id not in USERS_DB:
            USERS_DB[user_id] = {"points": 0, "reports_count": 0}

        USERS_DB[user_id]["points"] += points
        USERS_DB[user_id]["reports_count"] += 1

        REPORTS_DB.append({
            "user_id": user_id,
            "action_type": action_type,
            "points": points,
            "comment": comment
        })

        return web.json_response({"status": "success", "current_points": USERS_DB[user_id]["points"]})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

# --- MIDDLEWARE ДЛЯ CORS (Разрешает запросы от WebApp) ---

@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=200)
    else:
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# --- ЗАПУСК ВЕБ-СЕРВЕРА ---

async def start_web_server():
    app = web.Application(middlewares=[cors_middleware])
    
    # Добавляем маршруты API
    app.router.add_get("/ping", handle_ping)
    app.router.add_get("/api/user/{user_id}", handle_get_user)
    app.router.add_post("/api/report", handle_create_report)
    
    # Раздача статических файлов (HTML, JS, CSS)
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