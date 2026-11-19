#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================================================
Project: Yo'ldosh Taxi Telegram Bot (исправленная версия)
Stack:   Python 3.14, aiogram 3.x, aiosqlite, aiohttp

Переменные окружения (Render -> Environment):
    BOT_TOKEN              - токен бота (обязательно)
    ADMIN_PASSWORD         - пароль админ-панели (без него /admin отключён)
    ADMIN_ID               - Telegram ID администратора (по умолчанию 7543501900)
    COMMISSION_PERCENT     - процент комиссии с водителя за завершенный заказ (по умолчанию 20)
    MIN_BALANCE_TO_ACCEPT  - минимальный баланс для принятия заказов (по умолчанию 0)
    PORT                   - порт веб-сервера (Render задаёт сам)
=============================================================================
"""

import asyncio
import hmac
import html
import logging
import os
import re
import sys
from datetime import datetime
from typing import Optional, Set

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiohttp import web

# =====================================================================
# 1. КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
# =====================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("yoldosh_taxi_production.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("YoldoshTaxiProductionSystem")

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("ОШИБКА: Переменная окружения BOT_TOKEN не задана!")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7543501900"))
CHANNEL_USERNAME = "@Yoldosh_Taxi_Official"
PORT = int(os.getenv("PORT", 10000))
COMMISSION_PERCENT = float(os.getenv("COMMISSION_PERCENT", "20"))
MIN_BALANCE_TO_ACCEPT = float(os.getenv("MIN_BALANCE_TO_ACCEPT", "0"))
MIN_TOPUP = 5000

CARD_NUMBER = "4023060518850838"
CARD_HOLDER = "MIRXAMIDJON MIRBADALOV"
SUPPORT_PHONE = "+998 91 773-51-52"

if not ADMIN_PASSWORD:
    logger.warning("ADMIN_PASSWORD не задан — вход в админ-панель отключён.")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()

DB_NAME = "yoldosh_taxi_production.db"
LANG_BTN = "🌐 Сменить язык / Til / Language"


# =====================================================================
# 2. МНОГОЯЗЫЧНЫЕ СЛОВАРИ (RU, UZ, EN)  — разметка HTML
# =====================================================================

LANGS = {
    "ru": {
        "welcome": "🚖 Добро пожаловать в официальную систему заказа такси <b>Yo'ldosh Taxi</b>!",
        "choose_action": "Пожалуйста, выберите необходимое действие в меню:",
        "become_driver": "🚖 Стать водителем",
        "driver_activated": "✅ Режим водителя успешно активирован! Пройдите верификацию и пополните баланс.",
        "profile_title": "👤 <b>Ваш профиль в системе Yo'ldosh Taxi</b>",
        "balance_title": "💰 Баланс счета",
        "verified_status": "🛡 Статус верификации",
        "yes": "Да (Верифицирован) ✅",
        "no": "Нет (Не верифицирован) ❌",
        "order_taxi": "🚕 Заказать такси",
        "order_later": "🕒 Заказать на потом",
        "history": "📋 История поездок",
        "profile": "👤 Мой профиль",
        "topup": "💰 Пополнить баланс",
        "balance": "💳 Мой баланс",
        "verification": "📸 Верификация",
        "free_orders": "🚖 Свободные заказы",
        "how_to_use": "📖 Как пользоваться",
        "lang_changed": "🇷🇺 Язык успешно изменен на русский!",
        "sos_btn": "🚨 ТРЕВОГА (SOS)",
        "finish_trip_btn": "🏁 Завершить поездку",
        "delete_profile_btn": "❌ Удалить профиль",
        "how_to_use_text": (
            "📖 <b>Руководство пользователя Yo'ldosh Taxi</b>\n\n"
            "1️⃣ <b>Для пассажиров:</b>\n"
            "• Нажмите «🚕 Заказать такси» или «🕒 Заказать на потом».\n"
            "• Укажите точку отправления, пункт назначения и комментарий при необходимости.\n"
            "• Ожидайте, пока свободный водитель примет ваш заказ.\n\n"
            "2️⃣ <b>Для водителей:</b>\n"
            "• Нажмите «🚖 Стать водителем», пройдите верификацию (отправьте фото прав/паспорта) и пополните баланс.\n"
            "• В разделе «🚖 Свободные заказы» просматривайте и принимайте заявки.\n\n"
            "🚨 Во время поездки доступна кнопка экстренной связи <b>SOS</b>.\n"
            "📞 Служба поддержки: <b>+998 91 773-51-52</b>"
        ),
        "topup_instructions": (
            "💳 <b>Пополнение баланса водителя</b>\n\n"
            "Переведите необходимую сумму на банковскую карту:\n"
            "<code>{card}</code>\n"
            "Получатель: <b>{holder}</b>\n"
            "Телефон поддержки: <b>{phone}</b>\n\n"
            "📸 После совершения перевода отправьте скриншот или фото чека в этот чат."
        ),
        "topup_sent": "✅ Чек успешно отправлен администратору на проверку!",
        "verification_instructions": (
            "📸 <b>Верификация профиля водителя</b>\n\n"
            "Пожалуйста, отправьте в чат четкое фото ваших водительских прав или паспорта "
            "для прохождения проверки администрацией."
        ),
        "verification_sent": "✅ Фото документов отправлено администратору на проверку.",
        "reg_name": "📝 <b>Регистрация в системе</b>\n\nПожалуйста, введите ваши <b>Имя и Фамилию</b>:",
        "reg_age": "🔢 Укажите ваш <b>возраст</b> цифрами (например: <code>25</code>):",
        "reg_age_err": "⚠️ Пожалуйста, введите корректный возраст цифрами (например: 20):",
        "reg_phone": "📞 Теперь отправьте ваш <b>номер телефона</b>, нажав на кнопку ниже или написав его вручную:",
        "reg_phone_btn": "📱 Поделиться контактом",
        "reg_phone_err": "⚠️ Введите корректный номер телефона (например: +998 91 773-51-52):",
        "reg_done": "✅ <b>Регистрация успешно завершена!</b> Добро пожаловать в систему.",
        "role_driver": "Водитель 🚖",
        "role_passenger": "Пассажир 👤",
        "lbl_name": "Имя",
        "lbl_phone": "Телефон",
        "lbl_role": "Роль",
        "not_set": "Не указано",
        "currency": "сум",
        "balance_text": "💳 Ваш баланс: <b>{amount}</b>",
        "history_title": "📜 <b>История ваших последних поездок:</b>\n\n",
        "history_empty": "📭 У вас пока нет истории поездок.",
        "lbl_order": "Заказ",
        "lbl_status": "Статус",
        "lbl_from": "Откуда",
        "lbl_to": "Куда",
        "lbl_date": "Дата",
        "st_pending": "⏳ В поиске",
        "st_accepted": "🚗 Принят",
        "st_active": "🚕 В пути",
        "st_completed": "✅ Завершен",
        "st_cancelled": "❌ Отменен",
        "trip_done_driver": (
            "🏁 <b>Поездка #{id} завершена!</b>\n\n"
            "💵 Стоимость поездки: <b>{fare}</b>\n"
            "➖ Комиссия сервиса ({percent}%): <b>{fee}</b>\n"
            "💰 Ваш баланс: <b>{balance}</b>\n\n"
            "Спасибо за работу с Yo'ldosh Taxi."
        ),
        "ask_price": "💵 Введите <b>стоимость поездки</b> цифрами (например: <code>25000</code>).\nС вас будет списана комиссия сервиса — {percent}%.",
        "price_err": "⚠️ Введите стоимость поездки только цифрами (например: 25000):",
        "trip_done_passenger": "🏁 <b>Ваша поездка #{id} завершена!</b> Спасибо, что выбрали Yo'ldosh Taxi.",
        "no_active_trip": "⚠️ У вас сейчас нет активной поездки для завершения.",
        "sos_ask": "🚨 Кратко опишите, что случилось (одним сообщением). Оно будет сразу передано администрации:",
        "sos_sent": "🚨 Сигнал тревоги отправлен администрации. Оставайтесь на связи!",
    },
    "uz": {
        "welcome": "🚖 <b>Yo'ldosh Taxi</b> rasmiy buyurtma berish tizimiga xush kelibsiz!",
        "choose_action": "Iltimos, quyidagi menyudan kerakli amalni tanlang:",
        "become_driver": "🚖 Haydovchi bo'lish",
        "driver_activated": "✅ Haydovchi rejimi yoqildi! Verifikatsiyadan o'ting va balansni to'ldiring.",
        "profile_title": "👤 <b>Yo'ldosh Taxi tizimidagi profilingiz</b>",
        "balance_title": "💰 Hisob balansi",
        "verified_status": "🛡 Tasdiqlanganlik holati",
        "yes": "Ha (Tasdiqlangan) ✅",
        "no": "Yo'q (Tasdiqlanmagan) ❌",
        "order_taxi": "🚕 Taksi chaqirish",
        "order_later": "🕒 Keyinga buyurtma berish",
        "history": "📋 Safarlar tarixi",
        "profile": "👤 Mening profilim",
        "topup": "💰 Balansni to'ldirish",
        "balance": "💳 Mening balansim",
        "verification": "📸 Verifikatsiya",
        "free_orders": "🚖 Bo'sh buyurtmalar",
        "how_to_use": "📖 Qo'llanma",
        "lang_changed": "🇺🇿 Til muvaffaqiyatli o'zbek tiliga o'zgartirildi!",
        "sos_btn": "🚨 TREVOGA (SOS)",
        "finish_trip_btn": "🏁 Safarni yakunlash",
        "delete_profile_btn": "❌ Profilni o'chirish",
        "how_to_use_text": (
            "📖 <b>Yo'ldosh Taxi foydalanish qo'llanmasi</b>\n\n"
            "1️⃣ <b>Yo'lovchilar uchun:</b>\n"
            "• «🚕 Taksi chaqirish» yoki «🕒 Keyinga buyurtma berish» tugmasini bosing.\n"
            "• Qayerdan va qayerga borishingizni hamda izohni kiriting.\n"
            "• Haydovchi buyurtmangizni qabul qilishini kuting.\n\n"
            "2️⃣ <b>Haydovchilar uchun:</b>\n"
            "• «🚖 Haydovchi bo'lish»ni tanlang, verifikatsiyadan o'ting (guvohnoma/pasport rasmini yuboring) va balansni to'ldiring.\n"
            "• «🚖 Bo'sh buyurtmalar» bo'limidan buyurtmalarni qabul qiling.\n\n"
            "🚨 Safar davomida favqulodda <b>SOS</b> tugmasi ishlaydi.\n"
            "📞 Qo'llab-quvvatlash: <b>+998 91 773-51-52</b>"
        ),
        "topup_instructions": (
            "💳 <b>Haydovchi balansini to'ldirish</b>\n\n"
            "Kerakli summani quyidagi bank kartasiga o'tkazing:\n"
            "<code>{card}</code>\n"
            "Qabul qiluvchi: <b>{holder}</b>\n"
            "Qo'llab-quvvatlash: <b>{phone}</b>\n\n"
            "📸 O'tkazmadan so'ng chek yoki skrinshotni ushbu chatga yuboring."
        ),
        "topup_sent": "✅ Chek tekshirish uchun administratorga yuborildi!",
        "verification_instructions": (
            "📸 <b>Haydovchi profilini verifikatsiya qilish</b>\n\n"
            "Ma'muriyat tomonidan tekshiruvdan o'tish uchun haydovchilik guvohnomasi yoki pasportingiz rasmini yuboring."
        ),
        "verification_sent": "✅ Hujjatlar rasmi tekshirish uchun administratorga yuborildi.",
        "reg_name": "📝 <b>Ro'yxatdan o'tish</b>\n\nIltimos, <b>Ism va Familiyangizni</b> kiriting:",
        "reg_age": "🔢 <b>Yoshingizni</b> raqamlarda kiriting (masalan: <code>25</code>):",
        "reg_age_err": "⚠️ Iltimos, yoshingizni to'g'ri kiriting (masalan: 20):",
        "reg_phone": "📞 Endi <b>telefon raqamingizni</b> pastdagi tugma orqali yoki qo'lda yuboring:",
        "reg_phone_btn": "📱 Kontakt bilan bo'lishish",
        "reg_phone_err": "⚠️ To'g'ri telefon raqamini kiriting (masalan: +998 91 773-51-52):",
        "reg_done": "✅ <b>Ro'yxatdan o'tish muvaffaqiyatli yakunlandi!</b> Tizimga xush kelibsiz.",
        "role_driver": "Haydovchi 🚖",
        "role_passenger": "Yo'lovchi 👤",
        "lbl_name": "Ism",
        "lbl_phone": "Telefon",
        "lbl_role": "Rol",
        "not_set": "Ko'rsatilmagan",
        "currency": "so'm",
        "balance_text": "💳 Balansingiz: <b>{amount}</b>",
        "history_title": "📜 <b>Sizning oxirgi safarlaringiz tarixi:</b>\n\n",
        "history_empty": "📭 Sizda hali safarlar tarixi yo'q.",
        "lbl_order": "Buyurtma",
        "lbl_status": "Holati",
        "lbl_from": "Qayerdan",
        "lbl_to": "Qayerga",
        "lbl_date": "Sana",
        "st_pending": "⏳ Qidiruvda",
        "st_accepted": "🚗 Qabul qilingan",
        "st_active": "🚕 Yo'lda",
        "st_completed": "✅ Yakunlangan",
        "st_cancelled": "❌ Bekor qilingan",
        "trip_done_driver": (
            "🏁 <b>#{id}-safar yakunlandi!</b>\n\n"
            "💵 Safar narxi: <b>{fare}</b>\n"
            "➖ Xizmat komissiyasi ({percent}%): <b>{fee}</b>\n"
            "💰 Balansingiz: <b>{balance}</b>\n\n"
            "Yo'ldosh Taxi bilan ishlaganingiz uchun rahmat."
        ),
        "ask_price": "💵 <b>Safar narxini</b> raqamlarda kiriting (masalan: <code>25000</code>).\nSizdan xizmat komissiyasi — {percent}% yechib olinadi.",
        "price_err": "⚠️ Safar narxini faqat raqamlarda kiriting (masalan: 25000):",
        "trip_done_passenger": "🏁 <b>Sizning #{id}-safaringiz yakunlandi!</b> Yo'ldosh Taxi xizmatidan foydalanganingiz uchun rahmat.",
        "no_active_trip": "⚠️ Hozirda sizda yakunlash uchun faol safar yo'q.",
        "sos_ask": "🚨 Nima bo'lganini qisqacha yozing (bitta xabarda). U darhol ma'muriyatga yuboriladi:",
        "sos_sent": "🚨 Xavotir signali ma'muriyatga yuborildi. Aloqada qoling!",
    },
    "en": {
        "welcome": "🚖 Welcome to the official <b>Yo'ldosh Taxi</b> ordering system!",
        "choose_action": "Please choose the required action from the menu below:",
        "become_driver": "🚖 Become a Driver",
        "driver_activated": "✅ Driver mode activated! Pass verification and top up your balance.",
        "profile_title": "👤 <b>Your Yo'ldosh Taxi System Profile</b>",
        "balance_title": "💰 Account Balance",
        "verified_status": "🛡 Verification Status",
        "yes": "Yes (Verified) ✅",
        "no": "No (Unverified) ❌",
        "order_taxi": "🚕 Order Taxi",
        "order_later": "🕒 Order for Later",
        "history": "📋 Trip History",
        "profile": "👤 My Profile",
        "topup": "💰 Top Up Balance",
        "balance": "💳 My Balance",
        "verification": "📸 Verification",
        "free_orders": "🚖 Free Orders",
        "how_to_use": "📖 How to use",
        "lang_changed": "🇬🇧 Language successfully changed to English!",
        "sos_btn": "🚨 SOS EMERGENCY",
        "finish_trip_btn": "🏁 Complete Trip",
        "delete_profile_btn": "❌ Delete Profile",
        "how_to_use_text": (
            "📖 <b>Yo'ldosh Taxi User Guide</b>\n\n"
            "1️⃣ <b>For Passengers:</b>\n"
            "• Tap «🚕 Order Taxi» or «🕒 Order for Later».\n"
            "• Enter your pickup location, destination, and optional comment.\n"
            "• Wait for an available driver to accept your ride.\n\n"
            "2️⃣ <b>For Drivers:</b>\n"
            "• Choose «🚖 Become a Driver», pass verification (send license/passport photo), and top up your balance.\n"
            "• Browse and accept rides in the «🚖 Free Orders» section.\n\n"
            "🚨 An emergency <b>SOS</b> button is available during active trips.\n"
            "📞 Support: <b>+998 91 773-51-52</b>"
        ),
        "topup_instructions": (
            "💳 <b>Driver Balance Top-Up</b>\n\n"
            "Transfer the required amount to the bank card:\n"
            "<code>{card}</code>\n"
            "Recipient: <b>{holder}</b>\n"
            "Support Phone: <b>{phone}</b>\n\n"
            "📸 After the transfer, send a screenshot or receipt photo to this chat."
        ),
        "topup_sent": "✅ The receipt has been sent to the administrator for review!",
        "verification_instructions": (
            "📸 <b>Driver Profile Verification</b>\n\n"
            "Please send a clear photo of your driver's license or passport for verification."
        ),
        "verification_sent": "✅ Your document photo has been sent to the administrator for review.",
        "reg_name": "📝 <b>Registration</b>\n\nPlease enter your <b>First and Last Name</b>:",
        "reg_age": "🔢 Enter your <b>age</b> in digits (e.g. <code>25</code>):",
        "reg_age_err": "⚠️ Please enter a valid age in digits (e.g. 20):",
        "reg_phone": "📞 Now send your <b>phone number</b> using the button below or type it manually:",
        "reg_phone_btn": "📱 Share contact",
        "reg_phone_err": "⚠️ Please enter a valid phone number (e.g. +998 91 773-51-52):",
        "reg_done": "✅ <b>Registration successfully completed!</b> Welcome to the system.",
        "role_driver": "Driver 🚖",
        "role_passenger": "Passenger 👤",
        "lbl_name": "Name",
        "lbl_phone": "Phone",
        "lbl_role": "Role",
        "not_set": "Not set",
        "currency": "UZS",
        "balance_text": "💳 Your balance: <b>{amount}</b>",
        "history_title": "📜 <b>Your latest trips:</b>\n\n",
        "history_empty": "📭 You have no trip history yet.",
        "lbl_order": "Order",
        "lbl_status": "Status",
        "lbl_from": "From",
        "lbl_to": "To",
        "lbl_date": "Date",
        "st_pending": "⏳ Searching",
        "st_accepted": "🚗 Accepted",
        "st_active": "🚕 On the way",
        "st_completed": "✅ Completed",
        "st_cancelled": "❌ Cancelled",
        "trip_done_driver": (
            "🏁 <b>Trip #{id} completed!</b>\n\n"
            "💵 Trip fare: <b>{fare}</b>\n"
            "➖ Service commission ({percent}%): <b>{fee}</b>\n"
            "💰 Your balance: <b>{balance}</b>\n\n"
            "Thank you for driving with Yo'ldosh Taxi."
        ),
        "ask_price": "💵 Enter the <b>trip fare</b> in digits (e.g. <code>25000</code>).\nA service commission of {percent}% will be deducted from your balance.",
        "price_err": "⚠️ Enter the trip fare in digits only (e.g. 25000):",
        "trip_done_passenger": "🏁 <b>Your trip #{id} has been completed!</b> Thank you for choosing Yo'ldosh Taxi.",
        "no_active_trip": "⚠️ You don't have an active trip to complete right now.",
        "sos_ask": "🚨 Briefly describe what happened (one message). It will be sent to the administration immediately:",
        "sos_sent": "🚨 Your alert has been sent to the administration. Stay in touch!",
    },
}

LANG_PROMPT = (
    "Assalomu alaykum! Iltimos, tilni tanlang:\n\n"
    "Здравствуйте! Пожалуйста, выберите язык:\n\n"
    "Hello! Please select a language:"
)


def T(lang: Optional[str]) -> dict:
    return LANGS.get(lang or "ru", LANGS["ru"])


def texts(key: str) -> Set[str]:
    """Все варианты текста кнопки на всех языках."""
    return {d[key] for d in LANGS.values()}


def esc(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# =====================================================================
# 3. БАЗА ДАННЫХ (AIOSQLITE)
# =====================================================================

async def init_db() -> None:
    logger.info("Инициализация базы данных...")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                role TEXT DEFAULT 'passenger',
                lang TEXT DEFAULT 'ru',
                first_name TEXT,
                last_name TEXT,
                age INTEGER,
                phone TEXT,
                balance REAL DEFAULT 0.0,
                verified INTEGER DEFAULT 0,
                verification_photo TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                passenger_id INTEGER,
                driver_id INTEGER,
                pickup TEXT,
                destination TEXT,
                comment TEXT,
                status TEXT DEFAULT 'pending',
                is_scheduled INTEGER DEFAULT 0,
                schedule_time TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promos (
                code TEXT PRIMARY KEY,
                discount REAL,
                is_active INTEGER DEFAULT 1
            )
        """)
        # Миграция: цена поездки и комиссия сервиса
        for column in ("price REAL DEFAULT 0", "commission REAL DEFAULT 0"):
            try:
                await db.execute(f"ALTER TABLE orders ADD COLUMN {column}")
            except Exception:
                pass  # колонка уже существует
        await db.commit()
    logger.info("База данных успешно инициализирована.")


