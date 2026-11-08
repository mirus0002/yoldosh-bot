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

# Твой реальный токен бота
TOKEN = "8958743093:AAF4WxbQsQl96sTheScyOrO_C8lftm0-mWQ"

SUPPORT_PHONE = "+998 91 773-51-52"
CARD_NUMBER = "4023060518850838 (MIRXAMIDJON MIRBADALOV)"
ADMIN_PIN = "2009mmmm"
VIP_PRICE = 50000  # Стоимость VIP-статуса в сумах
REFERRAL_BONUS = 5000  # Бонус за приглашенного друга

logging.basicConfig(level=logging.INFO)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

DB_NAME = "yoldosh_taxi.db"


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
                is_banned INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0
            )
        ''')
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
            await conn.execute("ALTER TABLE users ADD COLUMN is_vip INTEGER DEFAULT 0")
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
                price INTEGER DEFAULT 0,
                is_urgent INTEGER DEFAULT 0,
                status TEXT DEFAULT 'new',
                driver_id INTEGER DEFAULT 0
            )
        ''')
        try:
            await conn.execute("ALTER TABLE orders ADD COLUMN price INTEGER DEFAULT 0")
            await conn.execute("ALTER TABLE orders ADD COLUMN is_urgent INTEGER DEFAULT 0")
            await conn.execute("ALTER TABLE orders ADD COLUMN driver_id INTEGER DEFAULT 0")
        except Exception:
            pass

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS order_messages (
                order_id INTEGER,
                driver_id INTEGER,
                message_id INTEGER,
                PRIMARY KEY (order_id, driver_id)
            )
        ''')
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

async def save_order_to_db(user_id: int, order_type: str, from_place: str, to_place: str, phone: str, details: str, price: int, is_urgent: int) -> int:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            "INSERT INTO orders (user_id, order_type, from_place, to_place, phone, details, price, is_urgent, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new')",
            (user_id, order_type, from_place, to_place, phone, details, price, is_urgent)
        )
        order_id = cursor.lastrowid
        await conn.commit()
        return order_id


# --- FSM СОСТОЯНИЯ ---

class OrderState(StatesGroup):
    waiting_for_from = State()
    waiting_for_to = State()
    waiting_for_price = State()
    waiting_for_urgent = State()
    waiting_for_phone = State()
    waiting_for_passengers = State()

class ParcelState(StatesGroup):
    waiting_for_from = State()
    waiting_for_to = State()
    waiting_for_details = State()
    waiting_for_price = State()
    waiting_for_urgent = State()
    waiting_for_phone = State()

class DriverRegState(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_car_model = State()
    waiting_for_car_number = State()
    waiting_for_tech_passport = State()
    waiting_for_phone = State()

class AdminState(StatesGroup):
    waiting_for_pin = State()
    waiting_for_ban_user_id = State()
    waiting_for_vip_user_id = State()


# --- СЛОВАРЬ ПЕРЕВОДОВ ---

TEXTS = {
    "ru": {
        "welcome": "👋 Здравствуйте, {name}!\nДобро пожаловать в «Yo'ldosh Taxi» 🚖\n\nВыберите язык:",
        "main_menu": "🏠 Главное меню «Yo'ldosh Taxi»",
        "btn_order": "🚖 Заказать поездку",
        "btn_parcel": "📦 Отправить посылку",
        "btn_driver": "👨‍✈️ Кабинет водителя",
        "btn_menu": "⚙️ Дополнительно / Меню",
        "ask_from": "📍 Шаг отбытия: Выберите город или введите вручную:",
        "ask_to": "🎯 Шаг назначения: Куда направляетесь?",
        "ask_price": "💰 Укажите сумму оплаты за поездку/посылку (в сумах, например: 50000):",
        "ask_urgent": "⚡ Это срочный (VIP) заказ?",
        "send_phone": "📱 Отправьте номер телефона или контакт:",
        "btn_send_phone": "📞 Отправить мой контакт",
        "passengers_count": "👥 Выберите количество мест:",
        "order_success": "✅ Заказ успешно зарегистрирован! Оповещаем водителей.",
        "parcel_desc": "📦 Опишите посылку (что везем, вес, особенности):",
        "parcel_success": "✅ Посылка зарегистрирована! Водитель скоро с вами свяжется.",
        "driver_menu": "👨‍✈️ Кабинет водителя\n\n💰 Баланс: {balance:,} сумов\n⭐ Рейтинг: {rating:.1f}\nСтатус: {status}",
        "btn_driver_reg": "📝 Регистрация водителя",
        "btn_driver_orders": "📋 Существующие заказы",
        "btn_driver_topup": "💳 Пополнить баланс",
        "btn_toggle_on": "🔴 В оффлайн (Отдых)",
        "btn_toggle_off": "🟢 В сеть (Работать)",
        "driver_not_registered": "⚠️ Вы не зарегистрированы как водитель!",
        "lang_changed": "✅ Выбран русский язык!",
        "btn_cancel": "❌ Отмена",
        "action_cancelled": "❌ Действие отменено.",
        "driver_reg_1": "👨‍✈️ Регистрация водителя\n\n1/6: Введите ваше Имя:",
        "driver_reg_2": "2/6: Введите вашу Фамилию:",
        "driver_reg_3": "3/6: Введите Марку и модель авто:",
        "driver_reg_4": "4/6: Введите Гос. номер автомобиля:",
        "driver_reg_5": "5/6: Введите Серию и номер Техпаспорта:",
        "driver_reg_6": "6/6: Отправьте номер телефона:",
        "driver_reg_success": "🎉 Регистрация завершена! Начислен бонус 10,000 сумов.",
        "menu_text": "⚙️ Дополнительное меню:\nВыберите интересующий раздел:",
        "admin_enter_pin": "🔐 Введите PIN-код администратора:",
        "admin_wrong_pin": "❌ Неверный PIN-код!",
        "admin_panel": "🛠 Панель администратора:",
        "btn_admin_ban": "🚫 Забанить пользователя",
        "btn_admin_profiles": "👥 Личные профили пользователей",
        "btn_admin_vip": "👑 Управление VIP статусами",
        "ask_ban_user": "🆔 Введите Telegram ID пользователя для блокировки:",
        "ask_vip_user": "🆔 Введите Telegram ID пользователя для выдачи/снятия VIP:",
        "user_banned_success": "✅ Пользователь успешно заблокирован.",
        "vip_updated_success": "✅ Статус VIP для пользователя успешно изменен.",
        "no_users_found": "📭 База данных пользователей пуста."
    },
    "uz": {
        "welcome": "👋 Assalomu alaykum, {name}!\n«Yo'ldosh Taxi» ga xush kelibsiz 🚖\n\nTilni tanlang:",
        "main_menu": "🏠 Asosiy menyu",
        "btn_order": "🚖 Safar buyurtma qilish",
        "btn_parcel": "📦 Posilka yuborish",
        "btn_driver": "👨‍✈️ Haydovchi kabineti",
        "btn_menu": "⚙️ Qo'shimcha / Menyu",
        "ask_from": "📍 Jo'nash joyi: Shaharni tanlang yoki yozing:",
        "ask_to": "🎯 Borish manzili: Qayerga borasiz?",
        "ask_price": "💰 Safar narxini so'mda kiriting (masalan: 50000):",
        "ask_urgent": "⚡ Bu shoshilinch (VIP) buyurtmaami?",
        "send_phone": "📱 Telefon raqamni yuboring:",
        "btn_send_phone": "📞 Kontaktimni yuborish",
        "passengers_count": "👥 Joylar sonini tanlang:",
        "order_success": "✅ Buyurtma ro'yxatga olindi!",
        "parcel_desc": "📦 Posilka tavsifini kiriting:",
        "parcel_success": "✅ Posilka qabul qilindi!",
        "driver_menu": "👨‍✈️ Haydovchi kabineti\n\n💰 Balans: {balance:,} so'm\n⭐ Reyting: {rating:.1f}",
        "btn_driver_reg": "📝 Haydovchi sifatida ro'yxatdan o'tish",
        "btn_driver_orders": "📋 Mavjud buyurtmalar",
        "btn_driver_topup": "💳 Balansni to'ldirish",
        "driver_not_registered": "⚠️ Siz haydovchi emassiz!",
        "lang_changed": "✅ O'zbek tili tanlandi!",
        "btn_cancel": "❌ Bekor qilish",
        "action_cancelled": "❌ Amaliyot bekor qilindi.",
        "driver_reg_1": "1/6: Ismingizni kiriting:",
        "driver_reg_2": "2/6: Familiyangizni kiriting:",
        "driver_reg_3": "3/6: Mashina markasi:",
        "driver_reg_4": "4/6: Davlat raqami:",
        "driver_reg_5": "5/6: Texpasport:",
        "driver_reg_6": "6/6: Telefon raqam:",
        "driver_reg_success": "🎉 Ro'yxatdan o'tish yakunlandi!",
        "menu_text": "⚙️ Qo'shimcha menyu:\nBo'limni tanlang:",
        "admin_enter_pin": "🔐 Administrator PIN-kodini kiriting:",
        "admin_wrong_pin": "❌ Noto'g'ri PIN-kod!",
        "admin_panel": "🛠 Administrator paneli:",
        "btn_admin_ban": "🚫 Foydalanuvchini bloklash",
        "btn_admin_profiles": "👥 Foydalanuvchilar profillari",
        "btn_admin_vip": "👑 VIP statuslarini boshqarish",
        "ask_ban_user": "🆔 Bloklanishi kerak bo'lgan ID:",
        "ask_vip_user": "🆔 VIP berish/olish uchun foydalanuvchi ID:",
        "user_banned_success": "✅ Foydalanuvchi bloklandi.",
        "vip_updated_success": "✅ VIP status o'zgartirildi.",
        "no_users_found": "📭 Ma'lumot yo'q."
    },
    "en": {
        "welcome": "👋 Hello, {name}!\nWelcome to «Yo'ldosh Taxi» 🚖\n\nChoose language:",
        "main_menu": "🏠 Main Menu",
        "btn_order": "🚖 Book a Trip",
        "btn_parcel": "📦 Send a Parcel",
        "btn_driver": "👨‍✈️ Driver Cabinet",
        "btn_menu": "⚙️ More / Menu",
        "ask_from": "📍 Departing from?",
        "ask_to": "🎯 Heading to?",
        "ask_price": "💰 Enter trip price in UZS:",
        "ask_urgent": "⚡ Is this an urgent (VIP) order?",
        "send_phone": "📱 Send contact:",
        "btn_send_phone": "📞 Share contact",
        "passengers_count": "👥 Select seats:",
        "order_success": "✅ Order registered!",
        "parcel_desc": "📦 Describe the parcel:",
        "parcel_success": "✅ Parcel registered!",
        "driver_menu": "👨‍✈️ Driver Cabinet",
        "btn_driver_reg": "📝 Driver Registration",
        "btn_driver_orders": "📋 Existing Orders",
        "btn_driver_topup": "💳 Top up Balance",
        "driver_not_registered": "⚠️ Not a driver!",
        "lang_changed": "✅ English selected!",
        "btn_cancel": "❌ Cancel",
        "action_cancelled": "❌ Action cancelled.",
        "driver_reg_1": "1/6: First Name:",
        "driver_reg_2": "2/6: Last Name:",
        "driver_reg_3": "3/6: Car model:",
        "driver_reg_4": "4/6: License plate:",
        "driver_reg_5": "5/6: Tech passport:",
        "driver_reg_6": "6/6: Phone number:",
        "driver_reg_success": "🎉 Registration completed!",
        "menu_text": "⚙️ Additional menu:",
        "admin_enter_pin": "🔐 Enter admin PIN:",
        "admin_wrong_pin": "❌ Wrong PIN!",
        "admin_panel": "🛠 Admin panel:",
        "btn_admin_ban": "🚫 Ban user",
        "btn_admin_profiles": "👥 User profiles",
        "btn_admin_vip": "👑 Manage VIP statuses",
        "ask_ban_user": "🆔 Enter user ID to ban:",
        "ask_vip_user": "🆔 Enter user ID for VIP:",
        "user_banned_success": "✅ User banned.",
        "vip_updated_success": "✅ VIP status updated.",
        "no_users_found": "📭 No users found."
    }
}


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def get_user_contact_link(bot: Bot, user_id: int, fallback_name: str = "Пользователь") -> str:
    try:
        chat = await bot.get_chat(user_id)
        if chat.username:
            return f"@{chat.username}"
        else:
            return f"[{fallback_name}](tg://user?id={user_id})"
    except Exception:
        return f"[{fallback_name}](tg://user?id={user_id})"

async def is_user_vip(user_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT is_vip FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] == 1 if row else False


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

def get_urgent_keyboard(lang="ru"):
    if lang == 'uz':
        yes_btn, no_btn = "⚡ Ha (VIP / Shoshilinch)", "⚪ Yo'q (Odatiy)"
    elif lang == 'en':
        yes_btn, no_btn = "⚡ Yes (VIP / Urgent)", "⚪ No (Standard)"
    else:
        yes_btn, no_btn = "⚡ Да (Срочный / VIP)", "⚪ Нет (Обычный)"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=yes_btn, callback_data="urgent_1")],
            [InlineKeyboardButton(text=no_btn, callback_data="urgent_0")]
        ]
    )

def get_driver_cabinet_keyboard(lang="ru"):
    t = TEXTS.get(lang, TEXTS["ru"])
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_driver_orders"], callback_data="driver_orders")],
            [InlineKeyboardButton(text=t["btn_driver_topup"], callback_data="driver_topup")],
        ]
    )

def get_cancel_keyboard(lang="ru"):
    t = TEXTS.get(lang, TEXTS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t["btn_cancel"])]],
        resize_keyboard=True
    )


# --- РАССЫЛКА ЗАКАЗОВ ВОДИТЕЛЯМ ---

async def notify_drivers_about_order(bot: Bot, order_id: int, user_id: int, order_type: str, from_place: str, to_place: str, phone: str, details: str, price: int, is_urgent: int):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM drivers WHERE is_active = 1") as cursor:
            drivers = await cursor.fetchall()

        for (driver_id,) in drivers:
            d_lang = await get_user_lang(driver_id)
            urgent_badge = "⚡ [VIP СРОЧНЫЙ] " if is_urgent else ""
            commission = int(price * 0.20) if price > 0 else 0

            if order_type == "trip":
                if d_lang == 'uz':
                    text = f"{urgent_badge}🚖 **Yangi safar! (#{order_id})**\n📍 Qayerdan: {from_place}\n🎯 Qayerga: {to_place}\n👥 {details}\n💰 Narxi: {price:,} so'm (Komissiya 20%: {commission:,} so'm)\n📞 Tel: {phone}"
                    btn_text = "✅ Qabul qilish"
                elif d_lang == 'en':
                    text = f"{urgent_badge}🚖 **New Trip! (#{order_id})**\n📍 From: {from_place}\n🎯 To: {to_place}\n👥 {details}\n💰 Price: {price:,} UZS (20% fee: {commission:,})\n📞 Phone: {phone}"
                    btn_text = "✅ Accept"
                else:
                    text = f"{urgent_badge}🚖 **Новый заказ! (#{order_id})**\n📍 Откуда: {from_place}\n🎯 Куда: {to_place}\n👥 {details}\n💰 Цена: {price:,} сум (Комиссия 20%: {commission:,} сум)\n📞 Тел: {phone}"
                    btn_text = "✅ Принять заказ"
            else:
                if d_lang == 'uz':
                    text = f"{urgent_badge}📦 **Yangi posilka! (#{order_id})**\n📍 Qayerdan: {from_place}\n🎯 Qayerga: {to_place}\nℹ️ {details}\n💰 Narxi: {price:,} so'm (Komissiya 20%: {commission:,} so'm)\n📞 Tel: {phone}"
                    btn_text = "✅ Qabul qilish"
                elif d_lang == 'en':
                    text = f"{urgent_badge}📦 **New Parcel! (#{order_id})**\n📍 From: {from_place}\n🎯 To: {to_place}\nℹ️ {details}\n💰 Price: {price:,} UZS (20% fee: {commission:,})\n📞 Phone: {phone}"
                    btn_text = "✅ Accept"
                else:
                    text = f"{urgent_badge}📦 **Новая посылка! (#{order_id})**\n📍 Откуда: {from_place}\n🎯 Куда: {to_place}\nℹ️ {details}\n💰 Цена: {price:,} сум (Комиссия 20%: {commission:,} сум)\n📞 Тел: {phone}"
                    btn_text = "✅ Принять заказ"

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=btn_text, callback_data=f"accept_order_{order_id}")]
            ])

            try:
                msg = await bot.send_message(driver_id, text, reply_markup=kb, parse_mode="Markdown")
                await conn.execute(
                    "INSERT OR REPLACE INTO order_messages (order_id, driver_id, message_id) VALUES (?, ?, ?)",
                    (order_id, driver_id, msg.message_id)
                )
            except Exception as e:
                logging.error(f"Не удалось отправить уведомление водителю {driver_id}: {e}")
        await conn.commit()


# --- ОБЩИЕ ХЕНДЛЕРЫ И РЕФЕРАЛКА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if await is_user_banned(message.from_user.id):
        return
    
    args = message.text.split()
    referrer_id = 0
    if len(args) > 1:
        try:
            ref_id = int(args[1])
            if ref_id != message.from_user.id:
                referrer_id = ref_id
        except ValueError:
            pass

    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id, referrer_id FROM users WHERE user_id = ?", (message.from_user.id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                await conn.execute(
                    "INSERT INTO users (user_id, referrer_id, balance_bonus) VALUES (?, ?, ?)",
                    (message.from_user.id, referrer_id, REFERRAL_BONUS if referrer_id else 0)
                )
                if referrer_id:
                    await conn.execute("UPDATE users SET balance_bonus = balance_bonus + ? WHERE user_id = ?", (REFERRAL_BONUS, referrer_id))
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

@dp.message(F.text.in_({TEXTS["ru"]["btn_cancel"], TEXTS["uz"]["btn_cancel"], TEXTS["en"]["btn_cancel"]}))
async def cancel_any_state(message: types.Message, state: FSMContext):
    await state.clear()
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["action_cancelled"], reply_markup=await get_main_keyboard(message.from_user.id))


# --- АДМИН-ПАНЕЛЬ С СТАТИСТИКОЙ ---

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    await state.clear()
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await state.set_state(AdminState.waiting_for_pin)
    await message.answer(t["admin_enter_pin"], reply_markup=get_cancel_keyboard(lang))

@dp.message(AdminState.waiting_for_pin)
async def process_admin_pin(message: types.Message, state: FSMContext):
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    if message.text == ADMIN_PIN:
        await state.clear()
        
        # Подсчет статистики пользователей
        async with aiosqlite.connect(DB_NAME) as conn:
            async with conn.execute("SELECT COUNT(*) FROM users") as cur1:
                total_users = (await cur1.fetchone())[0]
            async with conn.execute("SELECT COUNT(*) FROM drivers") as cur2:
                total_drivers = (await cur2.fetchone())[0]
            
            total_clients = max(0, total_users - total_drivers)

        stats_text = (
            f"🛠 **Панель администратора**\n\n"
            f"📊 **Статистика пользователей:**\n"
            f"👥 Всего пользователей: **{total_users}**\n"
            f"👤 Пассажиров (клиентов): **{total_clients}**\n"
            f"👨‍✈️ Водителей: **{total_drivers}**"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_admin_ban"], callback_data="admin_ban_menu")],
            [InlineKeyboardButton(text=t["btn_admin_vip"], callback_data="admin_vip_menu")],
            [InlineKeyboardButton(text=t["btn_admin_profiles"], callback_data="admin_profiles_menu")]
        ])
        await message.answer(stats_text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message.answer(t["admin_wrong_pin"])

@dp.callback_query(F.data == "admin_ban_menu")
async def admin_ban_menu(callback: types.CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await state.set_state(AdminState.waiting_for_ban_user_id)
    await callback.message.answer(t["ask_ban_user"], reply_markup=get_cancel_keyboard(lang))
    await callback.answer()

@dp.message(AdminState.waiting_for_ban_user_id)
async def process_admin_ban_user(message: types.Message, state: FSMContext):
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    try:
        target_id = int(message.text.strip())
        async with aiosqlite.connect(DB_NAME) as conn:
            await conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target_id,))
            await conn.commit()
        await state.clear()
        await message.answer(t["user_banned_success"], reply_markup=await get_main_keyboard(message.from_user.id))
    except ValueError:
        await message.answer("⚠️ Введите корректный числовой Telegram ID:")

@dp.callback_query(F.data == "admin_vip_menu")
async def admin_vip_menu(callback: types.CallbackQuery, state: FSMContext):
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await state.set_state(AdminState.waiting_for_vip_user_id)
    await callback.message.answer(t["ask_vip_user"], reply_markup=get_cancel_keyboard(lang))
    await callback.answer()

@dp.message(AdminState.waiting_for_vip_user_id)
async def process_admin_vip_user(message: types.Message, state: FSMContext):
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    try:
        target_id = int(message.text.strip())
        async with aiosqlite.connect(DB_NAME) as conn:
            async with conn.execute("SELECT is_vip FROM users WHERE user_id = ?", (target_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    new_vip = 0 if row[0] == 1 else 1
                    await conn.execute("UPDATE users SET is_vip = ? WHERE user_id = ?", (new_vip, target_id))
                    await conn.commit()
                else:
                    new_vip = 1
                    await conn.execute("INSERT INTO users (user_id, is_vip) VALUES (?, 1)", (target_id,))
                    await conn.commit()
        await state.clear()
        await message.answer(f"{t['vip_updated_success']} (Новый статус VIP: {'Вкл' if new_vip else 'Выкл'})", reply_markup=await get_main_keyboard(message.from_user.id))
    except ValueError:
        await message.answer("⚠️ Введите корректный числовой Telegram ID:")

@dp.callback_query(F.data == "admin_profiles_menu")
async def admin_profiles_menu(callback: types.CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id, lang, balance_bonus, is_banned, is_vip FROM users LIMIT 20") as cursor:
            rows = await cursor.fetchall()
            if not rows:
                await callback.message.answer(t["no_users_found"])
            else:
                text = "👥 **Список пользователей (первые 20):**\n\n"
                for r in rows:
                    contact_link = await get_user_contact_link(callback.bot, r[0], fallback_name=f"User {r[0]}")
                    vip_badge = "👑 VIP" if r[4] else ""
                    text += f"🆔 ID: {contact_link} | Язык: `{r[1]}` | Бонус: {r[2]} | Бан: {r[3]} {vip_badge}\n"
                await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


# --- ДОПОЛНИТЕЛЬНОЕ МЕНЮ И ПРОФИЛЬ ---

@dp.message(F.text.in_({TEXTS["ru"]["btn_menu"], TEXTS["uz"]["btn_menu"], TEXTS["en"]["btn_menu"]}))
async def extra_menu_handler(message: types.Message, state: FSMContext):
    await state.clear()
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    if lang == 'uz':
        profile_btn_text = "👤 Mening profilim"
        vip_btn_text = "👑 VIP statusni sotib olish"
    elif lang == 'en':
        profile_btn_text = "👤 My Profile"
        vip_btn_text = "👑 Buy VIP Status"
    else:
        profile_btn_text = "👤 Мой профиль"
        vip_btn_text = "👑 Купить VIP статус"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=profile_btn_text, callback_data="menu_my_profile")],
        [InlineKeyboardButton(text=vip_btn_text, callback_data="menu_buy_vip")],
        [InlineKeyboardButton(text="🌐 Изменить язык / Tilni o'zgartirish", callback_data="menu_change_lang")],
        [InlineKeyboardButton(text="📞 Поддержка / Support", callback_data="menu_support")],
    ])
    await message.answer(t["menu_text"], reply_markup=kb)

@dp.callback_query(F.data == "menu_my_profile")
async def menu_my_profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = await get_user_lang(user_id)
    is_vip = await is_user_vip(user_id)
    driver = await get_driver_info(user_id)
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    channel_link = "https://t.me/Yoldosh_Taxi_Official"
    
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT balance_bonus FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            bonus = row[0] if row else 0

    vip_str = "👑 VIP Активен" if is_vip else ("❌ Нет" if lang != 'uz' else "❌ Yo'q")
    
    if lang == 'uz':
        text = f"👤 **Sizning profilingiz:**\n\n🆔 ID: `{user_id}`\n🌐 Til: `{lang}`\n👑 VIP status: {vip_str}\n💰 Bonus balans: {bonus:,} so'm\n\n📞 Murojat uchun: `{SUPPORT_PHONE}`\n📢 Rasmiy kanal: {channel_link}\n\n🔗 Referal havolangiz:\n`{ref_link}`"
        if driver:
            text += f"\n\n👨‍✈️ **Haydovchi ma'lumotlari:**\nIsm: {driver['first_name']} {driver['last_name']}\nMashina: {driver['car_model']} ({driver['car_number']})\nTel: {driver['phone']}\nBalans: {driver['balance']:,} so'm"
            btn_edit = "📝 Anketani tahrirlash"
        else:
            btn_edit = "📝 Haydovchi bo'lish"
        btn_delete = "❌ Profilni o'chirish"
    elif lang == 'en':
        text = f"👤 **Your Profile:**\n\n🆔 ID: `{user_id}`\n🌐 Language: `{lang}`\n👑 VIP Status: {vip_str}\n💰 Bonus: {bonus:,} UZS\n\n📞 Support contact: `{SUPPORT_PHONE}`\n📢 Official Channel: {channel_link}\n\n🔗 Referral link:\n`{ref_link}`"
        if driver:
            text += f"\n\n👨‍✈️ **Driver Info:**\nName: {driver['first_name']} {driver['last_name']}\nCar: {driver['car_model']} ({driver['car_number']})\nPhone: {driver['phone']}\nBalance: {driver['balance']:,}"
            btn_edit = "📝 Edit Profile"
        else:
            btn_edit = "📝 Become Driver"
        btn_delete = "❌ Delete Profile"
    else:
        text = f"👤 **Ваш профиль:**\n\n🆔 ID: `{user_id}`\n🌐 Язык: `{lang}`\n👑 VIP статус: {vip_str}\n💰 Бонусный баланс: {bonus:,} сум\n\n📞 Murojat uchun: `{SUPPORT_PHONE}`\n📢 Официальный канал: {channel_link}\n\n🔗 Ваша реферальная ссылка:\n`{ref_link}`"
        if driver:
            text += f"\n\n👨‍✈️ **Данные водителя:**\nИмя: {driver['first_name']} {driver['last_name']}\nМашина: {driver['car_model']} ({driver['car_number']})\nТел: {driver['phone']}\nБаланс: {driver['balance']:,} сум"
            btn_edit = "📝 Изменить анкету"
        else:
            btn_edit = "📝 Стать водителем"
        btn_delete = "❌ Удалить профиль"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_edit, callback_data="start_driver_reg")],
        [InlineKeyboardButton(text=btn_delete, callback_data="menu_delete_profile")]
    ])
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "menu_buy_vip")
async def menu_buy_vip(callback: types.CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    if lang == 'uz':
        text = f"👑 **VIP statusni sotib olish**\n\nNarxi: **{VIP_PRICE:,} so'm**\nKarta raqami: `{CARD_NUMBER}`\n\nTo'lovni amalga oshirgach, chekni qo'llab-quvvatlash xizmatiga yuboring."
    elif lang == 'en':
        text = f"👑 **Buy VIP Status**\n\nPrice: **{VIP_PRICE:,} UZS**\nCard: `{CARD_NUMBER}`\n\nSend receipt after payment."
    else:
        text = f"👑 **Покупка VIP статуса**\n\nСтоимость: **{VIP_PRICE:,} сум**\nРеквизиты для оплаты: `{CARD_NUMBER}`\n\nПосле оплаты отправьте чек в поддержку."
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "menu_delete_profile")
async def menu_delete_profile(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = await get_user_lang(user_id)
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await conn.execute("DELETE FROM drivers WHERE user_id = ?", (user_id,))
        await conn.commit()
    
    del_text = "🗑 Ваш профиль был удален. Для перезапуска нажмите /start." if lang != 'uz' else "🗑 Profilingiz o'chirildi. /start bosing."
    await callback.message.answer(del_text, reply_markup=ReplyKeyboardRemove())
    await callback.answer()

@dp.callback_query(F.data == "menu_change_lang")
async def menu_change_lang(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите язык / Tilni tanlang:", reply_markup=get_lang_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "menu_support")
async def menu_support(callback: types.CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    text = f"📞 Служба поддержки:\nТелефон: {SUPPORT_PHONE}" if lang == 'ru' else f"📞 Qo'llab-quvvatlash:\nTelefon: {SUPPORT_PHONE}"
    await callback.message.answer(text)
    await callback.answer()


# --- ЗАКАЗ ПОЕЗДКИ ---

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
    await callback.message.edit_text(f"📍 <b>{city}</b> ➡️\n\n{t['ask_to']}", reply_markup=get_cities_keyboard(lang), parse_mode="HTML")
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
    await state.set_state(OrderState.waiting_for_price)
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(t["ask_price"], reply_markup=get_cancel_keyboard(lang))
    await callback.answer()

@dp.message(OrderState.waiting_for_to)
async def process_to_text(message: types.Message, state: FSMContext):
    await state.update_data(to_place=message.text)
    await state.set_state(OrderState.waiting_for_price)
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["ask_price"], reply_markup=get_cancel_keyboard(lang))

@dp.message(OrderState.waiting_for_price)
async def process_order_price(message: types.Message, state: FSMContext):
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    try:
        price = int(message.text.strip())
        await state.update_data(price=price)
        
        # Проверяем, есть ли у пользователя VIP-статус для срочного заказа
        user_vip = await is_user_vip(message.from_user.id)
        if user_vip:
            await state.set_state(OrderState.waiting_for_urgent)
            await message.answer(t["ask_urgent"], reply_markup=get_urgent_keyboard(lang))
        else:
            # Если не VIP — автоматически ставим обычный заказ (is_urgent = 0) и пропускаем шаг
            await state.update_data(is_urgent=0)
            await state.set_state(OrderState.waiting_for_phone)
            await message.answer(t["send_phone"], reply_markup=get_phone_keyboard(lang))
    except ValueError:
        await message.answer("⚠️ Введите корректную сумму числом (например: 50000):")

@dp.callback_query(OrderState.waiting_for_urgent, F.data.startswith("urgent_"))
async def process_order_urgent(callback: types.CallbackQuery, state: FSMContext):
    # Дополнительная проверка на всякий случай
    user_vip = await is_user_vip(callback.from_user.id)
    is_urgent = int(callback.data.split("_")[1]) if user_vip else 0
    
    await state.update_data(is_urgent=is_urgent)
    await state.set_state(OrderState.waiting_for_phone)
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    try:
        await callback.message.delete()
    except Exception:
        pass
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
    
    from_p = data.get("from_place")
    to_p = data.get("to_place")
    phone = data.get("phone")
    price = data.get("price", 0)
    is_urgent = data.get("is_urgent", 0)
    details = f"Количество мест: {pass_val}"

    order_id = await save_order_to_db(
        user_id=callback.from_user.id,
        order_type="trip",
        from_place=from_p,
        to_place=to_p,
        phone=phone,
        details=details,
        price=price,
        is_urgent=is_urgent
    )
    
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(t["order_success"], reply_markup=await get_main_keyboard(callback.from_user.id))
    
    await notify_drivers_about_order(callback.bot, order_id, callback.from_user.id, "trip", from_p, to_p, phone, details, price, is_urgent)
    await callback.answer()


# --- ОТПРАВКА ПОСЫЛКИ ---

@dp.message(F.text.in_({TEXTS["ru"]["btn_parcel"], TEXTS["uz"]["btn_parcel"], TEXTS["en"]["btn_parcel"]}))
async def start_parcel(message: types.Message, state: FSMContext):
    await state.clear()
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await state.set_state(ParcelState.waiting_for_from)
    await message.answer(t["ask_from"], reply_markup=get_cities_keyboard(lang))

@dp.callback_query(ParcelState.waiting_for_from, F.data.startswith("city_"))
async def parcel_from_city(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_")[1]
    await state.update_data(from_place=city)
    await state.set_state(ParcelState.waiting_for_to)
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await callback.message.edit_text(f"📍 Откуда: <b>{city}</b>\n\n{t['ask_to']}", reply_markup=get_cities_keyboard(lang), parse_mode="HTML")
    await callback.answer()

@dp.message(ParcelState.waiting_for_from)
async def parcel_from_text(message: types.Message, state: FSMContext):
    await state.update_data(from_place=message.text)
    await state.set_state(ParcelState.waiting_for_to)
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["ask_to"], reply_markup=get_cities_keyboard(lang))

@dp.callback_query(ParcelState.waiting_for_to, F.data.startswith("city_"))
async def parcel_to_city(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_")[1]
    await state.update_data(to_place=city)
    await state.set_state(ParcelState.waiting_for_details)
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(t["parcel_desc"])
    await callback.answer()

@dp.message(ParcelState.waiting_for_to)
async def parcel_to_text(message: types.Message, state: FSMContext):
    await state.update_data(to_place=message.text)
    await state.set_state(ParcelState.waiting_for_details)
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["parcel_desc"])

@dp.message(ParcelState.waiting_for_details)
async def parcel_details(message: types.Message, state: FSMContext):
    await state.update_data(details=message.text)
    await state.set_state(ParcelState.waiting_for_price)
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["ask_price"], reply_markup=get_cancel_keyboard(lang))

@dp.message(ParcelState.waiting_for_price)
async def parcel_price(message: types.Message, state: FSMContext):
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    try:
        price = int(message.text.strip())
        await state.update_data(price=price)
        
        user_vip = await is_user_vip(message.from_user.id)
        if user_vip:
            await state.set_state(ParcelState.waiting_for_urgent)
            await message.answer(t["ask_urgent"], reply_markup=get_urgent_keyboard(lang))
        else:
            await state.update_data(is_urgent=0)
            await state.set_state(ParcelState.waiting_for_phone)
            await message.answer(t["send_phone"], reply_markup=get_phone_keyboard(lang))
    except ValueError:
        await message.answer("⚠️ Введите корректную сумму числом:")

@dp.callback_query(ParcelState.waiting_for_urgent, F.data.startswith("urgent_"))
async def parcel_urgent(callback: types.CallbackQuery, state: FSMContext):
    user_vip = await is_user_vip(callback.from_user.id)
    is_urgent = int(callback.data.split("_")[1]) if user_vip else 0

    await state.update_data(is_urgent=is_urgent)
    await state.set_state(ParcelState.waiting_for_phone)
    lang = await get_user_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(t["send_phone"], reply_markup=get_phone_keyboard(lang))
    await callback.answer()

@dp.message(ParcelState.waiting_for_phone, F.contact)
async def parcel_finish_contact(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    data = await state.get_data()
    from_p = data.get("from_place")
    to_p = data.get("to_place")
    price = data.get("price", 0)
    is_urgent = data.get("is_urgent", 0)
    details = f"Посылка: {data.get('details')}"

    order_id = await save_order_to_db(
        user_id=message.from_user.id, order_type="parcel",
        from_place=from_p, to_place=to_p,
        phone=phone, details=details, price=price, is_urgent=is_urgent
    )
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await state.clear()
    await message.answer(t["parcel_success"], reply_markup=await get_main_keyboard(message.from_user.id))
    
    await notify_drivers_about_order(message.bot, order_id, message.from_user.id, "parcel", from_p, to_p, phone, details, price, is_urgent)

@dp.message(ParcelState.waiting_for_phone)
async def parcel_finish_text(message: types.Message, state: FSMContext):
    phone = message.text
    data = await state.get_data()
    from_p = data.get("from_place")
    to_p = data.get("to_place")
    price = data.get("price", 0)
    is_urgent = data.get("is_urgent", 0)
    details = f"Посылка: {data.get('details')}"

    order_id = await save_order_to_db(
        user_id=message.from_user.id, order_type="parcel",
        from_place=from_p, to_place=to_p,
        phone=phone, details=details, price=price, is_urgent=is_urgent
    )
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await state.clear()
    await message.answer(t["parcel_success"], reply_markup=await get_main_keyboard(message.from_user.id))
    
    await notify_drivers_about_order(message.bot, order_id, message.from_user.id, "parcel", from_p, to_p, phone, details, price, is_urgent)


# --- КАБИНЕТ ВОДИТЕЛЯ И ПРИНЯТИЕ ЗАКАЗОВ ---

@dp.message(F.text.in_({TEXTS["ru"]["btn_driver"], TEXTS["uz"]["btn_driver"], TEXTS["en"]["btn_driver"]}))
async def driver_cabinet(message: types.Message, state: FSMContext):
    await state.clear()
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    driver = await get_driver_info(message.from_user.id)
    if not driver:
        reg_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t["btn_driver_reg"], callback_data="start_driver_reg")]])
        await message.answer(t["driver_not_registered"], reply_markup=reg_btn)
    else:
        status_text = t["btn_toggle_on"] if driver["is_active"] else t["btn_toggle_off"]
        await message.answer(
            t["driver_menu"].format(balance=driver["balance"], rating=driver["rating"], status=status_text),
            reply_markup=get_driver_cabinet_keyboard(lang)
        )

@dp.callback_query(F.data == "driver_orders")
async def driver_existing_orders(callback: types.CallbackQuery):
    d_lang = await get_user_lang(callback.from_user.id)
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT id, from_place, to_place, order_type, details, phone, user_id, price, is_urgent FROM orders WHERE status = 'new' ORDER BY is_urgent DESC LIMIT 10") as cursor:
            rows = await cursor.fetchall()
            if not rows:
                if d_lang == 'uz':
                    text = "📭 Hozircha faol buyurtmalar yo'q."
                elif d_lang == 'en':
                    text = "📭 No active orders right now."
                else:
                    text = "📭 Активных заказов нет."
                await callback.message.answer(text)
            else:
                for r in rows:
                    client_link = await get_user_contact_link(callback.bot, r[6], fallback_name="Клиент")
                    urgent_badge = "⚡ [VIP СРОЧНЫЙ] " if r[8] else ""
                    commission = int(r[7] * 0.20) if r[7] > 0 else 0

                    if d_lang == 'uz':
                        card_text = f"{urgent_badge}🚖 **Buyurtma #{r[0]} ({r[3]})**\n📍 Qayerdan: {r[1]}\n🎯 Qayerga: {r[2]}\nℹ️ {r[4]}\n💰 Narxi: {r[7]:,} so'm (20% komissiya: {commission:,} so'm)\n📞 Tel: {r[5]}\n👤 Mijoz: {client_link}"
                        btn_text = "✅ Buyurtmani qabul qilish"
                    elif d_lang == 'en':
                        card_text = f"{urgent_badge}🚖 **Order #{r[0]} ({r[3]})**\n📍 From: {r[1]}\n🎯 To: {r[2]}\nℹ️ {r[4]}\n💰 Price: {r[7]:,} UZS (20% fee: {commission:,})\n📞 Phone: {r[5]}\n👤 Client: {client_link}"
                        btn_text = "✅ Accept Order"
                    else:
                        card_text = f"{urgent_badge}🚖 **Заказ #{r[0]} ({r[3]})**\n📍 Откуда: {r[1]}\n🎯 Куда: {r[2]}\nℹ️ {r[4]}\n💰 Цена: {r[7]:,} сум (Комиссия 20%: {commission:,} сум)\n📞 Тел: {r[5]}\n👤 Клиент: {client_link}"
                        btn_text = "✅ Принять заказ"

                    kb = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=btn_text, callback_data=f"accept_order_{r[0]}")]
                    ])
                    await callback.message.answer(card_text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("accept_order_"))
async def accept_order_action(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    d_lang = await get_user_lang(driver_id)

    driver_info = await get_driver_info(driver_id)
    if not driver_info:
        await callback.answer("⚠️ Вы не зарегистрированы как водитель!", show_alert=True)
        return

    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id, status, price FROM orders WHERE id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                text = "⚠️ Заказ не найден или уже удален." if d_lang == 'ru' else "⚠️ Buyurtma topilmadi."
                await callback.answer(text, show_alert=True)
                return
            
            client_id, status, price = row[0], row[1], row[2]
            if status != 'new':
                text = "⚠️ Этот заказ уже кто-то принял!" if d_lang == 'ru' else "⚠️ Bu buyurtmani allaqachon boshqa haydovchi oldi!"
                await callback.answer(text, show_alert=True)
                try:
                    await callback.message.delete()
                except Exception:
                    pass
                return

            commission = int(price * 0.20) if price > 0 else 0
            if driver_info["balance"] < commission:
                low_bal_text = f"⚠️ Недостаточно средств на балансе! Для принятия заказа нужно списать комиссию 20% ({commission:,} сум)." if d_lang == 'ru' else f"⚠️ Balans yetarli emas! 20% komissiya uchun {commission:,} so'm kerak."
                await callback.answer(low_bal_text, show_alert=True)
                return

            new_balance = driver_info["balance"] - commission
            await conn.execute("UPDATE drivers SET balance = ? WHERE user_id = ?", (new_balance, driver_id))
            await conn.execute("UPDATE orders SET status = 'accepted', driver_id = ? WHERE id = ?", (driver_id, order_id))

            async with conn.execute("SELECT driver_id, message_id FROM order_messages WHERE order_id = ?", (order_id,)) as cur2:
                msg_rows = await cur2.fetchall()

            await conn.commit()

    car_str = f"{driver_info['car_model']} ({driver_info['car_number']})"
    driver_name = driver_info['first_name']
    driver_phone = driver_info['phone']
    driver_link = await get_user_contact_link(callback.bot, driver_id, fallback_name=driver_name)

    client_lang = await get_user_lang(client_id)
    if client_lang == 'uz':
        client_msg = f"🎉 Sizning #{order_id}-sonli buyurtmangizni haydovchi qabul qildi!\n\n👨‍✈️ Haydovchi: {driver_link}\n🚗 Mashina: {car_str}\n📞 Tel: {driver_phone}"
    elif client_lang == 'en':
        client_msg = f"🎉 Your order #{order_id} has been accepted by a driver!\n\n👨‍✈️ Driver: {driver_link}\n🚗 Car: {car_str}\n📞 Phone: {driver_phone}"
    else:
        client_msg = f"🎉 Ваш заказ #{order_id} принят водителем!\n\n👨‍✈️ Водитель: {driver_link}\n🚗 Машина: {car_str}\n📞 Телефон: {driver_phone}"

    try:
        await callback.bot.send_message(client_id, client_msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление клиенту {client_id}: {e}")

    if d_lang == 'uz':
        await callback.message.edit_text(f"✅ Siz #{order_id}-sonli buyurtmani qabul qildingiz. Balansingizdan 20% komissiya ({commission:,} so'm) yechildi.")
    elif d_lang == 'en':
        await callback.message.edit_text(f"✅ You accepted order #{order_id}. 20% commission ({commission:,} UZS) deducted.")
    else:
        await callback.message.edit_text(f"✅ Вы приняли заказ #{order_id}. С вашего баланса списана комиссия 20% ({commission:,} сум).")

    for (other_d_id, other_m_id) in msg_rows:
        if other_d_id != driver_id:
            try:
                removed_text = f"❌ Заказ #{order_id} уже принят другим водителем." if d_lang == 'ru' else f"❌ #{order_id}-sonli buyurtma boshqa haydovchi tomonidan olindi."
                await callback.bot.edit_message_text(removed_text, chat_id=other_d_id, message_id=other_m_id)
            except Exception:
                try:
                    await callback.bot.delete_message(chat_id=other_d_id, message_id=other_m_id)
                except Exception:
                    pass

    await callback.answer()

@dp.callback_query(F.data == "driver_topup")
async def driver_topup_balance(callback: types.CallbackQuery):
    lang = await get_user_lang(callback.from_user.id)
    if lang == 'uz':
        text = f"💳 Balansni to'ldirish uchun karta:\n`{CARD_NUMBER}`\n\nTo'lovdan so'ng administratorga yozing."
    elif lang == 'en':
        text = f"💳 Top up card details:\n`{CARD_NUMBER}`\n\nContact support after payment."
    else:
        text = f"💳 Реквизиты для пополнения баланса:\n`{CARD_NUMBER}`\n\nПосле оплаты отправьте чек в поддержку."
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

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
    phone = message.contact.phone_number
    data = await state.get_data()
    data['phone'] = phone
    data['balance'] = 10000
    await save_driver(message.from_user.id, data)
    await state.clear()
    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["driver_reg_success"], reply_markup=await get_main_keyboard(message.from_user.id))

@dp.message(DriverRegState.waiting_for_phone)
async def process_driver_phone_text(message: types.Message, state: FSMContext):
    phone = message.text
    data = await state.get_data()
    data['phone'] = phone
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
    print("🌐 Фоновый веб-сервер успешно запущен на порту!")

async def main():
    bot_instance = Bot(token=TOKEN)
    await init_db()
    await asyncio.gather(
        start_background_web_server(),
        dp.start_polling(bot_instance, drop_pending_updates=True)
    )

if __name__ == "__main__":
    print("🚀 Бот «Yo'ldosh Taxi» запускается...")
    asyncio.run(main())
