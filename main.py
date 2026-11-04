import os
import asyncio
import logging
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

TOKEN = "8958743093:AAEyLj7SQZAeikwQ5AMuNBrBETnkaZLsY8M"

SUPPORT_PHONE = "+998 91 773-51-52"
CARD_NUMBER = "5614683400216925 (Abdumomin abdurahmanov)"
ORDER_COMMISSION = 3000
REFERRAL_BONUS = 5000
ADMIN_PIN = "2009mmmm"

CHANNEL_ID = "@yoldosh_orders" 

CLICK_SERVICE_ID = "35583"
CLICK_MERCHANT_ID = "22517"
PAYME_MERCHANT_ID = "65a123b4c5d6e7f8a9b01234"

logging.basicConfig(level=logging.INFO)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

DB_NAME = "yoldosh_taxi.db"

CITY_DISTANCES = {
    ("Ташкент", "Самарканд"): 300, ("Samarkand", "Tashkent"): 300,
    ("Ташкент", "Бухара"): 570, ("Bukhara", "Tashkent"): 570,
    ("Ташкент", "Фергана"): 320, ("Fergana", "Tashkent"): 320,
    ("Ташкент", "Андижан"): 350, ("Andijan", "Tashkent"): 350,
    ("Ташкент", "Наманган"): 290, ("Namangan", "Tashkent"): 290,
    ("Ташкент", "Карши"): 450, ("Karshi", "Tashkent"): 450,
    ("Ташкент", "Термез"): 660, ("Termez", "Tashkent"): 660,
    ("Самарканд", "Бухара"): 270, ("Bukhara", "Samarkand"): 270,
    ("Самарканд", "Карши"): 160, ("Karshi", "Samarkand"): 160,
}

def calculate_trip_price(from_place: str, to_place: str, car_class: str, pass_count_str: str) -> tuple[int, int]:
    dist = CITY_DISTANCES.get((from_place, to_place), 250)
    price_per_km = 800 if car_class == "Эконом" else 1200
    base_full_car = dist * price_per_km
    
    if pass_count_str == "full":
        return base_full_car, dist
    else:
        try:
            seats = int(pass_count_str)
            seat_price = int((base_full_car / 4) * 1.1)
            return seat_price * seats, dist
        except ValueError:
            return base_full_car, dist


# --- БАЗА ДАННЫХ ---

async def init_db():
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                lang TEXT DEFAULT 'ru',
                referrer_id INTEGER DEFAULT 0,
                balance_bonus INTEGER DEFAULT 0,
                has_first_order INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0
            )
        ''')
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
        except Exception:
            pass

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS drivers (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                car_model TEXT,
                car_number TEXT,
                tech_passport TEXT,
                phone TEXT,
                balance INTEGER,
                is_active INTEGER DEFAULT 1,
                rating REAL DEFAULT 5.0,
                total_ratings INTEGER DEFAULT 0
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                order_type TEXT,
                from_place TEXT,
                to_place TEXT,
                phone TEXT,
                details TEXT,
                status TEXT DEFAULT 'new',
                driver_id INTEGER DEFAULT 0,
                rating INTEGER DEFAULT 0
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                amount INTEGER,
                uses INTEGER DEFAULT 1
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name TEXT,
                text TEXT,
                sender TEXT,
                status TEXT DEFAULT 'open'
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        ''')
        await conn.execute("INSERT OR IGNORE INTO promocodes (code, amount, uses) VALUES ('START2026', 10000, 100)")
        await conn.commit()

async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] == 1 if row else False

async def get_user_lang(user_id: int) -> str:
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)) as cursor:
            res = await cursor.fetchone()
            return res[0] if res else "ru"

async def set_user_lang(user_id: int, lang: str):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO users (user_id, lang) VALUES (?, COALESCE((SELECT lang FROM users WHERE user_id = ?), ?))",
            (user_id, user_id, lang)
        )
        await conn.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id))
        await conn.commit()

async def get_driver_info(user_id: int):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT first_name, last_name, car_model, car_number, tech_passport, phone, balance, is_active, rating, total_ratings FROM drivers WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "first_name": row[0], "last_name": row[1], "car_model": row[2],
                    "car_number": row[3], "tech_passport": row[4], "phone": row[5],
                    "balance": row[6], "is_active": row[7], "rating": row[8], "total_ratings": row[9]
                }
            return None

