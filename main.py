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

TOKEN = "8958743093:AAFKtxlPlX12S_D1sG7DVXyHj1qKrTjDVwA"

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

async def toggle_driver_status(user_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT is_active FROM drivers WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            new_status = 0 if row and row[0] == 1 else 1
        await conn.execute("UPDATE drivers SET is_active = ? WHERE user_id = ?", (new_status, user_id))
        await conn.commit()
        return new_status

async def save_driver(user_id: int, data: dict):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute('''
            INSERT OR REPLACE INTO drivers (user_id, first_name, last_name, car_model, car_number, tech_passport, phone, balance, is_active, rating, total_ratings)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 5.0, 0)
        ''', (user_id, data['first_name'], data['last_name'], data['car_model'], data['car_number'], data['tech_passport'], data['phone'], data['balance']))
        await conn.commit()

async def update_driver_balance(user_id: int, amount: int):
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("UPDATE drivers SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await conn.commit()

async def get_active_drivers_dict():
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id, first_name FROM drivers WHERE is_active = 1") as cursor:
            rows = await cursor.fetchall()
            return {r[0]: {"first_name": r[1]} for r in rows}

async def save_order_to_db(user_id: int, order_type: str, from_place: str, to_place: str, phone: str, details: str) -> int:
    async with aiosqlite.connect(DB_NAME) as conn:
        cursor = await conn.execute(
            "INSERT INTO orders (user_id, order_type, from_place, to_place, phone, details) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, order_type, from_place, to_place, phone, details)
        )
        order_id = cursor.lastrowid
        await conn.commit()
        return order_id

async def check_and_apply_referral_bonus(user_id: int):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT referrer_id, has_first_order FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] > 0 and row[1] == 0:
                referrer_id = row[0]
                await conn.execute("UPDATE users SET has_first_order = 1 WHERE user_id = ?", (user_id,))
                await conn.execute("UPDATE users SET balance_bonus = balance_bonus + ? WHERE user_id = ?", (REFERRAL_BONUS, referrer_id))
                await conn.commit()
                return referrer_id
    return None

async def get_referral_stats(user_id: int):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,)) as cursor:
            count = (await cursor.fetchone())[0]
        async with conn.execute("SELECT balance_bonus FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            bonus = row[0] if row else 0
        return count, bonus

async def get_total_stats():
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as c1:
            users_count = (await c1.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM drivers") as c2:
            drivers_count = (await c2.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM orders") as c3:
            orders_count = (await c3.fetchone())[0]
        return users_count, drivers_count, orders_count


# --- FSM СОСТОЯНИЯ ---

class OrderState(StatesGroup):
    waiting_for_from = State()
    waiting_for_to = State()
    waiting_for_class = State()
    waiting_for_options = State()
    waiting_for_phone = State()
    waiting_for_passengers = State()

class ParcelState(StatesGroup):
    waiting_for_from = State()
    waiting_for_to = State()
    waiting_for_weight = State()
    waiting_for_space = State()
    waiting_for_fragile = State()
    waiting_for_phone = State()

class DriverRegState(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_last_name = State()
    waiting_for_car_model = State()
    waiting_for_car_number = State()
    waiting_for_tech_passport = State()
    waiting_for_phone = State()

class BroadcastState(StatesGroup):
    waiting_for_text = State()

class PromoState(StatesGroup):
    waiting_for_code = State()

class AdminAuthState(StatesGroup):
    waiting_for_pin = State()

class SupportState(StatesGroup):
    waiting_for_message = State()

class BanState(StatesGroup):
    waiting_for_user_id = State()

class AdminReplyState(StatesGroup):
    waiting_for_reply_text = State()


# --- СЛОВАРЬ ПЕРЕВОДОВ ---

TEXTS = {
    "ru": {
        "welcome": "👋 Здравствуйте, {name}!\nДобро пожаловать в «Yo'ldosh Taxi» 🚖\n\nВыберите язык:",
        "main_menu": "🏠 Главное меню «Yo'ldosh Taxi»",
        "btn_order": "🚖 Заказать поездку",
        "btn_parcel": "📦 Отправить посылку",
        "btn_driver": "👨‍✈️ Кабинет водителя",
        "btn_menu": "⚙️ Дополнительно / Меню",
        "btn_ref": "👥 Рефералы и бонус",
        "btn_my_orders": "📋 Мои поездки",
        "btn_lang": "🌐 Сменить язык",
        "btn_rules": "📜 Правила сервиса",
        "btn_promo": "🎁 Ввести промокод",
        "btn_support": "🆘 Поддержка",
        "btn_back_main": "⬅️ На главную",
        "more_menu_text": "📂 Выберите нужный раздел в меню ниже:",
        "rules_text": "📜 Правила сервиса «Yo'ldosh Taxi»\n\n1. Платформа является информационным посредником.\n2. Ответственность за ПДД и безопасность несут водитель и пассажир.",
        "ref_text": "👥 Реферальная программа\n\n📊 Приглашено друзей: {ref_count}\n💰 Ваш накопленный бонус: {bonus:,} сумов\n\nВаша персональная ссылка:\n{link}\n\n🎁 +5,000 сумов за каждого друга после его первой поездки!",
        "my_orders_title": "📋 Ваши последние поездки:\n\n",
        "no_orders": "📋 У вас пока нет созданных заказов.",
        "status_accepted": "🟢 Принят водителем",
        "status_search": "🟡 В поиске водителя",
        "status_completed": "🏁 Завершен",
        "status_cancelled": "❌ Отменен",
        "ask_from": "📍 Шаг 1/6: Откуда отправляемся? Выберите город или введите вручную:",
        "ask_to": "🎯 Шаг 2/6: Куда направляетесь? Выберите город или введите вручную:",
        "ask_class": "🚗 Шаг 3/6: Выберите класс поездки:",
        "ask_options": "⚙️ Шаг 4/6: Выберите дополнительные опции:",
        "send_phone": "📱 Шаг 5/6: Отправьте номер кнопкой ниже или введите вручную:",
        "btn_send_phone": "📞 Отправить мой контакт",
        "passengers_count": "👥 Шаг 6/6: Выберите количество мест:",
        "order_success": "✅ Заказ зарегистрирован! Оповещаем водителей и канал.",
        "driver_menu": "👨‍✈️ Кабинет водителя\n\n💰 Баланс: {balance:,} сумов\n⭐ Рейтинг: {rating:.1f}\nСтатус: {status}",
        "btn_driver_reg": "📝 Регистрация водителя",
        "btn_driver_orders": "📋 Доступные заказы",
        "btn_topup_balance": "💳 Пополнить баланс",
        "btn_toggle_on": "🔴 В оффлайн (Отдых)",
        "btn_toggle_off": "🟢 В сеть (Работать)",
        "driver_not_registered": "⚠️ Вы не зарегистрированы как водитель!",
        "insufficient_balance": f"⚠️ Недостаточно средств! Нужно минимум {ORDER_COMMISSION:,} сумов.",
        "topup_info": "💳 <b>Пополнение баланса водителя</b>\n\nВыберите удобный способ пополнения:\n• Оплата через системы Click / Payme ниже.\n• Ручной перевод на карту: <code>{card}</code>\nПосле перевода отправьте чек админу: @abddumomin",
        "btn_back": "⬅️ Назад",
        "lang_changed": "✅ Выбран русский язык!",
        "cancelled": "❌ Действие отменено.",
        "btn_cancel": "❌ Отмена",
        "p_from": "📦 Доставка (Шаг 1/6): Откуда забрать посылку?",
        "p_to": "📦 Доставка (Шаг 2/6): Куда доставить посылку?",
        "p_weight": "📦 Шаг 3/6: Укажите примерный вес:",
        "p_space": "📦 Шаг 4/6: Сколько места займет?",
        "p_fragile": "⚠️ Шаг 5/6: Есть ли хрупкие вещи?",
        "p_phone": "📱 Шаг 6/6: Введите номер телефона или отправьте контакт:",
        "p_success": "✅ Заявка на посылку принята!",
        "rating_prompt": "⭐ Оцените поездку от 1 до 5 звезд:",
        "rating_thanks": "Спасибо за оценку! ⭐",
        "driver_reg_1": "👨‍✈️ Регистрация водителя\n\n1/6: Введите ваше Имя:",
        "driver_reg_2": "2/6: Введите вашу Фамилию:",
        "driver_reg_3": "3/6: Введите Марку и модель авто:",
        "driver_reg_4": "4/6: Введите Гос. номер автомобиля:",
        "driver_reg_5": "5/6: Введите Серию и номер Техпаспорта:",
        "driver_reg_6": "6/6: Отправьте номер телефона:",
        "driver_reg_success": "🎉 Регистрация завершена! Начислен бонус 10,000 сумов.",
        "choose_lang_prompt": "Выберите язык / Tilni tanlang / Choose language:",
        "phone_received": "✅ Контакт получен.",
        "phone_accepted": "✅ Номер принят.",
        "no_available_orders": "📋 Нет доступных новых заказов.",
        "order_accepted_driver": "✅ Вы успешно приняли заказ #{order_id}! Списана комиссия {commission:,} сум.",
        "trip_finished": "🏁 Поездка успешно завершена!",
        "support_prompt": "✍️ Опишите вашу проблему или вопрос, и служба поддержки ответит вам напрямую:",
        "support_success": "✅ Ваше сообщение отправлено в поддержку! Ожидайте ответа.",
        "promo_prompt": "🎁 Введите ваш промокод для получения бонуса:",
        "promo_invalid": "❌ Недействительный или закончившийся промокод.",
        "promo_success": "🎉 Промокод успешно активирован!\n💰 В ваш бонусный баланс зачислено: {amount:,} сум.",
        "order_not_found": "⚠️ Заказ не найден.",
        "order_already_processed": "⚠️ Заказ уже принят водителем или отменен!",
        "not_driver_alert": "⚠️ Вы не зарегистрированы как водитель!"
    },
    "uz": {
        "welcome": "👋 Assalomu alaykum, {name}!\n«Yo'ldosh Taxi» ga xush kelibsiz 🚖\n\nTilni tanlang:",
        "main_menu": "🏠 Asosiy menyu",
        "btn_order": "🚖 Safar buyurtma qilish",
        "btn_parcel": "📦 Posilka yuborish",
        "btn_driver": "👨‍✈️ Haydovchi kabineti",
        "btn_menu": "⚙️ Qo'shimcha / Menyu",
        "btn_ref": "👥 Takliflar va bonus",
        "btn_my_orders": "📋 Mening safarlarim",
        "btn_lang": "🌐 Tilni o'zgartirish",
        "btn_rules": "📜 Xizmat qoidalari",
        "btn_promo": "🎁 Promokodni kiritish",
        "btn_support": "🆘 Qo'llab-quvvatlash",
        "btn_back_main": "⬅️ Asosiy menyuga",
        "more_menu_text": "📂 Kerakli bo'limni tanlang:",
        "rules_text": "📜 «Yo'ldosh Taxi» xizmat qoidalari.\n\n1. Platforma axborot vositachisi hisoblanadi.\n2. Yo'l harakati qoidalari va xavfsizlik uchun haydovchi va yo'lovchi javobgardir.",
        "ref_text": "👥 Takliflar dasturi\n\n📊 Taklif qilingan do'stlar: {ref_count}\n💰 To'plangan bonus: {bonus:,} so'm\n\nSizning shaxsiy havolangiz:\n{link}\n\n🎁 Har bir do'st uchun birinchi safaridan keyin +5,000 so'm!",
        "my_orders_title": "📋 Oxirgi safarlaringiz:\n\n",
        "no_orders": "📋 Hozircha buyurtmalar yo'q.",
        "status_accepted": "🟢 Haydovchi qabul qildi",
        "status_search": "🟡 Haydovchi qidirilmoqda",
        "status_completed": "🏁 Yakunlangan",
        "status_cancelled": "❌ Bekor qilingan",
        "ask_from": "📍 1/6-qadam: Qayerdan jo'nab ketasiz? Shaharni tanlang yoki o'zingiz kiriting:",
        "ask_to": "🎯 2/6-qadam: Qayerga borasiz? Shaharni tanlang yoki o'zingiz kiriting:",
        "ask_class": "🚗 3/6-qadam: Safar sinfini tanlang:",
        "ask_options": "⚙️ 4/6-qadam: Qo'shimcha qulayliklarni tanlang:",
        "send_phone": "📱 5/6-qadam: Telefon raqamingizni pastdagi tugma orqali yoki yozib yuboring:",
        "btn_send_phone": "📞 Kontaktimni yuborish",
        "passengers_count": "👥 6/6-qadam: Joylar sonini tanlang:",
        "order_success": "✅ Buyurtma ro'yxatga olindi! Haydovchilar va kanalga xabar berilmoqda.",
        "driver_menu": "👨‍✈️ Haydovchi kabineti\n\n💰 Balans: {balance:,} so'm\n⭐ Reyting: {rating:.1f}\nHolat: {status}",
        "btn_driver_reg": "📝 Haydovchi sifatida ro'yxatdan o'tish",
        "btn_driver_orders": "📋 Mavjud buyurtmalar",
        "btn_topup_balance": "💳 Balansni to'ldirish",
        "btn_toggle_on": "🔴 Dam olish (Offlayn)",
        "btn_toggle_off": "🟢 Ishlash (Onlayn)",
        "driver_not_registered": "⚠️ Siz haydovchi sifatida ro'yxatdan o'tmagansiz!",
        "insufficient_balance": f"⚠️ Mablag' yetarli emas! Kamida {ORDER_COMMISSION:,} so'm kerak.",
        "topup_info": "💳 <b>Haydovchi balansini to'ldirish</b>\n\nQulay usulni tanlang:\n• Click / Payme tizimlari orqali to'lash.\n• Kartaga qo'lda o'tkazish: <code>{card}</code>\nO'tkazmadan so'ng chekni adminga yuboring: @abddumomin",
        "btn_back": "⬅️ Orqaga",
        "lang_changed": "✅ O'zbek tili tanlandi!",
        "cancelled": "❌ Amal bekor qilindi.",
        "btn_cancel": "❌ Bekor qilish",
        "p_from": "📦 Yetkazib berish (1/6): Posilka qayerdan olinadi?",
        "p_to": "📦 Yetkazib berish (2/6): Posilka qayerga yetkaziladi?",
        "p_weight": "📦 3/6: Taxminiy vaznni ko'rsating:",
        "p_space": "📦 4/6: Qancha joy egallaydi?",
        "p_fragile": "⚠️ 5/6: Mo'rt narsalar bormi?",
        "p_phone": "📱 6/6: Telefon raqamni kiriting yoki kontaktni yuboring:",
        "p_success": "✅ Posilka bo'yicha ariza qabul qilindi!",
        "rating_prompt": "⭐ Safarni 1 dan 5 gacha baholang:",
        "rating_thanks": "Bahoyingiz uchun rahmat! ⭐",
        "driver_reg_1": "👨‍✈️ Haydovchi ro'yxatdan o'tishi\n\n1/6: Ismingizni kiriting:",
        "driver_reg_2": "2/6: Familiyangizni kiriting:",
        "driver_reg_3": "3/6: Mashina markasi va modelini kiriting:",
        "driver_reg_4": "4/6: Mashina davlat raqamini kiriting:",
        "driver_reg_5": "5/6: Texpasport seriyasi va raqamini kiriting:",
        "driver_reg_6": "6/6: Telefon raqamingizni yuboring:",
        "driver_reg_success": "🎉 Ro'yxatdan o'tish yakunlandi! 10,000 so'm bonus berildi.",
        "choose_lang_prompt": "Tilni tanlang / Выберите язык / Choose language:",
        "phone_received": "✅ Kontakt qabul qilindi.",
        "phone_accepted": "✅ Raqam qabul qilindi.",
        "no_available_orders": "📋 Hozircha yangi buyurtmalar yo'q.",
        "order_accepted_driver": "✅ Siz #{order_id}-buyurtmani qabul qildingiz! Komissiya {commission:,} so'm yechildi.",
        "trip_finished": "🏁 Safar muvaffaqiyatli yakunlandi!",
        "support_prompt": "✍️ Muammo yoki savolingizni yozib qoldiring, qo'llab-quvvatlash xizmati siz bilan bog'lanadi:",
        "support_success": "✅ Xabaringiz qo'llab-quvvatlash xizmatiga yuborildi! Javobni kuting.",
        "promo_prompt": "🎁 Bonus olish uchun promokodni kiriting:",
        "promo_invalid": "❌ Yaroqsiz yoki muddati tugagan promokod.",
        "promo_success": "🎉 Promokod faollashtirildi!\n💰 Bonus balansingizga qo'shildi: {amount:,} so'm.",
        "order_not_found": "⚠️ Buyurtma topilmadi.",
        "order_already_processed": "⚠️ Buyurtma allaqachon haydovchi tomonidan qabul qilingan yoki bekor qilingan!",
        "not_driver_alert": "⚠️ Siz haydovchi emassiz!"
    },
    "en": {
        "welcome": "👋 Hello, {name}!\nWelcome to «Yo'ldosh Taxi» 🚖\n\nChoose language:",
        "main_menu": "🏠 Main Menu",
        "btn_order": "🚖 Book a Trip",
        "btn_parcel": "📦 Send a Parcel",
        "btn_driver": "👨‍✈️ Driver Cabinet",
        "btn_menu": "⚙️ More / Menu",
        "btn_ref": "👥 Referrals & Bonus",
        "btn_my_orders": "📋 My Rides",
        "btn_lang": "🌐 Change Language",
        "btn_rules": "📜 Service Rules",
        "btn_promo": "🎁 Enter Promo Code",
        "btn_support": "🆘 Support",
        "btn_back_main": "⬅️ Main Menu",
        "more_menu_text": "📂 Choose an option below:",
        "rules_text": "📜 «Yo'ldosh Taxi» service rules.\n\n1. The platform acts as an information intermediary.\n2. Driver and passenger are responsible for road rules and safety.",
        "ref_text": "👥 Referral Program\n\n📊 Invited friends: {ref_count}\n💰 Accumulated bonus: {bonus:,} UZS\n\nYour personal link:\n{link}\n\n🎁 +5,000 UZS for each friend after their first trip!",
        "my_orders_title": "📋 Your recent rides:\n\n",
        "no_orders": "📋 You have no orders yet.",
        "status_accepted": "🟢 Accepted by driver",
        "status_search": "🟡 Searching for driver",
        "status_completed": "🏁 Completed",
        "status_cancelled": "❌ Cancelled",
        "ask_from": "📍 Step 1/6: Departing from? Choose city or type manually:",
        "ask_to": "🎯 Step 2/6: Heading to? Choose city or type manually:",
        "ask_class": "🚗 Step 3/6: Select trip class:",
        "ask_options": "⚙️ Step 4/6: Select additional options:",
        "send_phone": "📱 Step 5/6: Send contact via button below or type manually:",
        "btn_send_phone": "📞 Share my contact",
        "passengers_count": "👥 Step 6/6: Select number of seats:",
        "order_success": "✅ Order registered! Notifying drivers and channel.",
        "driver_menu": "👨‍✈️ Driver Cabinet\n\n💰 Balance: {balance:,} UZS\n⭐ Rating: {rating:.1f}\nStatus: {status}",
        "btn_driver_reg": "📝 Driver Registration",
        "btn_driver_orders": "📋 Available Orders",
        "btn_topup_balance": "💳 Top Up Balance",
        "btn_toggle_on": "🔴 Go Offline (Rest)",
        "btn_toggle_off": "🟢 Go Online (Work)",
        "driver_not_registered": "⚠️ You are not registered as a driver!",
        "insufficient_balance": f"⚠️ Insufficient balance! Minimum {ORDER_COMMISSION:,} UZS required.",
        "topup_info": "💳 <b>Driver Balance Top Up</b>\n\nChoose payment method:\n• Pay via Click / Payme systems below.\n• Manual transfer to card: <code>{card}</code>\nAfter transfer, send receipt to admin: @abddumomin",
        "btn_back": "⬅️ Back",
        "lang_changed": "✅ English language selected!",
        "cancelled": "❌ Action cancelled.",
        "btn_cancel": "❌ Cancel",
        "p_from": "📦 Delivery (Step 1/6): Where to pick up parcel?",
        "p_to": "📦 Delivery (Step 2/6): Where to deliver parcel?",
        "p_weight": "📦 Step 3/6: Specify approximate weight:",
        "p_space": "📦 Step 4/6: How much space will it take?",
        "p_fragile": "⚠️ Step 5/6: Are there fragile items?",
        "p_phone": "📱 Step 6/6: Enter phone number or share contact:",
        "p_success": "✅ Parcel request accepted!",
        "rating_prompt": "⭐ Rate your trip from 1 to 5 stars:",
        "rating_thanks": "Thank you for rating! ⭐",
        "driver_reg_1": "👨‍✈️ Driver Registration\n\n1/6: Enter your First Name:",
        "driver_reg_2": "2/6: Enter your Last Name:",
        "driver_reg_3": "3/6: Enter Car Brand and Model:",
        "driver_reg_4": "4/6: Enter License Plate:",
        "driver_reg_5": "5/6: Enter Tech Passport serial and number:",
        "driver_reg_6": "6/6: Send your phone number:",
        "driver_reg_success": "🎉 Registration completed! 10,000 UZS bonus awarded.",
        "choose_lang_prompt": "Choose language / Выберите язык / Tilni tanlang:",
        "phone_received": "✅ Contact received.",
        "phone_accepted": "✅ Number accepted.",
        "no_available_orders": "📋 No available new orders.",
        "order_accepted_driver": "✅ You successfully accepted order #{order_id}! Commission of {commission:,} UZS deducted.",
        "trip_finished": "🏁 Trip successfully completed!",
        "support_prompt": "✍️ Describe your problem or question, and support will answer you directly:",
        "support_success": "✅ Your message has been sent to support! Please wait for a reply.",
        "promo_prompt": "🎁 Enter your promo code to receive a bonus:",
        "promo_invalid": "❌ Invalid or expired promo code.",
        "promo_success": "🎉 Promo code successfully activated!\n💰 Added to your bonus balance: {amount:,} UZS.",
        "order_not_found": "⚠️ Order not found.",
        "order_already_processed": "⚠️ Order is already accepted by a driver or cancelled!",
        "not_driver_alert": "⚠️ You are not registered as a driver!"
    }
}


# --- УТИЛИТЫ И КЛАВИАТУРЫ ---

async def delete_last_prompt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    old_id = data.get("last_msg_id")
    if old_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=old_id)
        except Exception:
            pass
    try:
        await message.delete()
    except Exception:
        pass

async def send_step_msg(message: types.Message, state: FSMContext, text: str, reply_markup=None):
    await delete_last_prompt(message, state)
    msg = await message.answer(text, reply_markup=reply_markup)
    await state.update_data(last_msg_id=msg.message_id)
    return msg

async def get_lang(user_id: int) -> str:
    return await get_user_lang(user_id)

def get_cities_keyboard(lang="ru"):
    cities = {
        "ru": [("🏙 Ташкент", "city_Ташкент"), ("🕌 Самарканд", "city_Самарканд"),
               ("🏛 Бухара", "city_Бухара"), ("🏞 Фергана", "city_Фергана"),
               ("🏔 Андижан", "city_Андижан"), ("🌅 Наманган", "city_Наманган"),
               ("🏜 Карши", "city_Карши"), ("🌴 Термез", "city_Термез")],
        "uz": [("🏙 Toshkent", "city_Ташкент"), ("🕌 Samarqand", "city_Самарканд"),
               ("🏛 Buxoro", "city_Бухара"), ("🏞 Farg'ona", "city_Фергана"),
               ("🏔 Andijon", "city_Андижан"), ("🌅 Namangan", "city_Наманган"),
               ("🏜 Qarshi", "city_Карши"), ("🌴 Termiz", "city_Термез")],
        "en": [("🏙 Tashkent", "city_Ташкент"), ("🕌 Samarkand", "city_Samarkand"),
               ("🏛 Bukhara", "city_Бухара"), ("🏞 Fergana", "city_Fergana"),
               ("🏔 Andijan", "city_Андижан"), ("🌅 Namangan", "city_Наманган"),
               ("🏜 Karshi", "city_Карши"), ("🌴 Termez", "city_Термез")]
    }
    current_cities = cities.get(lang, cities["ru"])
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=current_cities[0][0], callback_data=current_cities[0][1]), InlineKeyboardButton(text=current_cities[1][0], callback_data=current_cities[1][1])],
            [InlineKeyboardButton(text=current_cities[2][0], callback_data=current_cities[2][1]), InlineKeyboardButton(text=current_cities[3][0], callback_data=current_cities[3][1])],
            [InlineKeyboardButton(text=current_cities[4][0], callback_data=current_cities[4][1]), InlineKeyboardButton(text=current_cities[5][0], callback_data=current_cities[5][1])],
            [InlineKeyboardButton(text=current_cities[6][0], callback_data=current_cities[6][1]), InlineKeyboardButton(text=current_cities[7][0], callback_data=current_cities[7][1])],
        ]
    )

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
    lang = await get_lang(user_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    buttons = [
        [KeyboardButton(text=t["btn_order"]), KeyboardButton(text=t["btn_parcel"])],
        [KeyboardButton(text=t["btn_driver"]), KeyboardButton(text=t["btn_menu"])],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

async def get_more_menu_keyboard(user_id: int):
    lang = await get_lang(user_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    buttons = [
        [KeyboardButton(text=t["btn_my_orders"]), KeyboardButton(text=t["btn_ref"])],
        [KeyboardButton(text=t["btn_promo"]), KeyboardButton(text=t["btn_support"])],
        [KeyboardButton(text=t["btn_lang"]), KeyboardButton(text=t["btn_rules"])],
        [KeyboardButton(text=t["btn_back_main"])],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_phone_keyboard(lang_code="ru"):
    t = TEXTS.get(lang_code, TEXTS["ru"])
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t["btn_send_phone"], request_contact=True)],
            [KeyboardButton(text=t["btn_cancel"])],
        ],
        resize_keyboard=True
    )

