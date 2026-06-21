import os
import asyncio
import json
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiohttp import web
from database import get_db_connection

BOT_TOKEN = os.getenv("BOT_TOKEN", "8891333611:AAENpJP5do6p27_GbrHQFqe-0uu3yBhoMdo")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ЛОГИКА БОТА ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    
    # Проверка реферала
    args = message.text.split()
    invited_by = None
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            invited_by = int(args[1].replace("ref", ""))
            if invited_by == user_id:
                invited_by = None
        except ValueError:
            pass

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.execute(
            "INSERT INTO users (id, first_name, username, invited_by, join_date) VALUES (?, ?, ?, ?, ?)",
            (user_id, first_name, username, invited_by, datetime.now().isoformat())
        )
        conn.commit()
    conn.close()

    await message.answer(
        f"Привет, {first_name}! Добро пожаловать в CRYPTOXRM.\nОткрой Mini App для покупок.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Открыть магазин", web_app=types.WebAppInfo(url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'localhost')}/"))]
        ])
    )

# --- API ДЛЯ МИНИ-АПП ---
async def handle_index(request):
    return web.FileResponse('index.html')

async def api_get_products(request):
    conn = get_db_connection()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return web.json_response([dict(p) for p in products])

async def api_get_user(request):
    user_id = int(request.match_info['user_id'])
    conn = get_db_connection()
    
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return web.json_response({"error": "User not found"}, status=404)
        
    referrals = conn.execute("SELECT username, join_date FROM users WHERE invited_by = ?", (user_id,)).fetchall()
    orders = conn.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    conn.close()
    
    return web.json_response({
        "id": user["id"],
        "first_name": user["first_name"],
        "balance": user["balance"],
        "invited_count": len(referrals),
        "bonus_earned": len(referrals) * 5,  # Пример статики
        "active_count": len(referrals),
        "referrals": [dict(r) for r in referrals],
        "orders": [{"id": o["id"], "total_amount": o["total_amount"], "payment_method": o["payment_method"], "timestamp": o["timestamp"], "titles": ["Заказ цифровых товаров"]} for o in orders]
    })

async def api_create_order(request):
    data = await request.json()
    user_id = data.get("user_id")
    total_amount = data.get("total_amount")
    method = data.get("method") # 'stars' или 'cryptobot'
    
    # Тут должна быть интеграция создания инвойса (CryptoBot API / Telegram Invoice для Stars)
    # В рамках примера симулируем успешное создание счета и сохранение:
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO orders (user_id, total_amount, payment_method, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, total_amount, method, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    
    # В реальном продакшене возвращается ссылка на оплату `pay_url`
    return web.json_response({"success": True, "message": f"Счет через {method} успешно создан!"})

# --- ИНИЦИАЛИЗАЦИЯ И ЗАПУСК СЕРВЕРА ---
async def init_app():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/api/products', api_get_products)
    app.router.add_get('/api/user/{user_id}', api_get_user)
    app.router.add_get('/api/order', api_create_order)
    return app

async def main():
    asyncio.create_task(dp.start_polling(bot))
    
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"Робот запущен. Веб-сервер работает на порту: {port}")
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.run(main())