async def db_fetchone(query: str, params: tuple = ()):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(query, params) as cur:
            return await cur.fetchone()


async def db_fetchall(query: str, params: tuple = ()):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(query, params) as cur:
            return await cur.fetchall()


async def db_execute(query: str, params: tuple = ()):
    """Возвращает (lastrowid, rowcount)."""
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute(query, params)
        await db.commit()
        return cur.lastrowid, cur.rowcount


async def get_lang(user_id: int) -> str:
    row = await db_fetchone("SELECT lang FROM users WHERE user_id = ?", (user_id,))
    return row[0] if row and row[0] in LANGS else "ru"


async def get_role_lang(user_id: int):
    row = await db_fetchone("SELECT role, lang FROM users WHERE user_id = ?", (user_id,))
    if not row:
        return "passenger", "ru"
    return (row[0] or "passenger"), (row[1] if row[1] in LANGS else "ru")


# =====================================================================
# 4. FSM СОСТОЯНИЯ
# =====================================================================

class OrderStates(StatesGroup):
    waiting_for_pickup = State()
    waiting_for_destination = State()
    waiting_for_schedule_time = State()
    waiting_for_comment = State()
    waiting_for_sos_reason = State()


class DriverStates(StatesGroup):
    waiting_for_verification_photo = State()
    waiting_for_receipt = State()
    waiting_for_trip_price = State()


class AdminStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_broadcast_text = State()
    waiting_for_promo_code = State()
    waiting_for_promo_discount = State()


class RegistrationStates(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_age = State()
    waiting_for_phone = State()


class SupportStates(StatesGroup):
    waiting_for_support_message = State()


class AdminReplyStates(StatesGroup):
    waiting_for_reply_text = State()


class AdminTopUpStates(StatesGroup):
    waiting_for_amount = State()


# =====================================================================
# 5. КЛАВИАТУРЫ
# =====================================================================

def get_main_menu(role: str = "passenger", lang: str = "ru") -> ReplyKeyboardMarkup:
    t = T(lang)
    if role == "driver":
        rows = [
            [KeyboardButton(text=t["free_orders"]), KeyboardButton(text=t["topup"])],
            [KeyboardButton(text=t["profile"]), KeyboardButton(text=t["balance"])],
            [KeyboardButton(text=t["verification"]), KeyboardButton(text=t["history"])],
            [KeyboardButton(text=t["how_to_use"]), KeyboardButton(text=LANG_BTN)],
        ]
    else:
        rows = [
            [KeyboardButton(text=t["order_taxi"]), KeyboardButton(text=t["order_later"])],
            [KeyboardButton(text=t["profile"]), KeyboardButton(text=t["balance"])],
            [KeyboardButton(text=t["history"]), KeyboardButton(text=t["become_driver"])],
            [KeyboardButton(text=t["how_to_use"]), KeyboardButton(text=LANG_BTN)],
        ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
        ]]
    )


def phone_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=T(lang)["reg_phone_btn"], request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# =====================================================================
# 6. СЛУЖБА ПОДДЕРЖКИ
# =====================================================================

@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.set_state(SupportStates.waiting_for_support_message)
    await message.answer(
        "🛠 <b>Служба поддержки Yo'ldosh Taxi</b>\n\n"
        "Напишите ваше сообщение, вопрос или проблему одним текстом, и оно будет мгновенно "
        "передано администрации. Мы ответим вам в ближайшее время!"
    )


@router.message(SupportStates.waiting_for_support_message, F.text)
async def process_support_message(message: Message, state: FSMContext) -> None:
    try:
        user_id = message.from_user.id
        username = f"@{esc(message.from_user.username)}" if message.from_user.username else "Не указан"
        full_name = esc(message.from_user.full_name or "Не указано")

        row = await db_fetchone("SELECT phone FROM users WHERE user_id = ?", (user_id,))
        phone = esc(row[0]) if row and row[0] else "Не указан в базе"

        admin_text = (
            "📩 <b>Новое обращение в поддержку!</b>\n\n"
            f"👤 <b>От:</b> {full_name}\n"
            f"🔗 <b>Username:</b> {username}\n"
            f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
            f"💬 <b>Сообщение:</b>\n{esc(message.text)}"
        )
        reply_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="💬 Ответить анонимно", callback_data=f"support_reply_{user_id}")]]
        )
        await bot.send_message(ADMIN_ID, admin_text, reply_markup=reply_kb)
        await message.answer("✅ Ваше сообщение успешно отправлено в службу поддержки! Ожидайте ответа.")
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение в поддержку админу: {e}")
        await message.answer("⚠️ Не удалось связаться с поддержкой. Попробуйте позже.")
    finally:
        await state.clear()