async def save_driver(user_id: int, data: dict):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute('''
            INSERT OR REPLACE INTO drivers (user_id, first_name, last_name, car_model, car_number, tech_passport, phone, balance, is_active, rating, total_ratings)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 5.0, 0)
        ''', (user_id, data['first_name'], data['last_name'], data['car_model'], data['car_number'], data['tech_passport'], data['phone'], data['balance']))
        await conn.commit()

async def save_order_to_db(user_id: int, order_type: str, from_place: str, to_place: str, phone: str, details: str) -> int:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            "INSERT INTO orders (user_id, order_type, from_place, to_place, phone, details) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, order_type, from_place, to_place, phone, details)
        )
        order_id = cursor.lastrowid
        await conn.commit()
        return order_id


# --- FSM СОСТОЯНИЯ ---

class OrderState(StatesGroup):
    waiting_for_from = State()
    waiting_for_to = State()
    waiting_for_class = State()
    waiting_for_options = State()
    waiting_for_phone = State()
    waiting_for_passengers = State()

class DriverRegState(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_car_model = State()
    waiting_for_car_number = State()
    waiting_for_tech_passport = State()
    waiting_for_phone = State()


# --- СЛОВАРЬ ПЕРЕВОДОВ ---

TEXTS = {
    "ru": {
        "welcome": "👋 Здравствуйте, {name}!\nДобро пожаловать в «Yo'ldosh Taxi» 🚖\n\nВыберите язык:",
        "main_menu": "🏠 Главное меню «Yo'ldosh Taxi»",
        "btn_order": "🚖 Заказать поездку",
        "btn_parcel": "📦 Отправить посылку",
        "btn_driver": "👨‍✈️ Кабинет водителя",
        "btn_menu": "⚙️ Дополнительно / Меню",
        "ask_from": "📍 Шаг 1/6: Откуда отправляемся? Выберите город или введите вручную:",
        "ask_to": "🎯 Шаг 2/6: Куда направляетесь? Выберите город или введите вручную:",
        "ask_class": "🚗 Шаг 3/6: Выберите класс поездки:",
        "ask_options": "⚙️ Шаг 4/6: Выберите дополнительные опции:",
        "send_phone": "📱 Шаг 5/6: Отправьте номер телефона или контакт:",
        "btn_send_phone": "📞 Отправить мой контакт",
        "passengers_count": "👥 Шаг 6/6: Выберите количество мест:",
        "order_success": "✅ Заказ успешно зарегистрирован! Оповещаем водителей.",
        "driver_menu": "👨‍✈️ Кабинет водителя\n\n💰 Баланс: {balance:,} сумов\n⭐ Рейтинг: {rating:.1f}\nСтатус: {status}",
        "btn_driver_reg": "📝 Регистрация водителя",
        "btn_toggle_on": "🔴 В оффлайн (Отдых)",
        "btn_toggle_off": "🟢 В сеть (Работать)",
        "driver_not_registered": "⚠️ Вы не зарегистрированы как водитель!",
        "lang_changed": "✅ Выбран русский язык!",
        "btn_cancel": "❌ Отмена",
        "driver_reg_1": "👨‍✈️ Регистрация водителя\n\n1/6: Введите ваше Имя:",
        "driver_reg_2": "2/6: Введите вашу Фамилию:",
        "driver_reg_3": "3/6: Введите Марку и модель авто:",
        "driver_reg_4": "4/6: Введите Гос. номер автомобиля:",
        "driver_reg_5": "5/6: Введите Серию и номер Техпаспорта:",
        "driver_reg_6": "6/6: Отправьте номер телефона:",
        "driver_reg_success": "🎉 Регистрация завершена! Начислен бонус 10,000 сумов.",
    },
    "uz": {
        "welcome": "👋 Assalomu alaykum, {name}!\n«Yo'ldosh Taxi» ga xush kelibsiz 🚖\n\nTilni tanlang:",
        "main_menu": "🏠 Asosiy menyu",
        "btn_order": "🚖 Safar buyurtma qilish",
        "btn_parcel": "📦 Posilka yuborish",
        "btn_driver": "👨‍✈️ Haydovchi kabineti",
        "btn_menu": "⚙️ Qo'shimcha / Menyu",
        "ask_from": "📍 1/6-qadam: Qayerdan jo'nab ketasiz?",
        "ask_to": "🎯 2/6-qadam: Qayerga borasiz?",
        "ask_class": "🚗 3/6-qadam: Safar sinfini tanlang:",
        "ask_options": "⚙️ 4/6-qadam: Qo'shimcha qulayliklar:",
        "send_phone": "📱 5/6-qadam: Telefon raqamni yuboring:",
        "btn_send_phone": "📞 Kontaktimni yuborish",
        "passengers_count": "👥 6/6-qadam: Joylar sonini tanlang:",
        "order_success": "✅ Buyurtma ro'yxatga olindi!",
        "driver_menu": "👨‍✈️ Haydovchi kabineti\n\n💰 Balans: {balance:,} so'm\n⭐ Reyting: {rating:.1f}",
        "btn_driver_reg": "📝 Haydovchi sifatida ro'yxatdan o'tish",
        "btn_toggle_on": "🔴 Dam olish",
        "btn_toggle_off": "🟢 Ishlash",
        "driver_not_registered": "⚠️ Siz haydovchi emassiz!",
        "lang_changed": "✅ O'zbek tili tanlandi!",
        "btn_cancel": "❌ Bekor qilish",
        "driver_reg_1": "1/6: Ismingizni kiriting:",
        "driver_reg_2": "2/6: Familiyangizni kiriting:",
        "driver_reg_3": "3/6: Mashina markasi:",
        "driver_reg_4": "4/6: Davlat raqami:",
        "driver_reg_5": "5/6: Texpasport:",
        "driver_reg_6": "6/6: Telefon raqam:",
        "driver_reg_success": "🎉 Ro'yxatdan o'tish yakunlandi!",
    },
    "en": {
        "welcome": "👋 Hello, {name}!\nWelcome to «Yo'ldosh Taxi» 🚖\n\nChoose language:",
        "main_menu": "🏠 Main Menu",
        "btn_order": "🚖 Book a Trip",
        "btn_parcel": "📦 Send a Parcel",
        "btn_driver": "👨‍✈️ Driver Cabinet",
        "btn_menu": "⚙️ More / Menu",
        "ask_from": "📍 Step 1/6: Departing from?",
        "ask_to": "🎯 Step 2/6: Heading to?",
        "ask_class": "🚗 Step 3/6: Select class:",
        "ask_options": "⚙️ Step 4/6: Select options:",
        "send_phone": "📱 Step 5/6: Send contact:",
        "btn_send_phone": "📞 Share contact",
        "passengers_count": "👥 Step 6/6: Select seats:",
        "order_success": "✅ Order registered!",
        "driver_menu": "👨‍✈️ Driver Cabinet",
        "btn_driver_reg": "📝 Driver Registration",
        "btn_toggle_on": "🔴 Go Offline",
        "btn_toggle_off": "🟢 Go Online",
        "driver_not_registered": "⚠️ Not a driver!",
        "lang_changed": "✅ English selected!",
        "btn_cancel": "❌ Cancel",
        "driver_reg_1": "1/6: First Name:",
        "driver_reg_2": "2/6: Last Name:",
        "driver_reg_3": "3/6: Car model:",
        "driver_reg_4": "4/6: License plate:",
        "driver_reg_5": "5/6: Tech passport:",
        "driver_reg_6": "6/6: Phone number:",
        "driver_reg_success": "🎉 Registration completed!",
    }
}


# --- КЛАВИАТУРЫ ---

def get_lang_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
                InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
            ]
        ]
    )