def get_car_class_keyboard(lang="ru"):
    ec = "🚘 Эконом" if lang=="ru" else ("🚘 Ekonom" if lang=="uz" else "🚘 Economy")
    co = "🚙 Комфорт" if lang=="ru" else ("🚙 Komfort" if lang=="uz" else "🚙 Comfort")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ec, callback_data="class_economy"), InlineKeyboardButton(text=co, callback_data="class_comfort")]
        ]
    )

def get_car_options_keyboard(lang="ru"):
    ac = "❄️ Кондиционер" if lang=="ru" else ("❄️ Konditsioner" if lang=="uz" else "❄️ AC")
    tr = "🎒 Багажник" if lang=="ru" else ("🎒 Yukxona" if lang=="uz" else "🎒 Trunk")
    no = "✅ Без опций" if lang=="ru" else ("✅ Qo'shimchalarsiz" if lang=="uz" else "✅ No options")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ac, callback_data="opt_ac"), InlineKeyboardButton(text=tr, callback_data="opt_trunk")],
            [InlineKeyboardButton(text=no, callback_data="opt_none")]
        ]
    )

def get_passengers_keyboard(lang="ru"):
    p1 = "1 место" if lang=="ru" else ("1 ta joy" if lang=="uz" else "1 seat")
    p2 = "2 места" if lang=="ru" else ("2 ta joy" if lang=="uz" else "2 seats")
    p3 = "3 места" if lang=="ru" else ("3 ta joy" if lang=="uz" else "3 seats")
    p4 = "4 места" if lang=="ru" else ("4 ta joy" if lang=="uz" else "4 seats")
    full = "🚕 Салон целиком" if lang=="ru" else ("🚕 To'liq salon" if lang=="uz" else "🚕 Whole car")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=p1, callback_data="pass_1"), InlineKeyboardButton(text=p2, callback_data="pass_2")],
            [InlineKeyboardButton(text=p3, callback_data="pass_3"), InlineKeyboardButton(text=p4, callback_data="pass_4")],
            [InlineKeyboardButton(text=full, callback_data="pass_full")],
        ]
    )