@router.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("support_reply_"))
async def admin_start_reply_callback(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        target_user_id = int(callback.data.split("_")[2])
        await state.update_data(reply_target_id=target_user_id)
        await state.set_state(AdminReplyStates.waiting_for_reply_text)
        await callback.message.answer(
            f"✍️ Напишите ответ для пользователя (ID: <code>{target_user_id}</code>).\n"
            "Ваше сообщение будет отправлено от имени бота:"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка в колбэке ответа поддержки: {e}")
        await callback.answer("⚠️ Произошла ошибка.", show_alert=True)


@router.message(F.from_user.id == ADMIN_ID, AdminReplyStates.waiting_for_reply_text, F.text)
async def admin_send_button_reply(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    target_user_id = data.get("reply_target_id")
    await state.clear()

    if not target_user_id:
        await message.reply("⚠️ Ошибка: ID получателя потерян. Нажмите кнопку «Ответить» ещё раз.")
        return

    user_lang = await get_lang(int(target_user_id))
    headers = {
        "ru": "🛠 <b>Ответ от службы поддержки Yo'ldosh Taxi:</b>",
        "uz": "🛠 <b>Yo'ldosh Taxi qo'llab-quvvatlash xizmatidan javob:</b>",
        "en": "🛠 <b>Response from Yo'ldosh Taxi Support:</b>",
    }
    try:
        await bot.send_message(int(target_user_id), f"{headers[user_lang]}\n\n{esc(message.text)}")
        await message.reply("✅ Ответ анонимно доставлен пользователю от имени бота!")
    except Exception as e:
        logger.error(f"Не удалось отправить ответ пользователю {target_user_id}: {e}")
        await message.reply("⚠️ Не удалось отправить сообщение пользователю (возможно, он заблокировал бота).")


# =====================================================================
# 7. /START, ВЫБОР ЯЗЫКА И РЕГИСТРАЦИЯ
# =====================================================================

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id

    row = await db_fetchone("SELECT role, lang, phone FROM users WHERE user_id = ?", (user_id,))

    # 1. Нет в базе или нет языка -> выбор языка
    if not row or not row[1]:
        if not row:
            await db_execute(
                "INSERT INTO users (user_id, role, lang, balance, created_at) VALUES (?, 'passenger', NULL, 0.0, ?)",
                (user_id, now_str()),
            )
        await message.answer(LANG_PROMPT, reply_markup=get_language_keyboard())
        return

    role, lang, phone = row
    t = T(lang)

    # 2. Регистрация не завершена -> ввод имени
    if not phone:
        await state.set_state(RegistrationStates.waiting_for_full_name)
        await message.answer(t["reg_name"], reply_markup=ReplyKeyboardRemove())
        return

    # 3. Всё готово -> главное меню
    await message.answer(f"{t['welcome']}\n\n{t['choose_action']}", reply_markup=get_main_menu(role, lang))


@router.callback_query(F.data.in_({"lang_uz", "lang_ru", "lang_en"}))
async def process_language_callback(callback: CallbackQuery, state: FSMContext) -> None:
    selected_lang = callback.data.split("_")[1]
    user_id = callback.from_user.id

    await db_execute(
        "INSERT INTO users (user_id, role, lang, balance, created_at) VALUES (?, 'passenger', ?, 0.0, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET lang = excluded.lang",
        (user_id, selected_lang, now_str()),
    )
    row = await db_fetchone("SELECT role, phone FROM users WHERE user_id = ?", (user_id,))
    role = row[0] if row and row[0] else "passenger"
    phone = row[1] if row else None

    try:
        await callback.message.delete()
    except Exception:
        pass

    t = T(selected_lang)
    if phone:
        # Уже зарегистрирован — просто смена языка
        await state.clear()
        await bot.send_message(
            user_id,
            f"{t['lang_changed']}\n\n{t['choose_action']}",
            reply_markup=get_main_menu(role, selected_lang),
        )
    else:
        await state.set_state(RegistrationStates.waiting_for_full_name)
        await bot.send_message(user_id, t["reg_name"], reply_markup=ReplyKeyboardRemove())
    await callback.answer()


@router.message(F.text == LANG_BTN)
async def change_language_request(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🌐 Выберите язык / Tilni tanlang / Choose language:", reply_markup=get_language_keyboard())


@router.message(RegistrationStates.waiting_for_full_name, F.text)
async def process_full_name(message: Message, state: FSMContext) -> None:
    parts = message.text.strip().split(maxsplit=1)
    if not parts:
        return
    await state.update_data(first_name=parts[0][:64], last_name=(parts[1] if len(parts) > 1 else "")[:64])
    await state.set_state(RegistrationStates.waiting_for_age)
    lang = await get_lang(message.from_user.id)
    await message.answer(T(lang)["reg_age"])


@router.message(RegistrationStates.waiting_for_age, F.text)
async def process_age(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id)
    t = T(lang)
    text = message.text.strip()
    if not text.isdigit() or not (5 <= int(text) <= 100):
        await message.answer(t["reg_age_err"])
        return
    await state.update_data(age=int(text))
    await state.set_state(RegistrationStates.waiting_for_phone)
    await message.answer(t["reg_phone"], reply_markup=phone_keyboard(lang))


async def save_user_and_finish(message: Message, state: FSMContext, phone: str) -> None:
    user_id = message.from_user.id
    data = await state.get_data()
    await db_execute(
        "UPDATE users SET first_name = ?, last_name = ?, age = ?, phone = ? WHERE user_id = ?",
        (data.get("first_name", ""), data.get("last_name", ""), data.get("age", 0), phone, user_id),
    )
    role, lang = await get_role_lang(user_id)
    await message.answer(T(lang)["reg_done"], reply_markup=get_main_menu(role, lang))
    await state.clear()


@router.message(RegistrationStates.waiting_for_phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext) -> None:
    await save_user_and_finish(message, state, message.contact.phone_number)


@router.message(RegistrationStates.waiting_for_phone, F.text)
async def process_phone_text(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    digits = re.sub(r"\D", "", phone)
    if not (9 <= len(digits) <= 15):
        lang = await get_lang(message.from_user.id)
        await message.answer(T(lang)["reg_phone_err"])
        return
    await save_user_and_finish(message, state, phone)


# =====================================================================
# 8. МЕНЮ: КАК ПОЛЬЗОВАТЬСЯ, ПРОФИЛЬ, БАЛАНС, ИСТОРИЯ, РОЛЬ ВОДИТЕЛЯ
# =====================================================================

@router.message(F.text.in_(texts("how_to_use")))
async def show_how_to_use(message: Message) -> None:
    lang = await get_lang(message.from_user.id)
    await message.answer(T(lang)["how_to_use_text"])


@router.message(F.text.in_(texts("become_driver")))
async def switch_to_driver_mode(message: Message) -> None:
    user_id = message.from_user.id
    await db_execute("UPDATE users SET role = 'driver' WHERE user_id = ?", (user_id,))
    lang = await get_lang(user_id)
    await message.answer(T(lang)["driver_activated"], reply_markup=get_main_menu("driver", lang))


@router.message(F.text.in_(texts("profile")))
async def show_user_profile(message: Message) -> None:
    user_id = message.from_user.id
    row = await db_fetchone(
        "SELECT role, balance, verified, lang, first_name, last_name, phone FROM users WHERE user_id = ?",
        (user_id,),
    )
    if not row:
        await message.answer("Нажмите /start")
        return

    role, balance, verified, lang, fname, lname, phone = row
    lang = lang if lang in LANGS else "ru"
    t = T(lang)
    role_str = t["role_driver"] if role == "driver" else t["role_passenger"]
    verified_str = t["yes"] if verified == 1 else t["no"]
    name_str = f"{fname or ''} {lname or ''}".strip() or t["not_set"]

    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t["delete_profile_btn"], callback_data="delete_my_profile")]]
    )
    await message.answer(
        f"{t['profile_title']}\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 {t['lbl_name']}: <b>{esc(name_str)}</b>\n"
        f"📞 {t['lbl_phone']}: <code>{esc(phone or t['not_set'])}</code>\n"
        f"📌 {t['lbl_role']}: {role_str}\n"
        f"{t['balance_title']}: <code>{(balance or 0):,.0f} {t['currency']}</code>\n"
        f"{t['verified_status']}: {verified_str}",
        reply_markup=markup,
    )


@router.callback_query(F.data == "delete_my_profile")
async def delete_profile_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await db_execute("DELETE FROM users WHERE user_id = ?", (callback.from_user.id,))
    await callback.message.edit_text(
        "❌ Ваш профиль был полностью удален из системы. Введите /start для регистрации заново."
    )
    await callback.answer()


@router.message(F.text.in_(texts("balance")))
async def show_balance(message: Message) -> None:
    user_id = message.from_user.id
    row = await db_fetchone("SELECT balance, lang FROM users WHERE user_id = ?", (user_id,))
    balance = (row[0] or 0) if row else 0
    lang = row[1] if row and row[1] in LANGS else "ru"
    t = T(lang)
    await message.answer(t["balance_text"].format(amount=f"{balance:,.0f} {t['currency']}"))


@router.message(F.text.in_(texts("history")))
async def show_trip_history(message: Message) -> None:
    user_id = message.from_user.id
    lang = await get_lang(user_id)
    t = T(lang)

    rows = await db_fetchall(
        """
        SELECT order_id, pickup, destination, status, created_at
        FROM orders
        WHERE passenger_id = ? OR driver_id = ?
        ORDER BY order_id DESC LIMIT 5
        """,
        (user_id, user_id),
    )
    if not rows:
        await message.answer(t["history_empty"])
        return

    text = t["history_title"]
    for order_id, pickup, destination, status, created_at in rows:
        status_text = t.get(f"st_{status}", esc(status))
        text += (
            f"🆔 <b>{t['lbl_order']} #{order_id}</b>\n"
            f"📌 {t['lbl_status']}: {status_text}\n"
            f"📍 {t['lbl_from']}: {esc(pickup)}\n"
            f"🏁 {t['lbl_to']}: {esc(destination)}\n"
            f"🕒 {t['lbl_date']}: {esc(created_at)}\n"
            "----------------------------------\n"
        )
    await message.answer(text)


# =====================================================================
# 9. АДМИН-ПАНЕЛЬ (СТАТИСТИКА, РАССЫЛКА, ПРОМОКОДЫ)
# =====================================================================

@router.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel_entry(message: Message, state: FSMContext) -> None:
    if not ADMIN_PASSWORD:
        await message.answer("⚠️ ADMIN_PASSWORD не задан в переменных окружения. Вход отключён.")
        return
    await state.set_state(AdminStates.waiting_for_password)
    await message.answer("🔐 <b>Введите пароль администратора:</b>")


@router.message(F.from_user.id == ADMIN_ID, AdminStates.waiting_for_password, F.text)
async def verify_admin_password(message: Message, state: FSMContext) -> None:
    await state.clear()
    try:
        await message.delete()  # убираем пароль из чата
    except Exception:
        pass

    if ADMIN_PASSWORD and hmac.compare_digest(message.text.encode(), ADMIN_PASSWORD.encode()):
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast_menu")],
                [InlineKeyboardButton(text="📊 Статистика сервиса", callback_data="admin_stats_menu")],
                [InlineKeyboardButton(text="🎟 Добавить промокод", callback_data="admin_promo_menu")],
            ]
        )
        await message.answer("👑 <b>Панель Администратора разблокирована!</b>", reply_markup=kb)
    else:
        await message.answer("❌ Неверный пароль. Доступ отклонен.")