async def get_main_keyboard(user_id: int):
    lang = await get_user_lang(user_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t["btn_order"]), KeyboardButton(text=t["btn_parcel"])],
            [KeyboardButton(text=t["btn_driver"]), KeyboardButton(text=t["btn_menu"])],
        ],
        resize_keyboard=True
    )

def get_cities_keyboard(lang="ru"):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏙 Ташкент", callback_data="city_Ташкент"), InlineKeyboardButton(text="🕌 Самарканд", callback_data="city_Самарканд")],
            [InlineKeyboardButton(text="🏛 Бухара", callback_data="city_Бухара"), InlineKeyboardButton(text="🏞 Фергана", callback_data="city_Фергана")],
            [InlineKeyboardButton(text="🏔 Андижан", callback_data="city_Андижан"), InlineKeyboardButton(text="🌅 Наманган", callback_data="city_Наманган")],
        ]
    )

def get_car_class_keyboard(lang="ru"):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚘 Эконом", callback_data="class_Эконом"), InlineKeyboardButton(text="🚙 Комфорт", callback_data="class_Комфорт")]
        ]
    )

def get_car_options_keyboard(lang="ru"):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❄️ Кондиционер", callback_data="opt_Кондиционер"), InlineKeyboardButton(text="🎒 Багажник", callback_data="opt_Багажник")],
            [InlineKeyboardButton(text="✅ Без опций", callback_data="opt_Без опций")]
        ]
    )