def get_parcel_weight_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 До 5 кг", callback_data="pw_5kg"), InlineKeyboardButton(text="📦 5 - 15 кг", callback_data="pw_15kg")],
            [InlineKeyboardButton(text="📦 15 - 30 кг", callback_data="pw_30kg"), InlineKeyboardButton(text="🧳 30+ кг", callback_data="pw_heavy")],
        ]
    )

def get_parcel_space_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💼 1 место", callback_data="ps_1place"), InlineKeyboardButton(text="🧳 2-3 сумки", callback_data="ps_2places")],
            [InlineKeyboardButton(text="🚗 Весь багажник", callback_data="ps_full_trunk")],
        ]
    )

def get_parcel_fragile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚠️ Хрупкое", callback_data="pf_yes"), InlineKeyboardButton(text="📦 Обычное", callback_data="pf_no")]
        ]
    )

async def get_driver_keyboard(user_id: int):
    lang = await get_lang(user_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    driver = await get_driver_info(user_id)
    toggle_text = t["btn_toggle_on"] if (driver and driver["is_active"] == 1) else t["btn_toggle_off"]
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_driver_reg"], callback_data="driver_reg")],
            [InlineKeyboardButton(text=t["btn_driver_orders"], callback_data="driver_orders")],
            [InlineKeyboardButton(text=toggle_text, callback_data="driver_toggle_status")],
            [InlineKeyboardButton(text=t["btn_topup_balance"], callback_data="driver_topup")],
        ]
    )