@router.callback_query(F.from_user.id == ADMIN_ID, F.data == "admin_stats_menu")
async def admin_stats_callback(callback: CallbackQuery) -> None:
    total_users = (await db_fetchone("SELECT COUNT(*) FROM users"))[0]
    total_drivers = (await db_fetchone("SELECT COUNT(*) FROM users WHERE role = 'driver'"))[0]
    total_orders = (await db_fetchone("SELECT COUNT(*) FROM orders"))[0]
    completed = (await db_fetchone("SELECT COUNT(*) FROM orders WHERE status = 'completed'"))[0]
    total_fee = (await db_fetchone("SELECT COALESCE(SUM(commission), 0) FROM orders WHERE status = 'completed'"))[0]

    await callback.message.answer(
        "📊 <b>Статистика сервиса Yo'ldosh Taxi</b>\n\n"
        f"👥 Всего пользователей: <code>{total_users}</code>\n"
        f"🚖 Зарегистрировано водителей: <code>{total_drivers}</code>\n"
        f"📦 Всего заказов создано: <code>{total_orders}</code>\n"
        f"🏁 Успешно завершено поездок: <code>{completed}</code>\n"
        f"💸 Собрано комиссии: <code>{total_fee:,.0f} сум</code>"
    )
    await callback.answer()


@router.callback_query(F.from_user.id == ADMIN_ID, F.data == "admin_broadcast_menu")
async def admin_broadcast_step_one(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("📢 Введите текст для рассылки всем пользователям бота:")
    await state.set_state(AdminStates.waiting_for_broadcast_text)
    await callback.answer()


@router.message(F.from_user.id == ADMIN_ID, AdminStates.waiting_for_broadcast_text, F.text)
async def admin_broadcast_execute(message: Message, state: FSMContext) -> None:
    broadcast_text = esc(message.text)
    await state.clear()

    users = await db_fetchall("SELECT user_id FROM users")
    success_count = 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, f"📢 <b>Объявление сервиса:</b>\n\n{broadcast_text}")
            success_count += 1
        except Exception:
            pass
        await asyncio.sleep(0.05)

    await message.answer(f"✅ Рассылка завершена! Получателей: {success_count} из {len(users)}")


