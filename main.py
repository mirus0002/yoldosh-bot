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

TOKEN = "AAFnQui2UUcMSNRNbPhiU-cp8vt5-SUF_KQ"

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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 5.0, 0)
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
    p1 = "1️⃣ 1 место" if lang=="ru" else ("1️⃣ 1 ta joy" if lang=="uz" else "1️⃣ 1 seat")
    p2 = "2️⃣ 2 места" if lang=="ru" else ("2️⃣ 2 ta joy" if lang=="uz" else "2️⃣ 2 seats")
    p3 = "3️⃣ 3 места" if lang=="ru" else ("3️⃣ 3 ta joy" if lang=="uz" else "3️⃣ 3 seats")
    p4 = "4️⃣ Полная машина" if lang=="ru" else ("4️⃣ To'liq mashina" if lang=="uz" else "4️⃣ Full car")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=p1, callback_data="pass_1"), InlineKeyboardButton(text=p2, callback_data="pass_2")],
            [InlineKeyboardButton(text=p3, callback_data="pass_3"), InlineKeyboardButton(text=p4, callback_data="pass_full")]
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


# --- ОСНОВНЫЕ ХЕНДЛЕРЫ И ЛОГИКА ЗАКАЗОВ/РЕГИСТРАЦИИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if await is_user_banned(message.from_user.id):
        return
    
    args = message.text.split()
    referrer_id = 0
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != message.from_user.id:
            referrer_id = ref_id

    async with aiosqlite.connect(DB_NAME) as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO users (user_id, referrer_id) VALUES (?, ?)",
            (message.from_user.id, referrer_id)
        )
        await conn.commit()

    lang = await get_user_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    await message.answer(
        t["welcome"].format(name=message.from_user.first_name),
        reply_markup=get_lang_keyboard()
    )

@dp.callback_query(F.data.startswith("lang_"))
async def process_language_choice(callback: types.CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    await set_user_lang(callback.from_user.id, lang)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    await callback.message.answer(
        t["lang_changed"],
        reply_markup=await get_main_keyboard(callback.from_user.id)
    )
    await callback.answer()


# --- ОБРАБОТКА ТЕЛЕФОНА (ЗАКАЗЫ И РЕГИСТРАЦИЯ ВОДИТЕЛЯ) ---

@dp.message(OrderState.waiting_for_phone, F.contact)
async def process_phone_contact_order(message: types.Message, state: FSMContext):
    phone_number = message.contact.phone_number
    await state.update_data(phone=phone_number)
    await state.set_state(OrderState.waiting_for_passengers)
    
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    remove_kb = ReplyKeyboardRemove()
    await message.answer(t["passengers_count"], reply_markup=remove_kb)
    await send_step_msg(message, state, t["passengers_count"], reply_markup=get_passengers_keyboard(lang))

@dp.message(OrderState.waiting_for_phone)
async def process_phone_text_order(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(OrderState.waiting_for_passengers)
    
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    remove_kb = ReplyKeyboardRemove()
    await message.answer(t["passengers_count"], reply_markup=remove_kb)
    await send_step_msg(message, state, t["passengers_count"], reply_markup=get_passengers_keyboard(lang))


# Регистрация водителя - шаг телефона
@dp.message(DriverRegState.waiting_for_phone, F.contact)
async def process_driver_phone_contact(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    data = await state.get_data()
    data['phone'] = phone
    data['balance'] = 10000  # Бонус при регистрации
    
    await save_driver(message.from_user.id, data)
    await state.clear()
    
    lang = await get_lang(message.from_user.id)
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
    
    lang = await get_lang(message.from_user.id)
    t = TEXTS.get(lang, TEXTS["ru"])
    
    await message.answer(t["driver_reg_success"], reply_markup=await get_main_keyboard(message.from_user.id))


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


# --- ЗАПУСК БОТА ---

bot_instance = None

async def main():
    global bot_instance
    bot_instance = Bot(token=TOKEN)
    
    await init_db()
    
    # 🌐 Фоном запускаем веб-сервер для Render
    asyncio.create_task(start_background_web_server())
    print("🌐 Фоновый веб-сервер успешно запущен!")
    
    # 🚀 Запускаем опрос бота (поллинг)
    print("🚀 Бот «Йолдош» успешно запущен и работает!")
    await dp.start_polling(bot_instance)

if __name__ == "__main__":
    asyncio.run(main())