def get_topup_keyboard(user_id: int, amount: int = 20000, lang="ru"):
    click_url = f"https://my.click.uz/services/pay?service_id={CLICK_SERVICE_ID}&merchant_id={CLICK_MERCHANT_ID}&amount={amount}&transaction_param={user_id}"
    payme_url = f"https://checkout.payme.uz/{PAYME_MERCHANT_ID}"
    
    click_btn = "💳 Оплатить через Click" if lang=="ru" else ("💳 Click orqali to'lash" if lang=="uz" else "💳 Pay via Click")
    payme_btn = "🅿️ Оплатить через Payme" if lang=="ru" else ("🅿️ Payme orqali to'lash" if lang=="uz" else "🅿️ Pay via Payme")
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=click_btn, url=click_url)],
            [InlineKeyboardButton(text=payme_btn, url=payme_url)]
        ]
    )

def get_admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить статистику", callback_data="admin_refresh"),
                InlineKeyboardButton(text="📋 Список заказов", callback_data="admin_orders"),
            ],
            [
                InlineKeyboardButton(text="💬 Обращения в чат", callback_data="admin_support_list"),
                InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast"),
            ],
            [
                InlineKeyboardButton(text="🚫 Забанить пользователя", callback_data="admin_ban"),
            ]
        ]
    )

def get_rating_keyboard(order_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐ 1", callback_data=f"rate_{order_id}_1"),
                InlineKeyboardButton(text="⭐ 2", callback_data=f"rate_{order_id}_2"),
                InlineKeyboardButton(text="⭐ 3", callback_data=f"rate_{order_id}_3"),
                InlineKeyboardButton(text="⭐ 4", callback_data=f"rate_{order_id}_4"),
                InlineKeyboardButton(text="⭐ 5", callback_data=f"rate_{order_id}_5"),
            ]
        ]
    )


# --- ВЕБ-СЕРВЕР ДЛЯ УДЕРЖАНИЯ ПОРТА НА RENDER ---
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


# --- ОБРАБОТЧИКИ КОМАНД И АДМИНКИ ---

@dp.callback_query(F.data == "driver_topup")
async def topup_balance_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = await get_lang(user_id)
    
    text = """💳 <b>Быстрое пополнение баланса водителя</b>

🎯 <b>Прямая карта для моментального перевода:</b>
<code>5614683400216925</code>
👤 <b>Получатель:</b> Abdumomin abdurahmanov

💡 Нажмите на номер карты выше, чтобы скопировать его, произведите оплату, а затем отправьте чек администратору: @abddumomin

👇 Или выберите автоматическую оплату через системы ниже:"""
    
    await callback.message.answer(
        text, 
        reply_markup=get_topup_keyboard(user_id, lang=lang), 
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(Command("admin"))
async def admin_auth_cmd(message: types.Message, state: FSMContext):
    await state.set_state(AdminAuthState.waiting_for_pin)
    await message.answer("🔐 Введите PIN-код администратора для входа:")

@dp.message(AdminAuthState.waiting_for_pin)
async def admin_pin_check(message: types.Message, state: FSMContext):
    if message.text.strip() == ADMIN_PIN:
        await state.clear()
        async with aiosqlite.connect(DB_NAME) as conn:
            await conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (message.from_user.id,))
            await conn.commit()

        u_count, d_count, o_count = await get_total_stats()
        text = (
            f"👑 <b>Панель Администратора (Успешный вход)</b>\n\n"
            f"👥 Пользователей: {u_count}\n"
            f"👨‍✈️ Водителей: {d_count}\n"
            f"📦 Всего заказов: {o_count}"
        )
        await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")
    else:
        await state.clear()
        await message.answer("❌ Неверный PIN-код. Доступ запрещен.")

