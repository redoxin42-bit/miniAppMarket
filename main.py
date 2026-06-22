import os
import asyncio
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiohttp import web
from database import get_db_connection

BOT_TOKEN = os.getenv("BOT_TOKEN", "8891333611:AAENpJP5do6p27_GbrHQFqe-0uu3yBhoMdo")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class AdminStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_price = State()
    waiting_for_img = State()
    waiting_for_delete_id = State()

# --- МЕНЮ БОТА ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Покупатель"
    username = message.from_user.username or "user"
    
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
            "INSERT INTO users (id, first_name, username, invited_by, join_date, role) VALUES (?, ?, ?, ?, ?, 'user')",
            (user_id, first_name, username, invited_by, datetime.now().isoformat(),)
        )
        conn.commit()
    conn.close()

    # Ссылка формируется динамически под твой локальный хост или домен Render
    app_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'localhost')}/"
    if 'localhost' in app_url or '0.0.0.0' in app_url:
        # Для тестов в Termux (подставь свой URL из Ngrok, если тестируешь удаленно)
        app_url = "http://localhost:8080/"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Открыть Магазин", web_app=WebAppInfo(url=app_url))]
    ])
    
    await message.answer(f"Привет, {first_name}! Добро пожаловать в CRYPTOXRM.\nНажми кнопку ниже, чтобы перейти к покупкам.", reply_markup=kb)

# --- ИНЛАЙН АДМИНКА ---
def get_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить товар", callback_code="admin_add")],
        [InlineKeyboardButton(text="❌ Удалить товар", callback_code="admin_del")],
        [InlineKeyboardButton(text="📋 Список товаров", callback_code="admin_list")]
    ])

@dp.message(Command("admin"))
async def admin_menu(message: types.Message):
    user_id = message.from_user.id
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    
    if user and user['role'] != 'admin':
        conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
        conn.commit()
    conn.close()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_add")],
        [InlineKeyboardButton(text="❌ Удалить товар", callback_data="admin_del")],
        [InlineKeyboardButton(text="📋 Список товаров", callback_data="admin_list")]
    ])
    await message.answer("⚙️ Панель управления CRYPTOXRM:", reply_markup=kb)

@dp.callback_query(F.data == "admin_add")
async def cb_add_product(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("📝 Введите название нового товара:")
    await state.set_state(AdminStates.waiting_for_title)
    await call.answer()

@dp.message(AdminStates.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("💰 Теперь укажите цену товара в USD (например: 12.99):")
    await state.set_state(AdminStates.waiting_for_price)

@dp.message(AdminStates.waiting_for_price)
async def process_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(',', '.'))
        await state.update_data(price=price)
        await message.answer("🖼 Отправьте прямую ссылку на картинку товара.\nЕсли картинки нет, отправьте знак `-`")
        await state.set_state(AdminStates.waiting_for_img)
    except ValueError:
        await message.answer("❌ Ошибка! Введите числовое значение цены.")

@dp.message(AdminStates.waiting_for_img)
async def process_img(message: types.Message, state: FSMContext):
    img_url = message.text if message.text != '-' else ''
    data = await state.get_data()
    
    conn = get_db_connection()
    conn.execute("INSERT INTO products (title, price, img) VALUES (?, ?, ?)", (data['title'], data['price'], img_url))
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Товар *{data['title']}* (${data['price']}) успешно добавлен на витрину!", parse_mode="Markdown")
    await state.clear()

@dp.callback_query(F.data == "admin_del")
async def cb_delete_product(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("🆔 Введите ID товара для его удаления с витрины:")
    await state.set_state(AdminStates.waiting_for_delete_id)
    await call.answer()

@dp.message(AdminStates.waiting_for_delete_id)
async def process_delete(message: types.Message, state: FSMContext):
    try:
        prod_id = int(message.text)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM products WHERE id = ?", (prod_id,))
        conn.commit()
        affected = cur.rowcount
        conn.close()
        
        if affected > 0:
            await message.answer(f"💥 Товар с ID {prod_id} успешно удален.")
        else:
            await message.answer("⚠️ Товар с таким ID не найден в базе данных.")
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID.")

@dp.callback_query(F.data == "admin_list")
async def cb_list_products(call: types.CallbackQuery):
    conn = get_db_connection()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    
    if not products:
        await call.message.answer("🛍 На витрине пока нет товаров.")
    else:
        text = "📋 **Список товаров в магазине:**\n\n"
        for p in products:
            text += f"🔹 **ID:** {p['id']} | {p['title']} — `${p['price']}`\n"
        await call.message.answer(text, parse_mode="Markdown")
    await call.answer()

# --- API СЕРВЕРА ---
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
        # Если юзер зашёл сразу в WebApp без команды /start, регистрируем на лету
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
    
    print(f"🚀 Бот и сервер запущены на порту {port}")
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.run(main())