def get_phone_keyboard(lang_code="ru"):
    t = TEXTS.get(lang_code, TEXTS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t["btn_send_phone"], request_contact=True)],
            [KeyboardButton(text=t["btn_cancel"])],
        ],
        resize_keyboard=True
    )

def get_passengers_keyboard(lang="ru"):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1️⃣ 1", callback_data="pass_1"), InlineKeyboardButton(text="2️⃣ 2", callback_data="pass_2")],
            [InlineKeyboardButton(text="3️⃣ 3", callback_data="pass_3"), InlineKeyboardButton(text="4️⃣ Full", callback_data="pass_full")]
        ]
    )


# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if await is_user_banned(message.from_user.id):
        return
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await conn.commit()
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["welcome"].format(name=message.from_user.first_name), reply_markup=get_lang_keyboard())

@dp.callback_query(F.data.startswith("lang_"))
async def process_language_choice(callback: types.CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    await set_user_lang(callback.from_user.id, lang)
    t = TEXTS.get(lang, TEXTS["ru"])
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(t["lang_changed"], reply_markup=await get_main_keyboard(callback.from_user.id))
    await callback.answer()


# --- ЛОГИКА ЗАКАЗА ПОЕЗДКИ ---

@dp.message(F.text.in_({TEXTS["ru"]["btn_order"], TEXTS["uz"]["btn_order"], TEXTS["en"]["btn_order"]}))
async def start_order(message: types.Message, state: FSMContext):
    await state.clear()
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await state.set_state(OrderState.waiting_for_from)
    await message.answer(t["ask_from"], reply_markup=get_cities_keyboard(lang))

@dp.callback_query(OrderState.waiting_for_from, F.data.startswith("city_"))
async def process_from_city(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_")[1]
    await state.update_data(from_place=city)
    await state.set_state(OrderState.waiting_for_to)
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await callback.message.edit_text(f"{t['ask_from']} <b>{city}</b>\n\n{t['ask_to']}", reply_markup=get_cities_keyboard(lang))
    await callback.answer()

@dp.message(OrderState.waiting_for_from)
async def process_from_text(message: types.Message, state: FSMContext):
    await state.update_data(from_place=message.text)
    await state.set_state(OrderState.waiting_for_to)
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["ask_to"], reply_markup=get_cities_keyboard(lang))

@dp.callback_query(OrderState.waiting_for_to, F.data.startswith("city_"))
async def process_to_city(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_")[1]
    await state.update_data(to_place=city)
    await state.set_state(OrderState.waiting_for_class)
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await callback.message.edit_text(t["ask_class"], reply_markup=get_car_class_keyboard(lang))
    await callback.answer()

@dp.message(OrderState.waiting_for_to)
async def process_to_text(message: types.Message, state: FSMContext):
    await state.update_data(to_place=message.text)
    await state.set_state(OrderState.waiting_for_class)
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["ask_class"], reply_markup=get_car_class_keyboard(lang))

@dp.callback_query(OrderState.waiting_for_class, F.data.startswith("class_"))
async def process_car_class(callback: types.CallbackQuery, state: FSMContext):
    car_class = callback.data.split("_")[1]
    await state.update_data(car_class=car_class)
    await state.set_state(OrderState.waiting_for_options)
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await callback.message.edit_text(t["ask_options"], reply_markup=get_car_options_keyboard(lang))
    await callback.answer()

@dp.callback_query(OrderState.waiting_for_options, F.data.startswith("opt_"))
async def process_car_options(callback: types.CallbackQuery, state: FSMContext):
    option = callback.data.split("_")[1]
    await state.update_data(options=option)
    await state.set_state(OrderState.waiting_for_phone)
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await callback.message.delete()
    await callback.message.answer(t["send_phone"], reply_markup=get_phone_keyboard(lang))
    await callback.answer()

@dp.message(OrderState.waiting_for_phone, F.contact)
async def process_phone_contact_order(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(OrderState.waiting_for_passengers)
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["passengers_count"], reply_markup=get_passengers_keyboard(lang))

@dp.message(OrderState.waiting_for_phone)
async def process_phone_text_order(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(OrderState.waiting_for_passengers)
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["passengers_count"], reply_markup=get_passengers_keyboard(lang))

@dp.callback_query(OrderState.waiting_for_passengers, F.data.startswith("pass_"))
async def process_passengers_count(callback: types.CallbackQuery, state: FSMContext):
    pass_val = callback.data.split("_")[1]
    data = await state.get_data()
    
    await save_order_to_db(
        user_id=callback.from_user.id,
        order_type="trip",
        from_place=data.get("from_place"),
        to_place=data.get("to_place"),
        phone=data.get("phone"),
        details=f"Класс: {data.get('car_class')}, Опции: {data.get('options')}, Мест: {pass_val}"
    )
    
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await state.clear()
    await callback.message.edit_text(t["order_success"])
    await callback.message.answer(t["main_menu"], reply_markup=await get_main_keyboard(callback.from_user.id))
    await callback.answer()


# --- КАБИНЕТ ВОДИТЕЛЯ ---

@dp.message(F.text.in_({TEXTS["ru"]["btn_driver"], TEXTS["uz"]["btn_driver"], TEXTS["en"]["btn_driver"]}))
async def driver_cabinet(message: types.Message, state: FSMContext):
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    driver = await get_driver_info(message.from_user.id)
    if not driver:
        reg_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t["btn_driver_reg"], callback_data="start_driver_reg")]])
        await message.answer(t["driver_not_registered"], reply_markup=reg_btn)
    else:
        status_text = t["btn_toggle_on"] if driver["is_active"] else t["btn_toggle_off"]
        await message.answer(t["driver_menu"].format(balance=driver["balance"], rating=driver["rating"], status=status_text))