@dp.callback_query(F.data == "admin_refresh")
async def admin_refresh_cb(callback: types.CallbackQuery):
    u_count, d_count, o_count = await get_total_stats()
    text = (
        f"👑 <b>Панель Администратора (Обновлено)</b>\n\n"
        f"👥 Пользователей: {u_count}\n"
        f"👨‍✈️ Водителей: {d_count}\n"
        f"📦 Всего заказов: {o_count}"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_orders")
async def admin_orders_cb(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT id, order_type, from_place, to_place, status FROM orders ORDER BY id DESC LIMIT 10") as cursor:
            orders = await cursor.fetchall()
            
    if not orders:
        await callback.message.answer("📋 Заказов пока нет.")
        await callback.answer()
        return
        
    text = "📋 <b>Последние 10 заказов:</b>\n\n"
    for o in orders:
        text += f"🆔 #{o[0]} | {o[1]}\n📍 {o[2]} ➔ {o[3]}\n📌 Статус: {o[4]}\n-------------------\n"
        
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_support_list")
async def admin_support_list_cb(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT DISTINCT user_id, user_name FROM support_messages WHERE status = 'open' ORDER BY id DESC LIMIT 10") as cursor:
            tickets = await cursor.fetchall()
            
    if not tickets:
        await callback.message.answer("💬 Активных обращений в поддержку нет.")
        await callback.answer()
        return
        
    keyboard = []
    for t in tickets:
        u_id, u_name = t[0], t[1] or "Клиент"
        keyboard.append([InlineKeyboardButton(text=f"💬 Чат с {u_name} (ID: {u_id})", callback_data=f"admin_chat_{u_id}")])
    
    await callback.message.answer("💬 <b>Активные чаты с пользователями:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_chat_"))
async def admin_open_chat(callback: types.CallbackQuery):
    target_user_id = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_name, text, sender FROM support_messages WHERE user_id = ? ORDER BY id ASC LIMIT 10", (target_user_id,)) as cursor:
            messages = await cursor.fetchall()
            
    text = f"💬 <b>История переписки с пользователем (ID: {target_user_id}):</b>\n\n"
    for m in messages:
        sender_label = "👤 Клиент" if m[2] == 'user' else "👑 Вы (Админ)"
        text += f"<b>{sender_label}:</b> {m[1]}\n\n"
        
    reply_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✍️ Написать ответ", callback_data=f"admin_reply_to_{target_user_id}")]])
    await callback.message.answer(text, reply_markup=reply_btn, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_reply_to_"))
async def admin_reply_prompt(callback: types.CallbackQuery, state: FSMContext):
    target_user_id = int(callback.data.split("_")[3])
    await state.set_state(AdminReplyState.waiting_for_reply_text)
    await state.update_data(target_user_id=target_user_id)
    await callback.message.answer(f"✍️ Введите текст ответа для пользователя (ID: {target_user_id}):")
    await callback.answer()

@dp.message(AdminReplyState.waiting_for_reply_text)
async def admin_send_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    reply_text = message.text
    await state.clear()
    
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            "INSERT INTO support_messages (user_id, user_name, text, sender, status) VALUES (?, ?, ?, 'admin', 'open')",
            (target_user_id, "Админ", reply_text)
        )
        await conn.commit()
        
    try:
        await bot_instance.send_message(
            target_user_id,
            f"💬 <b>Сообщение от службы поддержки «Yo'ldosh Taxi»</b>:\n\n{reply_text}",
            parse_mode="HTML"
        )
        await message.answer("✅ Ответ успешно отправлен пользователю!")
    except Exception as e:
        await message.answer(f"⚠️ Ошибка при отправке пользователю: {e}")

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastState.waiting_for_text)
    await callback.message.answer("📢 Введите текст для рассылки всем пользователям бота:")
    await callback.answer()

@dp.message(BroadcastState.waiting_for_text)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    text = message.text
    await state.clear()
    
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
            
    success = 0
    for u in users:
        try:
            await bot_instance.send_message(u[0], f"📢 <b>Объявление сервиса:</b>\n\n{text}", parse_mode="HTML")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
            
    await message.answer(f"✅ Рассылка завершена!\n📨 Доставлено пользователей: {success}")

@dp.callback_query(F.data == "admin_ban")
async def admin_ban_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BanState.waiting_for_user_id)
    await callback.message.answer("🚫 Введите User ID пользователя для блокировки:")
    await callback.answer()

@dp.message(BanState.waiting_for_user_id)
async def admin_ban_process(message: types.Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await state.clear()
        await message.answer("❌ Ошибка: ID должен состоять только из цифр.")
        return
    u_id = int(message.text.strip())
    await state.clear()
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (u_id,))
        await conn.commit()
    await message.answer(f"✅ Пользователь с ID `{u_id}` заблокирован.")


# --- ПОДДЕРЖКА ---

@dp.message(F.text.in_(["🆘 Поддержка", "🆘 Qo'llab-quvvatlash", "🆘 Support"]))
async def support_start(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        return
    await state.set_state(SupportState.waiting_for_message)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["support_prompt"], reply_markup=ReplyKeyboardRemove())

@dp.message(SupportState.waiting_for_message)
async def support_send(message: types.Message, state: FSMContext):
    text = message.text
    user = message.from_user
    await state.clear()
    
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            "INSERT INTO support_messages (user_id, user_name, text, sender, status) VALUES (?, ?, ?, 'user', 'open')",
            (user.id, user.full_name, text)
        )
        await conn.commit()
        
        async with conn.execute("SELECT user_id FROM admins") as cursor:
            admins = await cursor.fetchall()

    lang = await get_lang(user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["support_success"], reply_markup=await get_main_keyboard(user.id))
    
    admin_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✍️ Ответить клиенту", callback_data=f"admin_reply_to_{user.id}")]])
    for admin in admins:
        try:
            await bot_instance.send_message(
                admin[0],
                f"📩 <b>Новое обращение в поддержку!</b>\n\n"
                f"👤 <b>Клиент:</b> {user.full_name} (ID: <code>{user.id}</code>)\n"
                f"💬 <b>Сообщение:</b> {text}",
                reply_markup=admin_btn,
                parse_mode="HTML"
            )
        except Exception:
            pass


# --- ДОП. МЕНЮ И КОМАНДЫ ---

@dp.message(F.text.in_(["⚙️ Дополнительно / Меню", "⚙️ Qo'shimcha / Menyu", "⚙️ More / Menu"]))
async def open_more_menu(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["more_menu_text"], reply_markup=await get_more_menu_keyboard(message.from_user.id))

@dp.message(F.text.in_(["⬅️ На главную", "⬅️ Asosiy menyuga", "⬅️ Main Menu"]))
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        return
    lang = await get_lang(user_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["main_menu"], reply_markup=await get_main_keyboard(user_id))

@dp.message(F.text.in_(["🎁 Ввести промокод", "🎁 Promokodni kiritish", "🎁 Enter Promo Code"]))
async def promo_start(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        return
    await state.set_state(PromoState.waiting_for_code)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["promo_prompt"], reply_markup=ReplyKeyboardRemove())

