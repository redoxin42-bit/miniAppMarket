import os
import asyncio
import uuid
import secrets
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, LabeledPrice, PreCheckoutQuery
from aiohttp import web
from database import get_db_connection

BOT_TOKEN = "8891333611:AAENpJP5do6p27_GbrHQFqe-0uu3yBhoMdo"
# Получи токен в @CryptoBot -> Create App и вставь сюда для работы криптовалюты
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "ТВОЙ_CRYPTO_BOT_TOKEN") 

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Создаем папку для картинок товаров, если её нет
os.makedirs("static", exist_ok=True)

class AdminStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_price = State()
    waiting_for_img = State()
    waiting_for_delete_id = State()

# --- ЛОГИКА СТАРТА ---
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
            (user_id, first_name, username, invited_by, datetime.now().isoformat())
        )
        conn.commit()
    conn.close()

    app_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'localhost')}/"
    if 'localhost' in app_url:
        app_url = "http://localhost:8080/" # Для локальных тестов

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Открыть Магазин", web_app=WebAppInfo(url=app_url))]
    ])
    await message.answer(f"Привет, {first_name}! Добро пожаловать.\nИспользуй кнопку ниже для входа в Mini App.", reply_markup=kb)

# --- АДМИНКА (ДОБАВЛЕНИЕ ЛЮБЫХ ФОТО И НАСТРОЙКА ЦЕН) ---
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
    await call.message.answer("📝 Введите название товара:")
    await state.set_state(AdminStates.waiting_for_title)
    await call.answer()

@dp.message(AdminStates.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("💰 Укажите цену товара (в Stars или USD, пишите просто числом, например: 50):")
    await state.set_state(AdminStates.waiting_for_price)

@dp.message(AdminStates.waiting_for_price)
async def process_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text.replace(',', '.'))
        await state.update_data(price=price)
        await message.answer("📸 Отправьте изображение товара (как картинку или файл). Если фото нет, отправьте `-`")
        await state.set_state(AdminStates.waiting_for_img)
    except ValueError:
        await message.answer("❌ Введите корректное число.")

@dp.message(AdminStates.waiting_for_img, F.photo | F.document | F.text)
async def process_img(message: types.Message, state: FSMContext):
    img_name = ""
    if message.photo:
        file_id = message.photo[-1].file_id
        file = await bot.get_file(file_id)
        img_name = f"static/{uuid.uuid4().hex}.jpg"
        await bot.download_file(file.file_path, img_name)
    elif message.document and message.document.mime_type.startswith("image/"):
        file_id = message.document.file_id
        file = await bot.get_file(file_id)
        img_name = f"static/{uuid.uuid4().hex}.jpg"
        await bot.download_file(file.file_path, img_name)
        
    data = await state.get_data()
    conn = get_db_connection()
    conn.execute("INSERT INTO products (title, price, img) VALUES (?, ?, ?)", (data['title'], data['price'], img_name))
    conn.commit()
    conn.close()
    
    await message.answer(f"✅ Товар *{data['title']}* успешно добавлен!", parse_mode="Markdown")
    await state.clear()

@dp.callback_query(F.data == "admin_del")
async def cb_delete_product(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("🆔 Введите ID товара для удаления:")
    await state.set_state(AdminStates.waiting_for_delete_id)
    await call.answer()

@dp.message(AdminStates.waiting_for_delete_id)
async def process_delete(message: types.Message, state: FSMContext):
    try:
        prod_id = int(message.text)
        conn = get_db_connection()
        conn.execute("DELETE FROM products WHERE id = ?", (prod_id,))
        conn.commit()
        conn.close()
        await message.answer(f"💥 Товар #{prod_id} удален.")
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите числовой ID.")

@dp.callback_query(F.data == "admin_list")
async def cb_list_products(call: types.CallbackQuery):
    conn = get_db_connection()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    if not products:
        await call.message.answer("Витрина пуста.")
    else:
        text = "📋 **Список товаров:**\n\n"
        for p in products:
            text += f"🆔 {p['id']} | {p['title']} — {p['price']}\n"
        await call.message.answer(text, parse_mode="Markdown")
    await call.answer()


# --- РЕАЛЬНАЯ ОПЛАТА TELEGRAM STARS ---
@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    order_id = message.successful_payment.invoice_payload
    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    
    if order and order['status'] == 'pending':
        # Меняем статус заказа
        conn.execute("UPDATE orders SET status = 'completed' WHERE id = ?", (order_id,))
        
        # Реферальная система: проверяем, кто пригласил покупателя
        buyer = conn.execute("SELECT * FROM users WHERE id = ?", (order['user_id'],)).fetchone()
        if buyer and buyer['invited_by']:
            # Начисляем бонус за первую покупку пригласившему
            conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (order['total_amount'] * 0.1, buyer['invited_by']))
            
        conn.commit()
    conn.close()
    await message.answer("🎉 Спасибо! Ваша оплата через Telegram Stars успешно принята, бонусы реферальной системы распределены.")


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
        conn.execute("INSERT INTO users (id, first_name, username) VALUES (?, 'Покупатель', 'user')", (user_id,))
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        
    referrals = conn.execute("SELECT username, join_date FROM users WHERE invited_by = ?", (user_id,)).fetchall()
    orders = conn.execute("SELECT * FROM orders WHERE user_id = ? AND status='completed' ORDER BY id DESC", (user_id,)).fetchall()
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
    user_id = int(data.get("user_id"))
    total_amount = float(data.get("total_amount"))
    method = data.get("method")
    order_id = secrets.token_hex(8)
    
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO orders (id, user_id, total_amount, payment_method, timestamp) VALUES (?, ?, ?, ?, ?)",
        (order_id, user_id, total_amount, method, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    # Если выбраны Stars, шлем инвойс напрямую в чат пользователю
    if method == 'stars':
        try:
            asyncio.create_task(bot.send_invoice(
                chat_id=user_id,
                title="Оплата заказа CRYPTOXRM",
                description=f"Оплата корзины товаров в Mini App. ID: {order_id}",
                payload=order_id,
                currency="XTR", # Код валюты Telegram Stars
                prices=[LabeledPrice(label="Товары", amount=int(total_amount))]
            ))
        except Exception as e:
            print("Ошибка отправки инвойса:", e)
            
    # Если выбран CryptoBot — здесь создается счет через API (симулируем ссылку)
    elif method == 'cryptobot':
        pay_url = f"https://t.me/CryptoBot?start=invoice_mock_{order_id}"
        asyncio.create_task(bot.send_message(user_id, f"🔗 Ссылка на оплату через Crypto Bot:\n{pay_url}"))

    return web.json_response({"success": True})

async def init_app():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/api/products', api_get_products)
    app.router.add_get('/api/user/{user_id}', api_get_user)
    app.router.add_post('/api/order', api_create_order)
    # Позволяет фронтенду читать сохраненные картинки товаров из папки static
    app.router.add_static('/static/', path='static', name='static')
    return app

async def main():
    asyncio.create_task(dp.start_polling(bot))
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.run(main())