@dp.callback_query(F.data == "start_driver_reg")
async def start_driver_registration(callback: types.CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await state.set_state(DriverRegState.waiting_for_first_name)
    await callback.message.answer(t["driver_reg_1"], reply_markup=ReplyKeyboardRemove())
    await callback.answer()

@dp.message(DriverRegState.waiting_for_first_name)
async def reg_driver_name(message: types.Message, state: FSMContext):
    await state.update_data(first_name=message.text)
    await state.set_state(DriverRegState.waiting_for_last_name)
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["driver_reg_2"])

@dp.message(DriverRegState.waiting_for_last_name)
async def reg_driver_lastname(message: types.Message, state: FSMContext):
    await state.update_data(last_name=message.text)
    await state.set_state(DriverRegState.waiting_for_car_model)
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["driver_reg_3"])

@dp.message(DriverRegState.waiting_for_car_model)
async def reg_driver_car(message: types.Message, state: FSMContext):
    await state.update_data(car_model=message.text)
    await state.set_state(DriverRegState.waiting_for_car_number)
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["driver_reg_4"])

@dp.message(DriverRegState.waiting_for_car_number)
async def reg_driver_num(message: types.Message, state: FSMContext):
    await state.update_data(car_number=message.text)
    await state.set_state(DriverRegState.waiting_for_tech_passport)
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["driver_reg_5"])

@dp.message(DriverRegState.waiting_for_tech_passport)
async def reg_driver_passport(message: types.Message, state: FSMContext):
    await state.update_data(tech_passport=message.text)
    await state.set_state(DriverRegState.waiting_for_phone)
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["driver_reg_6"], reply_markup=get_phone_keyboard(lang))

@dp.message(DriverRegState.waiting_for_phone, F.contact)
async def process_driver_phone_contact(message: types.Message, state: FSMContext):
    data = await state.get_data()
    data['phone'] = message.contact.phone_number
    data['balance'] = 10000
    await save_driver(message.from_user.id, data)
    await state.clear()
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["driver_reg_success"], reply_markup=await get_main_keyboard(message.from_user.id))

@dp.message(DriverRegState.waiting_for_phone)
async def process_driver_phone_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    data['phone'] = message.text
    data['balance'] = 10000
    await save_driver(message.from_user.id, data)
    await state.clear()
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["driver_reg_success"], reply_markup=await get_main_keyboard(message.from_user.id))


# --- ВЕБ-СЕРВЕР И ЗАПУСК ---

async def handle(request):
    return web.Response(text="Yoldosh Bot is running!")

async def start_background_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    bot = Bot(token=TOKEN)
    await init_db()
    asyncio.create_task(start_background_web_server())
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 Бот «Йолдош» успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