@dp.message(PromoState.waiting_for_code)
async def promo_receive(message: types.Message, state: FSMContext):
    try:
        await message.delete()
    except Exception:
        pass
    code = message.text.strip().upper()
    user_id = message.from_user.id
    await state.clear()
    
    lang = await get_lang(user_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT amount, uses FROM promocodes WHERE code = ?", (code,)) as cursor:
            row = await cursor.fetchone()
            
        if not row or row[1] <= 0:
            await message.answer(t["promo_invalid"], reply_markup=await get_main_keyboard(user_id))
            return
            
        amount = row[0]
        await conn.execute("UPDATE users SET balance_bonus = balance_bonus + ? WHERE user_id = ?", (amount, user_id))
        await conn.execute("UPDATE promocodes SET uses = uses - 1 WHERE code = ?", (code,))
        await conn.commit()
        
    await message.answer(t["promo_success"].format(amount=amount), reply_markup=await get_main_keyboard(user_id))

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        await message.answer("🚫 Вы заблокированы в системе сервиса.")
        return

    name = message.from_user.first_name
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != user_id:
            async with aiosqlite.connect(DB_NAME) as conn:
                async with conn.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
                    existing = await cursor.fetchone()
                    if not existing:
                        await conn.execute("INSERT OR IGNORE INTO users (user_id, referrer_id) VALUES (?, ?)", (user_id, ref_id))
                        await conn.commit()

    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await conn.commit()

    lang = await get_user_lang(user_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["welcome"].format(name=name), reply_markup=get_lang_keyboard())

@dp.callback_query(F.data.startswith("lang_"))
async def process_language_choice(callback: types.CallbackQuery):
    lang = callback.data.split("_")[1]
    user_id = callback.from_user.id
    await set_user_lang(user_id, lang)
    t = TEXTS.get(lang, TEXTS["ru"])
    await callback.message.answer(t["lang_changed"], reply_markup=await get_main_keyboard(user_id))
    await callback.answer()

@dp.message(F.text.in_(["🌐 Сменить язык", "🌐 Tilni o'zgartirish", "🌐 Change Language"]))
async def change_lang_cmd(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["choose_lang_prompt"], reply_markup=get_lang_keyboard())

@dp.message(F.text.in_(["📜 Правила сервиса", "📜 Xizmat qoidalari", "📜 Service Rules"]))
async def rules_cmd(message: types.Message):
    if await is_user_banned(message.from_user.id):
        return
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["rules_text"], reply_markup=await get_main_keyboard(message.from_user.id))

@dp.message(F.text.in_(["👥 Рефералы и бонус", "👥 Takliflar va bonus", "👥 Referrals & Bonus"]))
async def referral_cmd(message: types.Message):
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        return
    lang = await get_lang(user_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    count, bonus = await get_referral_stats(user_id)
    bot_info = await bot_instance.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    await message.answer(
        t["ref_text"].format(ref_count=count, bonus=bonus, link=ref_link),
        reply_markup=await get_main_keyboard(user_id),
        disable_web_page_preview=True
    )

@dp.message(F.text.in_(["📋 Мои поездки", "📋 Mening safarlarim", "📋 My Rides"]))
async def my_orders_cmd(message: types.Message):
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        return
    lang = await get_lang(user_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute(
            "SELECT id, order_type, from_place, to_place, status FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 5",
            (user_id,)
        ) as cursor:
            orders = await cursor.fetchall()
            
    if not orders:
        await message.answer(t["no_orders"], reply_markup=await get_main_keyboard(user_id))
        return
        
    text = t["my_orders_title"]
    for o in orders:
        status_text = t.get(f"status_{o[4]}", o[4])
        text += f"🆔 #{o[0]} | {o[1]}\n📍 {o[2]} ➔ {o[3]}\n📌 Статус: {status_text}\n-------------------\n"
        
    await message.answer(text, reply_markup=await get_main_keyboard(user_id))

@dp.message(F.text.in_(["❌ Отмена", "❌ Bekor qilish", "❌ Cancel"]))
async def cancel_action(message: types.Message, state: FSMContext):
    await delete_last_prompt(message, state)
    await state.clear()
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await message.answer(t["cancelled"], reply_markup=ReplyKeyboardRemove())
    await message.answer(t["main_menu"], reply_markup=await get_main_keyboard(message.from_user.id))


# --- ЗАКАЗ ПОЕЗДКИ ---

@dp.message(F.text.in_(["🚖 Заказать поездку", "🚖 Safar buyurtma qilish", "🚖 Book a Trip"]))
async def start_order(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    await state.clear()
    await state.set_state(OrderState.waiting_for_from)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t["btn_cancel"])]], resize_keyboard=True)
    temp = await message.answer("🔄...", reply_markup=cancel_kb)
    await asyncio.sleep(0.05)
    try:
        await temp.delete()
    except Exception:
        pass
    await send_step_msg(message, state, t["ask_from"], reply_markup=get_cities_keyboard(lang))