@router.callback_query(F.from_user.id == ADMIN_ID, F.data == "admin_promo_menu")
async def admin_promo_step_one(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("🎟 Введите уникальный промокод:")
    await state.set_state(AdminStates.waiting_for_promo_code)
    await callback.answer()


@router.message(F.from_user.id == ADMIN_ID, AdminStates.waiting_for_promo_code, F.text)
async def admin_promo_step_two(message: Message, state: FSMContext) -> None:
    await state.update_data(promo_code=message.text.strip())
    await message.answer("💰 Введите номинал скидки (число):")
    await state.set_state(AdminStates.waiting_for_promo_discount)


@router.message(F.from_user.id == ADMIN_ID, AdminStates.waiting_for_promo_discount, F.text)
async def admin_promo_step_three(message: Message, state: FSMContext) -> None:
    try:
        discount = float(message.text.replace(" ", "").replace(",", "."))
    except ValueError:
        await message.answer("❌ Введите число, например: 5000")
        return

    data = await state.get_data()
    code = data["promo_code"]
    await db_execute("INSERT OR REPLACE INTO promos (code, discount, is_active) VALUES (?, ?, 1)", (code, discount))
    await message.answer(f"✅ Промокод <code>{esc(code)}</code> на скидку <code>{discount:,.0f} сум</code> создан!")
    await state.clear()


# =====================================================================
# 10. ЗАКАЗЫ
# =====================================================================

@router.message(F.text.in_(texts("order_taxi") | texts("order_later")))
async def start_taxi_order(message: Message, state: FSMContext) -> None:
    row = await db_fetchone("SELECT phone FROM users WHERE user_id = ?", (message.from_user.id,))
    if not row or not row[0]:
        await message.answer("⚠️ Сначала завершите регистрацию: /start")
        return

    is_scheduled = 1 if message.text in texts("order_later") else 0
    await state.update_data(is_scheduled=is_scheduled)
    await message.answer("📍 Укажите точный адрес отправления (откуда вас забрать):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OrderStates.waiting_for_pickup)


@router.message(OrderStates.waiting_for_pickup, F.text)
async def process_order_pickup(message: Message, state: FSMContext) -> None:
    await state.update_data(pickup=message.text)
    await message.answer("🏁 Укажите точный адрес назначения (куда едем):")
    await state.set_state(OrderStates.waiting_for_destination)


@router.message(OrderStates.waiting_for_destination, F.text)
async def process_order_destination(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.update_data(destination=message.text)

    if data.get("is_scheduled") == 1:
        await message.answer("📅 Укажите дату и примерное время выезда (например: <code>26.11.2026 в 15:00</code>):")
        await state.set_state(OrderStates.waiting_for_schedule_time)
    else:
        await state.update_data(schedule_time="Срочно сейчас")
        await message.answer("💬 Укажите комментарий для водителя (или напишите 'нет'):")
        await state.set_state(OrderStates.waiting_for_comment)


@router.message(OrderStates.waiting_for_schedule_time, F.text)
async def process_order_schedule_time(message: Message, state: FSMContext) -> None:
    await state.update_data(schedule_time=message.text)
    await message.answer("💬 Укажите комментарий для водителя (или напишите 'нет'):")
    await state.set_state(OrderStates.waiting_for_comment)


@router.message(OrderStates.waiting_for_comment, F.text)
async def finalize_order_creation(message: Message, state: FSMContext) -> None:
    comment = message.text
    data = await state.get_data()
    passenger_id = message.from_user.id
    pickup = data.get("pickup", "")
    destination = data.get("destination", "")
    is_scheduled = data.get("is_scheduled", 0)
    schedule_time = data.get("schedule_time", "Срочно сейчас")

    order_id, _ = await db_execute(
        "INSERT INTO orders (passenger_id, pickup, destination, comment, is_scheduled, schedule_time, created_at, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
        (passenger_id, pickup, destination, comment, is_scheduled, schedule_time, now_str()),
    )

    order_type_text = (
        f"🕒 <b>ПРЕДВАРИТЕЛЬНЫЙ ЗАКАЗ</b> (Время: {esc(schedule_time)})" if is_scheduled else "🚀 <b>СРОЧНЫЙ ЗАКАЗ</b>"
    )
    body = (
        f"{order_type_text}\n📍 Откуда: {esc(pickup)}\n🏁 Куда: {esc(destination)}\n💬 Комментарий: {esc(comment)}"
    )

    role, lang = await get_role_lang(passenger_id)
    cancel_markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel_order_{order_id}")]]
    )
    await message.answer(f"✅ Заказ <b>#{order_id}</b> успешно создан!\n\n{body}\n\n🔄 Поиск водителя...", reply_markup=cancel_markup)
    # Возвращаем главное меню (клавиатура была скрыта на время заказа)
    await message.answer("👇", reply_markup=get_main_menu(role, lang))

    channel_markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🚖 Принять заказ", callback_data=f"accept_order_{order_id}")]]
    )
    try:
        await bot.send_message(CHANNEL_USERNAME, f"🆕 <b>Новый заказ #{order_id}</b>\n\n{body}", reply_markup=channel_markup)
    except Exception as e:
        logger.error(f"Не удалось отправить в канал: {e}")

    await state.clear()


@router.callback_query(F.data.startswith("cancel_order_"))
async def passenger_cancel_order_handler(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split("_")[2])
    row = await db_fetchone("SELECT status, passenger_id FROM orders WHERE order_id = ?", (order_id,))

    if not row or row[1] != callback.from_user.id:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return
    if row[0] != "pending":
        await callback.answer("⚠️ Заказ уже принят водителем или отменен!", show_alert=True)
        return

    _, changed = await db_execute(
        "UPDATE orders SET status = 'cancelled' WHERE order_id = ? AND status = 'pending'", (order_id,)
    )
    if changed == 0:
        await callback.answer("⚠️ Заказ уже принят водителем!", show_alert=True)
        return

    await callback.message.edit_text(f"❌ Заказ #{order_id} был успешно отменен пассажиром.")
    await callback.answer()
    logger.info(f"Заказ #{order_id} отменен.")


@router.message(F.text.in_(texts("free_orders")))
async def show_free_orders_for_drivers(message: Message) -> None:
    row = await db_fetchone("SELECT role FROM users WHERE user_id = ?", (message.from_user.id,))
    if not row or row[0] != "driver":
        await message.answer("⚠️ Этот раздел доступен только водителям.")
        return

    rows = await db_fetchall(
        "SELECT order_id, pickup, destination, comment, schedule_time, is_scheduled "
        "FROM orders WHERE status = 'pending' ORDER BY order_id DESC LIMIT 5"
    )
    if not rows:
        await message.answer("🚖 В данный момент свободных заказов нет.")
        return

    for order_id, pickup, destination, comment, schedule_time, is_scheduled in rows:
        type_str = f"🕒 Предварительный ({esc(schedule_time)})" if is_scheduled else "🚀 Срочный"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🚖 Принять заказ", callback_data=f"accept_order_{order_id}")]]
        )
        await message.answer(
            f"📦 <b>Заказ #{order_id}</b> ({type_str})\n"
            f"📍 Откуда: {esc(pickup)}\n🏁 Куда: {esc(destination)}\n💬 Комментарий: {esc(comment)}",
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("accept_order_"))
async def driver_accept_order_handler(callback: CallbackQuery) -> None:
    try:
        order_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка в данных заказа.", show_alert=True)
        return

    driver_id = callback.from_user.id

    try:
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute(
                "SELECT role, verified, phone, first_name, verification_photo, lang, balance FROM users WHERE user_id = ?",
                (driver_id,),
            ) as cur:
                user_row = await cur.fetchone()

            if not user_row:
                await callback.answer("❌ Вы не зарегистрированы в системе. Нажмите /start", show_alert=True)
                return

            role, is_verified, phone, first_name, verification_photo, lang, balance = user_row
            lang = lang if lang in LANGS else "ru"

            if role != "driver" or not phone or not first_name:
                msgs = {
                    "ru": "⚠️ Вы не завершили полную регистрацию водителя! Нажмите «Стать водителем» и укажите данные.",
                    "uz": "⚠️ Siz to'liq haydovchi ro'yxatidan o'tmagansiz!",
                    "en": "⚠️ You have not completed full driver registration!",
                }
                await callback.answer(msgs[lang], show_alert=True)
                return

            if not verification_photo or int(is_verified or 0) != 1:
                msgs = {
                    "ru": "⚠️ Требуется верификация! Отправьте фото документов и дождитесь подтверждения администратора.",
                    "uz": "⚠️ Verifikatsiya talab etiladi! Hujjatlar rasmini yuboring va tasdiqni kuting.",
                    "en": "⚠️ Verification required! Send document photos and wait for admin approval.",
                }
                await callback.answer(msgs[lang], show_alert=True)
                return

            if (balance or 0) < MIN_BALANCE_TO_ACCEPT:
                await callback.answer(
                    "⚠️ Недостаточно средств на балансе. Пополните баланс, чтобы принимать заказы.",
                    show_alert=True,
                )
                return

            async with db.execute(
                "SELECT status, passenger_id, pickup, destination FROM orders WHERE order_id = ?", (order_id,)
            ) as cur:
                order_row = await cur.fetchone()

            if not order_row:
                await callback.answer("❌ Заказ не найден в базе данных!", show_alert=True)
                return

            status, passenger_id, pickup, destination = order_row
            if passenger_id == driver_id:
                await callback.answer("❌ Нельзя принять собственный заказ.", show_alert=True)
                return
            if status != "pending":
                await callback.answer("❌ Этот заказ уже занят другим водителем или отменен!", show_alert=True)
                return

            cur = await db.execute(
                "UPDATE orders SET driver_id = ?, status = 'accepted' WHERE order_id = ? AND status = 'pending'",
                (driver_id, order_id),
            )
            if cur.rowcount == 0:
                await callback.answer("❌ Этот заказ только что был принят другим водителем!", show_alert=True)
                return

            await db.commit()

        # Обновляем исходное сообщение (канал / список свободных заказов)
        try:
            status_line = f"\n\n✅ <b>СТАТУС: Заказ принят водителем {esc(first_name)}</b>"
            if callback.message.text:
                await callback.message.edit_text(esc(callback.message.text) + status_line, reply_markup=None)
            elif callback.message.caption:
                await callback.message.edit_caption(caption=esc(callback.message.caption) + status_line, reply_markup=None)
        except Exception as e:
            logger.error(f"Не удалось обновить статус заказа в канале: {e}")

        await callback.answer(f"✅ Вы успешно приняли заказ #{order_id}!", show_alert=True)

        t = T(lang)
        driver_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=t["finish_trip_btn"])]], resize_keyboard=True
        )
        driver_msg = {
            "ru": f"🚖 <b>Вы приняли заказ #{order_id}</b>\n📍 Откуда: {esc(pickup)}\n🏁 Куда: {esc(destination)}\n\nКогда доставите пассажира, нажмите кнопку ниже:",
            "uz": f"🚖 <b>Siz #{order_id}-buyurtmani qabul qildingiz</b>\n📍 Qayerdan: {esc(pickup)}\n🏁 Qayerga: {esc(destination)}\n\nYo'lovchini manzilga yetkazgach, quyidagi tugmani bosing:",
            "en": f"🚖 <b>You accepted order #{order_id}</b>\n📍 From: {esc(pickup)}\n🏁 To: {esc(destination)}\n\nTap the button below once you complete the trip:",
        }
        await bot.send_message(driver_id, driver_msg[lang], reply_markup=driver_kb)

        # Запрашиваем геопозицию у пассажира
        location_markup = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Отправить мою геопозицию", request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        try:
            await bot.send_message(
                passenger_id,
                "🚗 Водитель принял ваш заказ! Отправьте свою текущую геопозицию для построения маршрута.",
                reply_markup=location_markup,
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить пассажира {passenger_id}: {e}")

    except Exception as e:
        logger.error(f"Ошибка в хендлере принятия заказа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при принятии заказа. Попробуйте еще раз.", show_alert=True)


# =====================================================================
# 11. ГЕОПОЗИЦИЯ, ЗАВЕРШЕНИЕ ПОЕЗДКИ И SOS
# =====================================================================

@router.message(F.location)
async def passenger_location_receiver(message: Message) -> None:
    passenger_id = message.from_user.id
    lat, lon = message.location.latitude, message.location.longitude

    row = await db_fetchone(
        "SELECT order_id, driver_id FROM orders WHERE passenger_id = ? AND status IN ('accepted', 'active') "
        "ORDER BY order_id DESC LIMIT 1",
        (passenger_id,),
    )
    role, lang = await get_role_lang(passenger_id)
    if not row:
        await message.answer("⚠️ У вас нет активного заказа.", reply_markup=get_main_menu(role, lang))
        return

    order_id, driver_id = row
    await db_execute("UPDATE orders SET status = 'active' WHERE order_id = ?", (order_id,))

    yandex_url = f"https://yandex.com/maps/?rtext=~{lat},{lon}&rtt=auto"
    driver_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚨 ТРЕВОГА (SOS)", callback_data=f"trip_sos_{order_id}")],
            [InlineKeyboardButton(text="🏁 Завершить поездку", callback_data=f"trip_finish_{order_id}")],
        ]
    )
    try:
        await bot.send_message(
            driver_id,
            f"📍 Геопозиция пассажира по заказу #{order_id}!\n\n"
            f'🔗 <a href="{html.escape(yandex_url)}">Открыть маршрут в Яндекс Картах</a>',
            reply_markup=driver_markup,
        )
        await bot.send_location(driver_id, latitude=lat, longitude=lon)
    except Exception as e:
        logger.error(f"Не удалось отправить геопозицию водителю {driver_id}: {e}")

    passenger_markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=T(lang)["sos_btn"], callback_data=f"trip_sos_{order_id}")]]
    )
    await message.answer("✅ Геопозиция передана водителю.", reply_markup=get_main_menu(role, lang))
    await message.answer("🚨 В случае опасности нажмите кнопку ниже:", reply_markup=passenger_markup)


