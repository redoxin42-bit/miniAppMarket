import os
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiohttp import web
from database import get_db_connection

BOT_TOKEN = os.getenv("BOT_TOKEN", "8891333611:AAENpJP5do6p27_GbrHQFqe-0uu3yBhoMdo")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Состояния для создания товара в админке
class AdminStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_price = State()
    waiting_for_img = State()
    waiting_for_delete_id = State()

# --- ЛОГИКА БОТА ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Пользователь"
    username = message.from_user.username or "anonymous"
    
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
        # Первого пользователя или по умолчанию делаем обычным, права выдадим через код или /admin
        conn.execute(
            "INSERT INTO users (id, first_name, username, invited_by, join_date, role) VALUES (?, ?, ?, ?, ?, 'user')",
            (user_id, first_name, username, invited_by, datetime.now().isoformat())
        )
        conn.commit()
    conn.close()

    app_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'localhost')}/"
    await message.answer(
        f"Привет, {first_name}! Добро пожаловать в CRYPTOXRM.\nОткрой Mini App для управления и покупок.",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Открыть Магазин", web_app=types.WebAppInfo(url=app_url))]
        ])
    )

# --- АДМИН ПАНЕЛЬ В ТЕЛЕГРАМЕ ---
@dp.message(Command("admin"))
async def admin_menu(message: types.Message):
    user_id = message.from_user.id
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    
    # Авто-апгрейд первого зашедшего до админа для удобства тестов
    if user and user['role'] != 'admin':
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
        conn.commit()
    conn.close()

    kb = types.ReplyKeyboardMarkup(keyboard=[
        [types.KeyboardButton(text="➕ Добавить товар"), types.KeyboardButton(text="❌ Удалить товар")],
        [types.KeyboardButton(text="📋 Список товаров")]
    ], resize_keyboard=True)
    
    await message.answer("⚙️ Добро пожаловать в панель управления магазином CRYPTOXRM:", reply_markup=kb)

@dp.message(lambda msg: msg.text == "➕ Добавить товар")
async def add_product_start(message: types.Message, state: FSMContext):
    await message.answer("Введите название товара:")
    await state.set_state(AdminStates.waiting_for_title)

@dp.message(AdminStates.waiting_for_title)
async def add_product_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Введите цену товара в USD (например: 15.5):")
    await state.set_state(AdminStates.waiting_for_price)

@dp.message(AdminStates.waiting_for_price)
async def add_product_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text)
        await state.update_data(price=price)
        await message.answer("Отправьте прямую ссылку на картинку товара (или отправьте '-' если картинки нет):")
        await state.set_state(AdminStates.waiting_for_img)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число.")

@dp.message(AdminStates.waiting_for_img)
async def add_product_final(message: types.Message, state: FSMContext):
    img_url = message.text if message.text != '-' else ''
    data = await state.get_data()
    
    conn = get_db_connection()
    conn.execute("INSERT INTO products (title, price, img) VALUES (?, ?, ?)", (data['title'], data['price'], img_url))
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Товар «{data['title']}» успешно добавлен на витрину Mini App!")
    await state.clear()

@dp.message(lambda msg: msg.text == "❌ Удалить товар")
async def delete_product_start(message: types.Message, state: FSMContext):
    await message.answer("Введите ID товара, который нужно удалить:")
    await state.set_state(AdminStates.waiting_for_delete_id)

@dp.message(AdminStates.waiting_for_delete_id)
async def delete_product_exec(message: types.Message, state: FSMContext):
    try:
        p_id = int(message.text)
        conn = get_db_connection()
        conn.execute("DELETE FROM products WHERE id = ?", (p_id,))
        conn.commit()
        conn.close()
        await message.answer(f"💥 Товар с ID {p_id} удален.")
        await state.clear()
    except ValueError:
        await message.answer("ID должен быть числом.")

@dp.message(lambda msg: msg.text == "📋 Список товаров")
async def list_products_admin(message: types.Message):
    conn = get_db_connection()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    if not products:
        await message.answer("На витрине пока нет товаров.")
        return
    text = "🛍 **Текущие товары:**\n\n"
    for p in products:
        text += f"🆔 {p['id']} | {p['title']} — ${p['price']}\n"
    await message.answer(text, parse_mode="Markdown")

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
    
    # Берем или создаем динамически, если зашли напрямую через WebApp
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    
    if not user:
        conn.execute("INSERT INTO users (id, first_name, username) VALUES (?, 'Покупатель', 'tg_user')", (user_id,))
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        
    referrals = conn.execute("SELECT username, join_date FROM users WHERE invited_by = ?", (user_id,)).fetchall()
    orders = conn.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    conn.close()
    
    return web.json_response({
        "id": user["id"],
        "first_name": user["first_name"],
        "username": user["username"],
        "balance": user["balance"],
        "invited_count": len(referrals),
        "referrals": [dict(r) for r in referrals],
        "orders": [dict(o) for o in orders]
    })

async def api_create_order(request):
    data = await request.json()
    user_id = data.get("user_id")
    total_amount = data.get("total_amount")
    method = data.get("method")
    
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO orders (user_id, total_amount, payment_method, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, total_amount, method, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return web.json_response({"success": True})

async def init_app():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/api/products', api_get_products)
    app.router.add_get('/api/user/{user_id}', api_get_user)
    app.router.add_post('/api/order', api_create_order)
    return app

async def main():
    asyncio.create_task(dp.start_polling(bot))
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    print(f"Сервер активен на порту {port}")
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.run(main())