@dp.callback_query(F.data.startswith("city_"), OrderState.waiting_for_from)
async def process_city_from(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_")[1]
    await state.update_data(from_place=city)
    await state.set_state(OrderState.waiting_for_to)
    lang = await get_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    try:
        msg = await callback.message.edit_text(f"📍 {city}\n\n" + t["ask_to"], reply_markup=get_cities_keyboard(lang))
        await state.update_data(last_msg_id=msg.message_id)
    except Exception:
        await send_step_msg(callback.message, state, f"📍 {city}\n\n" + t["ask_to"], reply_markup=get_cities_keyboard(lang))
    await callback.answer()

@dp.message(OrderState.waiting_for_from)
async def process_city_from_text(message: types.Message, state: FSMContext):
    city = message.text
    await state.update_data(from_place=city)
    await state.set_state(OrderState.waiting_for_to)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await send_step_msg(message, state, t["ask_to"], reply_markup=get_cities_keyboard(lang))

@dp.callback_query(F.data.startswith("city_"), OrderState.waiting_for_to)
async def process_city_to(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_")[1]
    await state.update_data(to_place=city)
    await state.set_state(OrderState.waiting_for_class)
    lang = await get_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    try:
        msg = await callback.message.edit_text(t["ask_class"], reply_markup=get_car_class_keyboard(lang))
        await state.update_data(last_msg_id=msg.message_id)
    except Exception:
        await send_step_msg(callback.message, state, t["ask_class"], reply_markup=get_car_class_keyboard(lang))
    await callback.answer()

@dp.message(OrderState.waiting_for_to)
async def process_city_to_text(message: types.Message, state: FSMContext):
    city = message.text
    await state.update_data(to_place=city)
    await state.set_state(OrderState.waiting_for_class)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await send_step_msg(message, state, t["ask_class"], reply_markup=get_car_class_keyboard(lang))

@dp.callback_query(F.data.startswith("class_"), OrderState.waiting_for_class)
async def process_car_class(callback: types.CallbackQuery, state: FSMContext):
    c_class = "Эконом" if callback.data == "class_economy" else "Комфорт"
    await state.update_data(car_class=c_class)
    await state.set_state(OrderState.waiting_for_options)
    lang = await get_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    try:
        msg = await callback.message.edit_text(t["ask_options"], reply_markup=get_car_options_keyboard(lang))
        await state.update_data(last_msg_id=msg.message_id)
    except Exception:
        await send_step_msg(callback.message, state, t["ask_options"], reply_markup=get_car_options_keyboard(lang))
    await callback.answer()

@dp.callback_query(F.data.startswith("opt_"), OrderState.waiting_for_options)
async def process_car_options(callback: types.CallbackQuery, state: FSMContext):
    opt = callback.data.split("_")[1]
    await state.update_data(options=opt)
    await state.set_state(OrderState.waiting_for_phone)
    lang = await get_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    try:
        await callback.message.delete()
    except Exception:
        pass
    await send_step_msg(callback.message, state, t["send_phone"], reply_markup=get_phone_keyboard(lang))
    await callback.answer()

@dp.message(OrderState.waiting_for_phone, F.contact)
async def process_phone_contact(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(OrderState.waiting_for_passengers)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    try:
        await message.delete()
    except Exception:
        pass
    await send_step_msg(message, state, t["passengers_count"], reply_markup=get_passengers_keyboard(lang))

@dp.message(OrderState.waiting_for_phone)
async def process_phone_text(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(OrderState.waiting_for_passengers)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await send_step_msg(message, state, t["passengers_count"], reply_markup=get_passengers_keyboard(lang))

@dp.callback_query(F.data.startswith("pass_"), OrderState.waiting_for_passengers)
async def process_passengers_count(callback: types.CallbackQuery, state: FSMContext):
    pass_data = callback.data.split("_")[1]
    data = await state.get_data()
    client_id = callback.from_user.id
    client_name = callback.from_user.full_name
    client_username = callback.from_user.username
    
    price, dist = calculate_trip_price(data["from_place"], data["to_place"], data["car_class"], pass_data)
    details = f"Класс: {data['car_class']}, Мест: {pass_data}, Опции: {data['options']}, Расстояние: ~{dist} км, Сумма: {price:,} сум"
    
    order_id = await save_order_to_db(
        user_id=client_id,
        order_type="🚖 Поездка межгород",
        from_place=data["from_place"],
        to_place=data["to_place"],
        phone=data["phone"],
        details=details
    )
    
    await state.clear()
    lang = await get_lang(client_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    cancel_order_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отменить поиск", callback_data=f"cancel_order_{order_id}")]])
    await callback.message.answer(f"{t['order_success']}\n💰 {price:,}", reply_markup=cancel_order_btn)
    await callback.message.answer(t["main_menu"], reply_markup=await get_main_keyboard(client_id))
    
    contact_link = f"@{client_username}" if client_username else f"<a href='tg://user?id={client_id}'>Client</a>"

    drivers = await get_active_drivers_dict()
    for d_id in drivers:
        try:
            btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🟢 Принять заказ", callback_data=f"accept_order_{order_id}")]])
            await bot_instance.send_message(
                d_id, 
                f"🚨 <b>NEW ORDER #{order_id}</b> ⚡️\n\n"
                f"📍 <b>Route:</b> {data['from_place']} ➔ {data['to_place']}\n"
                f"👤 <b>Client:</b> {client_name} ({contact_link})\n"
                f"📝 <b>Details:</b> {details}\n"
                f"💰 <b>Commission:</b> {ORDER_COMMISSION:,} UZS", 
                reply_markup=btn, 
                parse_mode="HTML"
            )
        except Exception:
            pass

    if CHANNEL_ID:
        try:
            await bot_instance.send_message(
                CHANNEL_ID,
                f"🚨 <b>NEW ORDER #{order_id}</b>\n\n"
                f"📍 <b>Route:</b> {data['from_place']} ➔ {data['to_place']}\n"
                f"🚗 <b>Type:</b> Intercity ({data['car_class']})\n"
                f"💰 <b>Price:</b> {price:,} UZS\n\n"
                f"👉 Open @yoldosh_taxibot to accept!",
                parse_mode="HTML"
            )
        except Exception:
            pass

    await callback.answer()


# --- ДОСТАВКА ПОСЫЛКИ ---

@dp.message(F.text.in_(["📦 Отправить посылку", "📦 Posilka yuborish", "📦 Send a Parcel"]))
async def start_parcel(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        return
    try:
        await message.delete()
    except Exception:
        pass
    await state.clear()
    await state.set_state(ParcelState.waiting_for_from)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t["btn_cancel"])]], resize_keyboard=True)
    temp = await message.answer("🔄...", reply_markup=cancel_kb)
    await asyncio.sleep(0.05)
    try:
        await temp.delete()
    except Exception:
        pass
    await send_step_msg(message, state, t["p_from"], reply_markup=get_cities_keyboard(lang))

@dp.callback_query(F.data.startswith("city_"), ParcelState.waiting_for_from)
async def parcel_from_city(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_")[1]
    await state.update_data(from_place=city)
    await state.set_state(ParcelState.waiting_for_to)
    lang = await get_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    try:
        msg = await callback.message.edit_text(t["p_to"], reply_markup=get_cities_keyboard(lang))
        await state.update_data(last_msg_id=msg.message_id)
    except Exception:
        await send_step_msg(callback.message, state, t["p_to"], reply_markup=get_cities_keyboard(lang))
    await callback.answer()

@dp.message(ParcelState.waiting_for_from)
async def parcel_from_text(message: types.Message, state: FSMContext):
    await state.update_data(from_place=message.text)
    await state.set_state(ParcelState.waiting_for_to)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await send_step_msg(message, state, t["p_to"], reply_markup=get_cities_keyboard(lang))

@dp.callback_query(F.data.startswith("city_"), ParcelState.waiting_for_to)
async def parcel_to_city(callback: types.CallbackQuery, state: FSMContext):
    city = callback.data.split("_")[1]
    await state.update_data(to_place=city)
    await state.set_state(ParcelState.waiting_for_weight)
    lang = await get_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    try:
        msg = await callback.message.edit_text(t["p_weight"], reply_markup=get_parcel_weight_keyboard())
        await state.update_data(last_msg_id=msg.message_id)
    except Exception:
        await send_step_msg(callback.message, state, t["p_weight"], reply_markup=get_parcel_weight_keyboard())
    await callback.answer()

@dp.message(ParcelState.waiting_for_to)
async def parcel_to_text(message: types.Message, state: FSMContext):
    await state.update_data(to_place=message.text)
    await state.set_state(ParcelState.waiting_for_weight)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await send_step_msg(message, state, t["p_weight"], reply_markup=get_parcel_weight_keyboard())

@dp.callback_query(F.data.startswith("pw_"), ParcelState.waiting_for_weight)
async def parcel_weight(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(weight=callback.data.split("_")[1])
    await state.set_state(ParcelState.waiting_for_space)
    lang = await get_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    try:
        msg = await callback.message.edit_text(t["p_space"], reply_markup=get_parcel_space_keyboard())
        await state.update_data(last_msg_id=msg.message_id)
    except Exception:
        await send_step_msg(callback.message, state, t["p_space"], reply_markup=get_parcel_space_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("ps_"), ParcelState.waiting_for_space)
async def parcel_space(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(space=callback.data.split("_")[1])
    await state.set_state(ParcelState.waiting_for_fragile)
    lang = await get_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    try:
        msg = await callback.message.edit_text(t["p_fragile"], reply_markup=get_parcel_fragile_keyboard())
        await state.update_data(last_msg_id=msg.message_id)
    except Exception:
        await send_step_msg(callback.message, state, t["p_fragile"], reply_markup=get_parcel_fragile_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("pf_"), ParcelState.waiting_for_fragile)
async def parcel_fragile(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(fragile=callback.data.split("_")[1])
    await state.set_state(ParcelState.waiting_for_phone)
    lang = await get_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    try:
        await callback.message.delete()
    except Exception:
        pass
    await send_step_msg(callback.message, state, t["p_phone"], reply_markup=get_phone_keyboard(lang))
    await callback.answer()

@dp.message(ParcelState.waiting_for_phone, F.contact)
async def parcel_phone_contact(message: types.Message, state: FSMContext):
    data = await state.get_data()
    details = f"Parcel: weight {data['weight']}, space {data['space']}, fragile: {data['fragile']}"
    await save_order_to_db(message.from_user.id, "📦 Parcel", data['from_place'], data['to_place'], message.contact.phone_number, details)
    await state.clear()
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    try:
        await message.delete()
    except Exception:
        pass
    await delete_last_prompt(message, state)
    await message.answer(t["p_success"], reply_markup=await get_main_keyboard(message.from_user.id))

@dp.message(ParcelState.waiting_for_phone)
async def parcel_phone_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    details = f"Parcel: weight {data['weight']}, space {data['space']}, fragile: {data['fragile']}"
    await save_order_to_db(message.from_user.id, "📦 Parcel", data['from_place'], data['to_place'], message.text, details)
    await state.clear()
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await delete_last_prompt(message, state)
    await message.answer(t["p_success"], reply_markup=await get_main_keyboard(message.from_user.id))

@dp.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order_callback(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    lang = await get_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] != 'new':
                await callback.answer(t["order_already_processed"], show_alert=True)
                return
        await conn.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
        await conn.commit()
    await callback.message.edit_text("❌ Заказ успешно отменен." if lang=="ru" else "❌ Buyurtma bekor qilindi.")
    await callback.answer()


# --- КАБИНЕТ ВОДИТЕЛЯ ---

@dp.message(F.text.in_(["👨‍✈️ Кабинет водителя", "👨‍✈️ Haydovchi kabineti", "👨‍✈️ Driver Cabinet"]))
async def driver_cabinet(message: types.Message):
    user_id = message.from_user.id
    if await is_user_banned(user_id):
        return
    lang = await get_lang(user_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    driver = await get_driver_info(user_id)
    
    try:
        await message.delete()
    except Exception:
        pass

    if not driver:
        reg_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t["btn_driver_reg"], callback_data="driver_reg")]])
        await message.answer(t["driver_not_registered"], reply_markup=reg_btn)
        return
        
    status_str = "🟢 Online" if driver["is_active"] == 1 else "🔴 Offline"
    text = t["driver_menu"].format(balance=driver["balance"], rating=driver["rating"], status=status_str)
    await message.answer(text, reply_markup=await get_driver_keyboard(user_id))

@dp.callback_query(F.data == "driver_reg")
async def start_driver_reg(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(DriverRegState.waiting_for_first_name)
    lang = await get_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    try:
        await callback.message.delete()
    except Exception:
        pass
    await send_step_msg(callback.message, state, t["driver_reg_1"], reply_markup=ReplyKeyboardRemove())
    await callback.answer()

@dp.message(DriverRegState.waiting_for_first_name)
async def reg_first_name(message: types.Message, state: FSMContext):
    await state.update_data(first_name=message.text)
    await state.set_state(DriverRegState.waiting_for_last_name)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await send_step_msg(message, state, t["driver_reg_2"])

@dp.message(DriverRegState.waiting_for_last_name)
async def reg_last_name(message: types.Message, state: FSMContext):
    await state.update_data(last_name=message.text)
    await state.set_state(DriverRegState.waiting_for_car_model)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await send_step_msg(message, state, t["driver_reg_3"])

@dp.message(DriverRegState.waiting_for_car_model)
async def reg_car_model(message: types.Message, state: FSMContext):
    await state.update_data(car_model=message.text)
    await state.set_state(DriverRegState.waiting_for_car_number)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await send_step_msg(message, state, t["driver_reg_4"])

@dp.message(DriverRegState.waiting_for_car_number)
async def reg_car_number(message: types.Message, state: FSMContext):
    await state.update_data(car_number=message.text)
    await state.set_state(DriverRegState.waiting_for_tech_passport)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await send_step_msg(message, state, t["driver_reg_5"])

@dp.message(DriverRegState.waiting_for_tech_passport)
async def reg_tech_passport(message: types.Message, state: FSMContext):
    await state.update_data(tech_passport=message.text)
    await state.set_state(DriverRegState.waiting_for_phone)
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await send_step_msg(message, state, t["driver_reg_6"], reply_markup=get_phone_keyboard(lang))

@dp.message(DriverRegState.waiting_for_phone)
async def reg_finish(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    data = await state.get_data()
    driver_data = {**data, "phone": phone, "balance": 10000}
    await save_driver(message.from_user.id, driver_data)
    await state.clear()
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await delete_last_prompt(message, state)
    await message.answer(t["driver_reg_success"], reply_markup=await get_main_keyboard(message.from_user.id))

@dp.callback_query(F.data == "driver_toggle_status")
async def toggle_status_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    new_status = await toggle_driver_status(user_id)
    driver = await get_driver_info(user_id)
    lang = await get_lang(user_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    status_str = "🟢 Online" if new_status == 1 else "🔴 Offline"
    await callback.message.edit_text(t["driver_menu"].format(balance=driver["balance"], rating=driver["rating"], status=status_str), reply_markup=await get_driver_keyboard(user_id))
    await callback.answer()

@dp.callback_query(F.data == "driver_orders")
async def show_available_orders(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = await get_lang(user_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    driver = await get_driver_info(user_id)
    if not driver:
        await callback.answer(t["not_driver_alert"], show_alert=True)
        return
        
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT id, order_type, from_place, to_place, details FROM orders WHERE status = 'new' ORDER BY id DESC LIMIT 5") as cursor:
            orders = await cursor.fetchall()
            
    if not orders:
        await callback.message.answer(t["no_available_orders"])
        await callback.answer()
        return
        
    btn_text = "🟢 Принять" if lang=="ru" else ("🟢 Qabul qilish" if lang=="uz" else "🟢 Accept")
    for o in orders:
        text = f"📋 Order #{o[0]}\n🏷 Type: {o[1]}\n📍 Route: {o[2]} ➔ {o[3]}\n📝 {o[4]}\n💰 Commission: {ORDER_COMMISSION:,} UZS"
        btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn_text, callback_data=f"accept_order_{o[0]}")]])
        await callback.message.answer(text, reply_markup=btn)
    await callback.answer()

@dp.callback_query(F.data.startswith("accept_order_"))
async def accept_order_action(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    lang = await get_lang(driver_id)
    t = TEXTS.get(lang, TEXTS["ru"])
    driver = await get_driver_info(driver_id)
    
    if not driver:
        await callback.answer(t["not_driver_alert"], show_alert=True)
        return

    if driver["balance"] < ORDER_COMMISSION:
        await callback.answer(t["insufficient_balance"], show_alert=True)
        return
        
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT status, user_id FROM orders WHERE id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] != 'new':
                await callback.answer(t["order_already_processed"], show_alert=True)
                return
            client_id = row[1]
            
        await conn.execute("UPDATE orders SET status = 'accepted', driver_id = ? WHERE id = ?", (driver_id, order_id))
        await conn.commit()
        
    await update_driver_balance(driver_id, -ORDER_COMMISSION)
    await callback.message.answer(t["order_accepted_driver"].format(order_id=order_id, commission=ORDER_COMMISSION))
    
    driver_username = callback.from_user.username
    driver_contact = f"@{driver_username}" if driver_username else f"<a href='tg://user?id={driver_id}'>Driver</a>"

    try:
        c_lang = await get_lang(client_id)
        finish_btn_text = "🏁 Завершить" if c_lang=="ru" else ("🏁 Yakunlash" if c_lang=="uz" else "🏁 Finish")
        finish_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=finish_btn_text, callback_data=f"finish_order_{order_id}")]])
        await bot_instance.send_message(
            client_id, 
            f"🎉 <b>Your order #{order_id} has been accepted by a driver!</b>\n\n"
            f"👨‍✈️ <b>Driver:</b> {driver['first_name']} {driver['last_name']} ({driver_contact})\n"
            f"🚗 <b>Car:</b> {driver['car_model']} ({driver['car_number']})\n"
            f"📞 <b>Phone:</b> {driver['phone']}", 
            reply_markup=finish_btn,
            parse_mode="HTML"
        )
    except Exception:
        pass
    await callback.answer()