async def finish_order(order_id: int, user_id: Optional[int] = None, price: Optional[float] = None):
    """Завершает заказ и списывает комиссию с водителя (в одной транзакции).
    Возвращает (код, passenger_id, driver_id, fee, new_balance)."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT passenger_id, driver_id, status FROM orders WHERE order_id = ?", (order_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return "not_found", None, None, 0.0, 0.0

        p_id, d_id, status = row
        if user_id is not None and user_id != d_id:
            return "forbidden", p_id, d_id, 0.0, 0.0
        if status == "completed":
            return "done", p_id, d_id, 0.0, 0.0
        if status not in ("accepted", "active"):
            return "invalid", p_id, d_id, 0.0, 0.0

        price = float(price or 0)
        fee = round(price * COMMISSION_PERCENT / 100, 2)

        cur = await db.execute(
            "UPDATE orders SET status = 'completed', price = ?, commission = ? "
            "WHERE order_id = ? AND status IN ('accepted', 'active')",
            (price, fee, order_id),
        )
        if cur.rowcount == 0:
            return "done", p_id, d_id, 0.0, 0.0

        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (fee, d_id))
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (d_id,)) as cur2:
            b_row = await cur2.fetchone()
        await db.commit()

    logger.info(f"Заказ #{order_id} завершен: цена {price}, комиссия {fee}, водитель {d_id}")
    return "ok", p_id, d_id, fee, (b_row[0] if b_row else 0.0)


async def notify_trip_finished(
    order_id: int, p_id: Optional[int], d_id: Optional[int], price: float, fee: float, balance: float
) -> None:
    for uid, key in ((d_id, "trip_done_driver"), (p_id, "trip_done_passenger")):
        if not uid:
            continue
        role, lang = await get_role_lang(uid)
        t = T(lang)
        cur = t["currency"]
        text = t[key].format(
            id=order_id,
            fare=f"{price:,.0f} {cur}",
            percent=f"{COMMISSION_PERCENT:g}",
            fee=f"{fee:,.0f} {cur}",
            balance=f"{balance:,.0f} {cur}",
        )
        try:
            await bot.send_message(uid, text, reply_markup=get_main_menu(role, lang))
        except Exception as e:
            logger.error(f"Не удалось уведомить {uid} о завершении поездки: {e}")


async def ask_trip_price(user_id: int, order_id: int, state: FSMContext) -> None:
    lang = await get_lang(user_id)
    await state.clear()
    await state.update_data(finish_order_id=order_id)
    await state.set_state(DriverStates.waiting_for_trip_price)
    await bot.send_message(
        user_id,
        T(lang)["ask_price"].format(percent=f"{COMMISSION_PERCENT:g}"),
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(F.text.in_(texts("finish_trip_btn")))
async def driver_finish_trip_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    driver_id = message.from_user.id
    lang = await get_lang(driver_id)

    row = await db_fetchone(
        "SELECT order_id FROM orders WHERE driver_id = ? AND status IN ('accepted', 'active') "
        "ORDER BY order_id DESC LIMIT 1",
        (driver_id,),
    )
    if not row:
        await message.answer(T(lang)["no_active_trip"], reply_markup=get_main_menu("driver", lang))
        return
    await ask_trip_price(driver_id, row[0], state)


@router.callback_query(F.data.startswith("trip_finish_"))
async def trip_finish_handler(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split("_")[2])
    row = await db_fetchone("SELECT driver_id, status FROM orders WHERE order_id = ?", (order_id,))

    if not row:
        await callback.answer("⚠️ Ошибка: поездка не найдена.", show_alert=True)
        return
    if row[0] != callback.from_user.id:
        await callback.answer("⛔ Завершить поездку может только водитель.", show_alert=True)
        return
    if row[1] not in ("accepted", "active"):
        await callback.answer("ℹ️ Эта поездка уже завершена.", show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()
    await ask_trip_price(callback.from_user.id, order_id, state)


@router.message(DriverStates.waiting_for_trip_price, F.text)
async def process_trip_price(message: Message, state: FSMContext) -> None:
    driver_id = message.from_user.id
    lang = await get_lang(driver_id)
    t = T(lang)

    clean = message.text.replace(" ", "").replace(",", "")
    if not clean.isdigit() or not (0 < int(clean) <= 100_000_000):
        await message.answer(t["price_err"])
        return

    data = await state.get_data()
    order_id = data.get("finish_order_id")
    await state.clear()

    code, p_id, d_id, fee, balance = await finish_order(order_id, driver_id, float(clean))
    if code != "ok":
        await message.answer(t["no_active_trip"], reply_markup=get_main_menu("driver", lang))
        return
    await notify_trip_finished(order_id, p_id, d_id, float(clean), fee, balance)


@router.callback_query(F.data.startswith("trip_sos_"))
async def trip_sos_callback(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split("_")[2])
    row = await db_fetchone(
        "SELECT passenger_id, driver_id, status FROM orders WHERE order_id = ?", (order_id,)
    )
    if not row or callback.from_user.id not in (row[0], row[1]) or row[2] not in ("accepted", "active"):
        await callback.answer("⚠️ Поездка не активна.", show_alert=True)
        return

    lang = await get_lang(callback.from_user.id)
    await state.update_data(sos_order_id=order_id)
    await state.set_state(OrderStates.waiting_for_sos_reason)
    await callback.message.answer(T(lang)["sos_ask"])
    await callback.answer()


async def user_label(uid: Optional[int]) -> str:
    if not uid:
        return "—"
    row = await db_fetchone("SELECT first_name, last_name, phone FROM users WHERE user_id = ?", (uid,))
    if not row:
        return f"ID <code>{uid}</code>"
    name = esc(f"{row[0] or ''} {row[1] or ''}".strip() or "—")
    return f"{name}, <code>{esc(row[2] or '—')}</code>, ID <code>{uid}</code>"


@router.message(OrderStates.waiting_for_sos_reason, F.text)
async def process_sos_reason(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    order_id = data.get("sos_order_id")
    user_id = message.from_user.id
    role, lang = await get_role_lang(user_id)

    order = await db_fetchone(
        "SELECT passenger_id, driver_id, pickup, destination FROM orders WHERE order_id = ?", (order_id,)
    )
    if not order:
        await message.answer("⚠️ Заказ не найден.", reply_markup=get_main_menu(role, lang))
        return

    p_id, d_id, pickup, destination = order
    admin_text = (
        f"🚨🚨 <b>ТРЕВОГА (SOS) по заказу #{order_id}</b>\n\n"
        f"⚠️ Сигнал от: {await user_label(user_id)}\n"
        f"👤 Пассажир: {await user_label(p_id)}\n"
        f"🚖 Водитель: {await user_label(d_id)}\n"
        f"📍 Откуда: {esc(pickup)}\n🏁 Куда: {esc(destination)}\n\n"
        f"💬 <b>Сообщение:</b>\n{esc(message.text)}"
    )
    try:
        await bot.send_message(ADMIN_ID, admin_text)
    except Exception as e:
        logger.error(f"Не удалось отправить SOS админу: {e}")

    await message.answer(T(lang)["sos_sent"], reply_markup=get_main_menu(role, lang))


# =====================================================================
# 12. ПОПОЛНЕНИЕ БАЛАНСА (ЧЕК -> АДМИН -> СУММА)
# =====================================================================

@router.message(F.text.in_(texts("topup")))
async def driver_topup_menu(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id)
    await message.answer(
        T(lang)["topup_instructions"].format(card=CARD_NUMBER, holder=CARD_HOLDER, phone=SUPPORT_PHONE)
    )
    await state.set_state(DriverStates.waiting_for_receipt)


@router.message(DriverStates.waiting_for_receipt, F.photo)
async def driver_receipt_receiver(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    role, lang = await get_role_lang(user_id)
    row = await db_fetchone("SELECT phone FROM users WHERE user_id = ?", (user_id,))
    phone = esc(row[0]) if row and row[0] else "Не указан"
    username = f"@{esc(message.from_user.username)}" if message.from_user.username else "Не указан"

    caption = (
        "💰 <b>Запрос на пополнение баланса!</b>\n\n"
        f"👤 <b>От:</b> {esc(message.from_user.full_name or 'Не указано')}\n"
        f"🔗 <b>Username:</b> {username}\n"
        f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
        "👇 Подтвердите платеж и укажите сумму:"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить пополнение", callback_data=f"topup_accept_{user_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"topup_reject_{user_id}")],
        ]
    )
    try:
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=caption, reply_markup=kb)
        await message.answer(T(lang)["topup_sent"], reply_markup=get_main_menu(role, lang))
    except Exception as e:
        logger.error(f"Не удалось отправить чек админу: {e}")
        await message.answer("⚠️ Не удалось отправить чек. Попробуйте позже.", reply_markup=get_main_menu(role, lang))
    await state.clear()


@router.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("topup_accept_"))
async def admin_accept_topup_callback(callback: CallbackQuery, state: FSMContext) -> None:
    target_user_id = int(callback.data.split("_")[2])
    await state.update_data(topup_target_id=target_user_id)
    await state.set_state(AdminTopUpStates.waiting_for_amount)
    await callback.message.answer(
        f"✍️ Введите сумму пополнения для пользователя (ID: <code>{target_user_id}</code>) цифрами:\n"
        f"<i>Например: 30000 (минимум {MIN_TOPUP:,})</i>"
    )
    await callback.answer()


@router.message(F.from_user.id == ADMIN_ID, AdminTopUpStates.waiting_for_amount, F.text)
async def admin_enter_amount_handler(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    target_user_id = data.get("topup_target_id")
    if not target_user_id:
        await state.clear()
        await message.reply("⚠️ Ошибка: ID пользователя потерян. Нажмите кнопку подтверждения заново.")
        return

    clean = message.text.replace(" ", "").replace(",", "")
    if not clean.isdigit():
        await message.reply("❌ Сумма должна состоять только из цифр (например: 30000). Введите ещё раз:")
        return

    amount = float(clean)
    if amount < MIN_TOPUP:
        await message.reply(f"⚠️ <b>Минимальная сумма пополнения — {MIN_TOPUP:,} сум!</b> Введите сумму ещё раз:")
        return

    await state.clear()
    await db_execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_user_id))
    row = await db_fetchone("SELECT lang, balance FROM users WHERE user_id = ?", (target_user_id,))
    user_lang = row[0] if row and row[0] in LANGS else "ru"
    new_balance = row[1] if row and row[1] is not None else amount

    success_texts = {
        "ru": f"✅ <b>Ваш баланс успешно пополнен!</b>\n\n💳 Зачислено: <b>{amount:,.0f} сум</b>\n💰 Текущий баланс: <b>{new_balance:,.0f} сум</b>",
        "uz": f"✅ <b>Hisobingiz muvaffaqiyatli to'ldirildi!</b>\n\n💳 Qo'shildi: <b>{amount:,.0f} so'm</b>\n💰 Joriy balans: <b>{new_balance:,.0f} so'm</b>",
        "en": f"✅ <b>Your balance has been topped up!</b>\n\n💳 Added: <b>{amount:,.0f} UZS</b>\n💰 Current balance: <b>{new_balance:,.0f} UZS</b>",
    }
    try:
        await bot.send_message(target_user_id, success_texts[user_lang])
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {target_user_id} о пополнении: {e}")

    await message.reply(f"✅ Баланс пользователя <code>{target_user_id}</code> пополнен на <b>{amount:,.0f} сум</b>!")


@router.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("topup_reject_"))
async def admin_reject_topup_callback(callback: CallbackQuery) -> None:
    target_user_id = int(callback.data.split("_")[2])
    reject_texts = {
        "ru": "❌ <b>К сожалению, ваш платеж был отклонен администрацией.</b>\nЕсли у вас есть вопросы, обратитесь в поддержку /help.",
        "uz": "❌ <b>Afsuski, to'lovingiz ma'muriyat tomonidan rad etildi.</b>\nSavollar bo'lsa, /help orqali murojaat qiling.",
        "en": "❌ <b>Unfortunately, your payment was rejected by administration.</b>\nIf you have questions, contact support via /help.",
    }
    user_lang = await get_lang(target_user_id)
    try:
        await bot.send_message(target_user_id, reject_texts[user_lang])
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя об отклонении платежа: {e}")

    try:
        await callback.message.edit_caption(
            caption=f"{esc(callback.message.caption)}\n\n❌ <b>СТАТУС: Отклонено администратором</b>", reply_markup=None
        )
    except Exception as e:
        logger.error(f"Ошибка при обновлении сообщения: {e}")
    await callback.answer("Платеж отклонен.", show_alert=True)


# =====================================================================
# 13. ВЕРИФИКАЦИЯ ВОДИТЕЛЕЙ
# =====================================================================

@router.message(F.text.in_(texts("verification")))
async def driver_verification_menu(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id)
    await message.answer(T(lang)["verification_instructions"])
    await state.set_state(DriverStates.waiting_for_verification_photo)


@router.message(DriverStates.waiting_for_verification_photo, F.photo)
async def driver_verification_receiver(message: Message, state: FSMContext) -> None:
    photo_id = message.photo[-1].file_id
    driver_id = message.from_user.id

    await db_execute("UPDATE users SET verification_photo = ? WHERE user_id = ?", (photo_id, driver_id))
    row = await db_fetchone("SELECT lang, first_name, last_name, phone FROM users WHERE user_id = ?", (driver_id,))
    lang = row[0] if row and row[0] in LANGS else "ru"
    full_name = (f"{row[1] or ''} {row[2] or ''}".strip() if row else "") or "Не указано"
    phone = row[3] if row and row[3] else "Не указан"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve_driver_{driver_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_driver_{driver_id}"),
        ]]
    )
    try:
        await bot.send_photo(
            ADMIN_ID,
            photo_id,
            caption=(
                "📸 <b>Запрос на верификацию водителя</b>\n\n"
                f"👤 Имя: {esc(full_name)}\n"
                f"📞 <b>Телефон:</b> <code>{esc(phone)}</code>\n"
                f"🆔 Telegram ID: <code>{driver_id}</code>"
            ),
            reply_markup=kb,
        )
    except Exception as e:
        logger.error(f"Не удалось отправить верификацию админу: {e}")

    await message.answer(T(lang)["verification_sent"], reply_markup=get_main_menu("driver", lang))
    await state.clear()


@router.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("approve_driver_"))
async def approve_driver_callback(callback: CallbackQuery) -> None:
    driver_id = int(callback.data.split("_")[2])
    await db_execute("UPDATE users SET verified = 1 WHERE user_id = ?", (driver_id,))
    lang = await get_lang(driver_id)

    try:
        await callback.message.edit_caption(
            caption=f"{esc(callback.message.caption)}\n\n✅ <b>ПОДТВЕРЖДЕНО АДМИНИСТРАТОРОМ</b>", reply_markup=None
        )
    except Exception as e:
        logger.error(f"Не удалось обновить подпись: {e}")
    await callback.answer("Водитель верифицирован!")

    notify = {
        "ru": "✅ Ваша верификация подтверждена администратором! Теперь ваш аккаунт имеет статус «Верифицирован».",
        "uz": "✅ Verifikatsiyangiz administrator tomonidan tasdiqlandi! Endi hisobingiz «Tasdiqlangan» maqomiga ega.",
        "en": "✅ Your verification has been approved by the admin! Your account is now marked as Verified.",
    }
    try:
        await bot.send_message(driver_id, notify[lang])
    except Exception as e:
        logger.error(f"Не удалось уведомить водителя {driver_id}: {e}")


@router.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("reject_driver_"))
async def reject_driver_callback(callback: CallbackQuery) -> None:
    driver_id = int(callback.data.split("_")[2])
    await db_execute("UPDATE users SET verified = 0, verification_photo = NULL WHERE user_id = ?", (driver_id,))
    lang = await get_lang(driver_id)

    try:
        await callback.message.edit_caption(
            caption=f"{esc(callback.message.caption)}\n\n❌ <b>ОТКЛОНЕНО АДМИНИСТРАТОРОМ</b>", reply_markup=None
        )
    except Exception as e:
        logger.error(f"Не удалось обновить подпись: {e}")
    await callback.answer("Заявка отклонена.")

    notify = {
        "ru": "❌ Ваша заявка на верификацию отклонена. Пожалуйста, отправьте более четкое фото документов.",
        "uz": "❌ Verifikatsiya so'rovingiz rad etildi. Iltimos, hujjatlarning aniqroq rasmini qayta yuboring.",
        "en": "❌ Your verification request was rejected. Please submit a clearer photo of your documents.",
    }
    try:
        await bot.send_message(driver_id, notify[lang])
    except Exception as e:
        logger.error(f"Не удалось уведомить водителя {driver_id}: {e}")


# Защита: callback'и админских кнопок от не-админов
@router.callback_query(
    F.data.startswith(("approve_driver_", "reject_driver_", "topup_accept_", "topup_reject_",
                       "admin_", "support_reply_"))
)
async def deny_non_admin(callback: CallbackQuery) -> None:
    await callback.answer("⛔ Нет доступа", show_alert=True)


# =====================================================================
# 14. ВЕБ-СЕРВЕР ДЛЯ RENDER И ЗАПУСК
# =====================================================================

async def handle_ping(request: web.Request) -> web.Response:
    return web.Response(text="Yo'ldosh Taxi Bot is active and running!")


async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"AIOHTTP веб-сервер запущен на порту {PORT}")
    return runner


async def main() -> None:
    await init_db()

    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="🚀 Запустить бота / Главное меню"),
            BotCommand(command="help", description="❓ Служба поддержки"),
        ])
    except Exception as e:
        logger.warning(f"Не удалось установить команды бота: {e}")

    dp.include_router(router)
    runner = await start_web_server()

    logger.info("Запуск опроса Telegram API...")
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