@dp.callback_query(F.data.startswith("finish_order_"))
async def finish_order_action(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    lang = await get_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute("UPDATE orders SET status = 'completed' WHERE id = ?", (order_id,))
        async with conn.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
            client_id = row[0] if row else None
        await conn.commit()
        
    if client_id:
        await check_and_apply_referral_bonus(client_id)
        client_lang = await get_lang(client_id)
        ct = TEXTS.get(client_lang, TEXTS["ru"])
        await bot_instance.send_message(client_id, ct["rating_prompt"], reply_markup=get_rating_keyboard(order_id))
        
    await callback.message.answer(t["trip_finished"])
    await callback.answer()

@dp.callback_query(F.data.startswith("rate_"))
async def process_rating(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    order_id, stars = int(parts[1]), int(parts[2])
    
    async with aiosqlite.connect(DB_NAME) as conn:
        async with conn.execute("SELECT driver_id FROM orders WHERE id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
            driver_id = row[0] if row else None
            
        if driver_id:
            async with conn.execute("SELECT rating, total_ratings FROM drivers WHERE user_id = ?", (driver_id,)) as cursor:
                d_row = await cursor.fetchone()
                if d_row:
                    old_rating, total = d_row[0], d_row[1]
                    new_total = total + 1
                    new_rating = ((old_rating * total) + stars) / new_total
                    await conn.execute("UPDATE drivers SET rating = ?, total_ratings = ? WHERE user_id = ?", (new_rating, new_total, driver_id))
                    await conn.commit()
                    
    lang = await get_lang(callback.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    await callback.message.edit_text(t["rating_thanks"])
    await callback.answer()


# --- ЗАПУСК БОТА И ВЕБ-СЕРВЕРА (В САМОМ НИЗУ) ---

bot_instance = None

async def main():
    global bot_instance
    bot_instance = Bot(token=TOKEN)
    
    await init_db()
    
    # Запускаем фоновый веб-сервер для удержания порта 8080 на Render
    await start_background_web_server()
    print("🌐 Фоновый веб-сервер успешно запущен на порту!")
    
    print("🚀 Бот «Yo'ldosh Taxi» успешно запущен!")
    await dp.start_polling(bot_instance)

if __name__ == "__main__":
    asyncio.run(main())