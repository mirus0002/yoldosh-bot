#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================================================
Project: Yo'ldosh Taxi Telegram Bot (Full Production Version)
Author: Mirxamidjon Mirbadalov
Stack: Python 3.14, aiogram 3.x, aiosqlite, aiohttp
Description: Full-featured taxi booking system with all requested features,
             admin controls, stats, broadcast, free orders, and aiohttp web-server.
=============================================================================
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
import aiosqlite
from aiohttp import web

# =====================================================================
# 1. КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
# =====================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("yoldosh_taxi_production.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("YoldoshTaxiProductionSystem")

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("ОШИБКА: Переменная окружения BOT_TOKEN не задана в настройках Render!")

ADMIN_PASSWORD = "2009mmmm"
ADMIN_ID = 7543501900
CHANNEL_USERNAME = "@Yoldosh_Taxi_Official"
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

DB_NAME = "yoldosh_taxi_production.db"


# =====================================================================
# 2. МНОГОЯЗЫЧНЫЕ СЛОВАРИ (RU, UZ, EN)
# =====================================================================

LANGS: Dict[str, Dict[str, str]] = {
    "ru": {
        "welcome": "🚖 Добро пожаловать в официальную систему заказа такси **Yo'ldosh Taxi**!",
        "choose_action": "Пожалуйста, выберите необходимое действие в меню:",
        "become_driver": "🚖 Стать водителем",
        "driver_activated": "✅ Режим водителя успешно активирован! Вам доступны функции для работы.",
        "profile_title": "👤 **Ваш профиль в системе Yo'ldosh Taxi**",
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
        "cancel_order_btn": "❌ Отменить заказ",
        "accept_order_btn": "🚖 Принять заказ",
        "send_location_btn": "📍 Отправить мою геопозицию",
        "sos_btn": "🚨 ТРЕВОГА (SOS)",
        "finish_trip_btn": "🏁 Завершить поездку",
        "delete_profile_btn": "❌ Удалить профиль",
        "how_to_use_text": (
            "📖 **Руководство пользователя Yo'ldosh Taxi**\n\n"
            "1️⃣ **Для пассажиров:**\n"
            "• Нажмите «🚕 Заказать такси» или «🕒 Заказать на потом».\n"
            "• Укажите точку отправления, пункт назначения и комментарий при необходимости.\n"
            "• Ожидайте, пока свободный водитель примет ваш заказ.\n\n"
            "2️⃣ **Для водителей:**\n"
            "• Нажмите «🚖 Стать водителем», пройдите верификацию (отправьте фото прав/паспорта) и пополните баланс.\n"
            "• В разделе «🚖 Свободные заказы» просматривайте и принимайте заявки.\n\n"
            "🚨 Во время поездки доступна кнопка экстренной связи **SOS**.\n"
            "📞 Служба поддержки: **+998 91 773-51-52**"
        ),
        "topup_instructions": (
            "💳 **Пополнение баланса водителя**\n\n"
            "Переведите необходимую сумму на банковскую карту:\n"
            "`4023060518850838`\n"
            "Получатель: **MIRXAMIDJON MIRBADALOV**\n"
            "Телефон поддержки: **+998 91 773-51-52**\n\n"
            "📸 После совершения перевода отправьте скриншот или фото чека в этот чат."
        ),
        "verification_instructions": (
            "📸 **Верификация профиля водителя**\n\n"
            "Пожалуйста, отправьте в чат четкое фото ваших водительских прав или паспорта "
            "для прохождения проверки администрацией."
        )
    },
    "uz": {
        "welcome": "🚖 **Yo'ldosh Taxi** rasmiy buyurtma berish tizimiga xush kelibsiz!",
        "choose_action": "Iltimos, quyidagi menyudan kerakli amalni tanlang:",
        "become_driver": "🚖 Haydovchi bo'lish",
        "driver_activated": "✅ Haydovchi rejimi muvaffaqiyatli yoqildi! Endi siz buyurtmalarni qabul qilishingiz mumkin.",
        "profile_title": "👤 **Yo'ldosh Taxi tizimidagi profilingiz**",
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
        "cancel_order_btn": "❌ Buyurtmani bekor qilish",
        "accept_order_btn": "🚖 Buyurtmani qabul qilish",
        "send_location_btn": "📍 Mening geolyatsiyamni yuborish",
        "sos_btn": "🚨 TREVOGA (SOS)",
        "finish_trip_btn": "🏁 Safarni yakunlash",
        "delete_profile_btn": "❌ Profilni o'chirish",
        "how_to_use_text": (
            "📖 **Yo'ldosh Taxi foydalanish qo'llanmasi**\n\n"
            "1️⃣ **Yo'lovchilar uchun:**\n"
            "• «🚕 Taksi chaqirish» yoki «🕒 Keyinga buyurtma berish» tugmasini bosing.\n"
            "• Qayerdan va qayerga borishingizni hamda izohni kiriting.\n"
            "• Haydovchi buyurtmangizni qabul qilishini kuting.\n\n"
            "2️⃣ **Haydovchilar uchun:**\n"
            "• «🚖 Haydovchi bo'lish»ni tanlang, verifikatsiyadan o'ting (guvohnoma/pasport rasmini yuboring) va balansni to'ldiring.\n"
            "• «🚖 Bo'sh buyurtmalar» bo'limidan buyurtmalarni qabul qiling.\n\n"
            "🚨 Safar davomida favqulodda **SOS** tugmasi ishlaydi.\n"
            "📞 Qo'llab-quvvatlash: **+998 91 773-51-52**"
        ),
        "topup_instructions": (
            "💳 **Haydovchi balansini to'ldirish**\n\n"
            "Kerakli summani quyidagi bank kartasiga o'tkazing:\n"
            "`4023060518850838`\n"
            "Qabul qiluvchi: **MIRXAMIDJON MIRBADALOV**\n"
            "Qo'llab-quvvatlash: **+998 91 773-51-52**\n\n"
            "📸 O'tkazmadan so'ng chek yoki skrinshotni ushbu chatga yuboring."
        ),
        "verification_instructions": (
            "📸 **Haydovchi profilini verifikatsiya qilish**\n\n"
            "Ma'muriyat tomonidan tekshiruvdan o'tish uchun haydovchilik guvohnomasi yoki pasportingiz rasmini yuboring."
        )
    },
    "en": {
        "welcome": "🚖 Welcome to the official **Yo'ldosh Taxi** ordering system!",
        "choose_action": "Please choose the required action from the menu below:",
        "become_driver": "🚖 Become a Driver",
        "driver_activated": "✅ Driver mode successfully activated! You can now accept orders.",
        "profile_title": "👤 **Your Yo'ldosh Taxi System Profile**",
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
        "cancel_order_btn": "❌ Cancel Order",
        "accept_order_btn": "🚖 Accept Order",
        "send_location_btn": "📍 Send My Location",
        "sos_btn": "🚨 SOS EMERGENCY",
        "finish_trip_btn": "🏁 Complete Trip",
        "delete_profile_btn": "❌ Delete Profile",
        "how_to_use_text": (
            "📖 **Yo'ldosh Taxi User Guide**\n\n"
            "1️⃣ **For Passengers:**\n"
            "• Tap «🚕 Order Taxi» or «🕒 Order for Later».\n"
            "• Enter your pickup location, destination, and optional comment.\n"
            "• Wait for an available driver to accept your ride.\n\n"
            "2️⃣ **For Drivers:**\n"
            "• Choose «🚖 Become a Driver», pass verification (send license/passport photo), and top up your balance.\n"
            "• Browse and accept rides in the «🚖 Free Orders» section.\n\n"
            "🚨 An emergency **SOS** button is available during active trips.\n"
            "📞 Support: **+998 91 773-51-52**"
        ),
        "topup_instructions": (
            "💳 **Driver Balance Top-Up**\n\n"
            "Transfer the required amount to the bank card:\n"
            "`4023060518850838`\n"
            "Recipient: **MIRXAMIDJON MIRBADALOV**\n"
            "Support Phone: **+998 91 773-51-52**\n\n"
            "📸 After the transfer, send a screenshot or receipt photo to this chat."
        ),
        "verification_instructions": (
            "📸 **Driver Profile Verification**\n\n"
            "Please send a clear photo of your driver's license or passport for verification."
        )
    }
}


# =====================================================================
# 3. ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ (AIOSQLITE)
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
        await db.commit()
    logger.info("База данных успешно инициализирована.")


# =====================================================================
# 4. FSM СОСТОЯНИЯ
# =====================================================================

class OrderStates(StatesGroup):
    waiting_for_pickup = State()
    waiting_for_destination = State()
    waiting_for_schedule_time = State()
    waiting_for_comment = State()
    waiting_for_sos_reason = State()  # <-- Новое состояние для фиксации причины тревоги


class DriverStates(StatesGroup):
    waiting_for_verification_photo = State()
    waiting_for_receipt = State()


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


# =====================================================================
# СЛУЖБА ПОДДЕРЖКИ (ОБРАЩЕНИЯ ПОЛЬЗОВАТЕЛЕЙ И ОТВЕТ АДМИНА)
# =====================================================================

@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.set_state(SupportStates.waiting_for_support_message)
    await message.answer(
        "🛠 <b>Служба поддержки Yo'ldosh Taxi</b>\n\n"
        "Напишите ваше сообщение, вопрос или проблему одним текстом, и оно будет мгновенно передано администрации. Мы ответим вам в ближайшее время!",
        parse_mode="HTML"
    )


@router.message(SupportStates.waiting_for_support_message, F.text)
async def process_support_message(message: Message, state: FSMContext) -> None:
    try:
        user_id = message.from_user.id
        username = f"@{html.escape(message.from_user.username)}" if message.from_user.username else "Не указан"
        full_name = html.escape(message.from_user.full_name or "Не указано")
        user_text = html.escape(message.text)

        phone = "Не указан в базе"
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    phone = html.escape(str(row[0]))

        admin_text = (
            f"📩 <b>Новое обращение в поддержку!</b>\n\n"
            f"👤 <b>От:</b> {full_name}\n"
            f"🔗 <b>Username:</b> {username}\n"
            f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
            f"💬 <b>Сообщение:</b>\n{user_text}"
        )

        reply_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💬 Ответить анонимно", callback_data=f"support_reply_{user_id}")]
            ]
        )

        await bot.send_message(ADMIN_ID, admin_text, reply_markup=reply_kb, parse_mode="HTML")
        await message.answer("✅ Ваше сообщение успешно отправлено в службу поддержки! Ожидайте ответа.")
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение в поддержку админу: {e}")
        await message.answer("⚠️ Не удалось связаться с поддержкой. Попробуйте позже.")
    finally:
        # ГАРАНТИРОВАННЫЙ СБРОС СОСТОЯНИЯ — ЗАЩИТА ОТ ЗАВИСАНИЙ
        await state.clear()


@router.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("support_reply_"))
async def admin_start_reply_callback(callback: CallbackQuery, state: FSMContext) -> None:
    target_user_id = int(callback.data.split("_")[2])
    await state.update_data(reply_target_id=target_user_id)
    await state.set_state(AdminReplyStates.waiting_for_reply_text)
    await callback.message.answer(
        f"✍️ Напишите ответ для пользователя (ID: <code>{target_user_id}</code>).\n"
        f"Ваше сообщение будет отправлено от имени бота:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(F.from_user.id == ADMIN_ID, AdminReplyStates.waiting_for_reply_text, F.text)
async def admin_send_button_reply(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    target_user_id = data.get("reply_target_id")
    await state.clear()

    if not target_user_id:
        await message.reply("⚠️ Ошибка: ID получателя потерян. Нажмите кнопку «Ответить» ещё раз.")
        return

    safe_response = html.escape(message.text)

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (int(target_user_id),)) as cursor:
            row = await cursor.fetchone()
    user_lang = row[0] if row and row[0] else "ru"

    headers = {
        "ru": "🛠 <b>Ответ от службы поддержки Yo'ldosh Taxi:</b>",
        "uz": "🛠 <b>Yo'ldosh Taxi qo'llab-quvvatlash xizmatidan javob:</b>",
        "en": "🛠 <b>Response from Yo'ldosh Taxi Support:</b>"
    }
    header = headers.get(user_lang, headers["ru"])

    try:
        await bot.send_message(
            int(target_user_id),
            f"{header}\n\n{safe_response}",
            parse_mode="HTML"
        )
        await message.reply("✅ Ответ анонимно доставлен пользователю от имени бота!")
    except Exception as e:
        logger.error(f"Не удалось отправить ответ пользователю {target_user_id}: {e}")
        await message.reply(f"⚠️ Не удалось отправить сообщение пользователю: {html.escape(str(e))}")


# =====================================================================
# ШАГ 1: КОМАНДА /START (ПРОВЕРКА ЯЗЫКА И БАЗЫ)
# =====================================================================

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    
    # Проверяем, есть ли пользователь в базе и выбран ли у него язык
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang, first_name FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            
    # Если пользователя нет в базе или у него не выбран язык — просим выбрать язык
    if not row or not row[0]:
        lang_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")
            ]
        ])
        await message.answer(
            "Assalomu alaykum! Iltimos, tilni tanlang:\n\n"
            "Здравствуйте! Пожалуйста, выберите язык:\n\n"
            "Hello! Please select a language:",
            reply_markup=lang_kb
        )
        return

    # Если язык есть, но не введено имя (не закончена регистрация) -> запускаем регистрацию
    if not row[1]:
        await start_registration(message, state)
        return

    # Если пользователь полностью зарегистрирован -> открываем главное меню
    lang = row[0]
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,)) as cursor:
            role_row = await cursor.fetchone()
            role = role_row[0] if role_row else "passenger"

    if lang == "uz":
        welcome_text = "Asosiy menyuga xush kelibsiz! 🎉"
    elif lang == "en":
        welcome_text = "Welcome to the main menu! 🎉"
    else:
        welcome_text = "Добро пожаловать в главное меню! 🎉"
        
    await message.answer(welcome_text, reply_markup=get_main_menu(role, lang))


# =====================================================================
# ШАГ 2: ОБРАБОТКА ВЫБОРА ЯЗЫКА И ЗАПУСК РЕГИСТРАЦИИ
# =====================================================================

@router.callback_query(F.data.startswith("lang_"))
async def process_language_selection(callback: CallbackQuery, state: FSMContext) -> None:
    selected_lang = callback.data.split("_")[1] # 'uz', 'ru' или 'en'
    user_id = callback.from_user.id
    
    # Сохраняем язык в базу данных
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO users (user_id, lang, role, balance, created_at) VALUES (?, ?, 'passenger', 0.0, datetime('now')) ON CONFLICT(user_id) DO UPDATE SET lang = ?",
            (user_id, selected_lang, selected_lang)
        )
        await db.commit()
        
    await callback.message.delete()
    
    # Запускаем ввод имени на выбранном языке
    await state.set_state(RegistrationStates.waiting_for_full_name)
    
    if selected_lang == "uz":
        text = "📝 **Ro'yxatdan o'tish**\n\nIltimos, **Ism va Familiyangizni** kiriting:"
    elif selected_lang == "en":
        text = "📝 **Registration**\n\nPlease enter your **First and Last Name**:"
    else:
        text = "📝 **Регистрация в системе**\n\nПожалуйста, введите ваши **Имя и Фамилию**:"
    
    await callback.message.answer(text, parse_mode="Markdown")


# =====================================================================
# ХЕНДЛЕРЫ РЕГИСТРАЦИИ (ИМЯ -> ВОЗРАСТ -> ТЕЛЕФОН)
# =====================================================================

async def start_registration(message: Message, state: FSMContext) -> None:
    await state.set_state(RegistrationStates.waiting_for_full_name)
    await message.answer(
        "📝 **Регистрация в системе**\n\nПожалуйста, введите ваши **Имя и Фамилию**:",
        parse_mode="Markdown"
    )

@router.message(RegistrationStates.waiting_for_full_name, F.text)
async def process_full_name(message: Message, state: FSMContext) -> None:
    full_name_parts = message.text.strip().split(maxsplit=1)
    first_name = full_name_parts[0]
    last_name = full_name_parts[1] if len(full_name_parts) > 1 else ""

    await state.update_data(first_name=first_name, last_name=last_name)
    await state.set_state(RegistrationStates.waiting_for_age)
    
    await message.answer(
        "🔢 Укажите ваш **возраст** цифрами (например: `25`):",
        parse_mode="Markdown"
    )

@router.message(RegistrationStates.waiting_for_age, F.text)
async def process_age(message: Message, state: FSMContext) -> None:
    if not message.text.isdigit():
        await message.answer("⚠️ Пожалуйста, введите возраст цифрами (например: `20`):")
        return

    age = int(message.text)
    await state.update_data(age=age)
    await state.set_state(RegistrationStates.waiting_for_phone)

    phone_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(
        "📞 Теперь отправьте ваш **номер телефона**, нажав на кнопку ниже или написав его вручную:",
        reply_markup=phone_kb,
        parse_mode="Markdown"
    )

@router.message(RegistrationStates.waiting_for_phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext) -> None:
    phone = message.contact.phone_number
    await save_user_and_finish(message, state, phone)

@router.message(RegistrationStates.waiting_for_phone, F.text)
async def process_phone_text(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    await save_user_and_finish(message, state, phone)

async def save_user_and_finish(message: Message, state: FSMContext, phone: str) -> None:
    user_id = message.from_user.id
    data = await state.get_data()
    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    age = data.get("age", 0)

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            UPDATE users 
            SET first_name = ?, last_name = ?, age = ?, phone = ? 
            WHERE user_id = ?
            """,
            (first_name, last_name, age, phone, user_id)
        )
        
        async with db.execute("SELECT role, lang FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            role, lang = row if row else ("passenger", "ru")
        await db.commit()

    if lang == "uz":
        success_text = "✅ **Ro'yxatdan o'tish muvaffaqiyatli yakunlandi!** Tizimga xush kelibsiz."
    elif lang == "en":
        success_text = "✅ **Registration successfully completed!** Welcome to the system."
    else:
        success_text = "✅ **Регистрация успешно завершена!** Добро пожаловать в систему."

    await message.answer(
        success_text,
        reply_markup=get_main_menu(role, lang),
        parse_mode="Markdown"
    )
    await state.clear()


# =====================================================================
# 5. КЛАВИАТУРЫ И ОБРАБОТЧИК КНОПКИ «КАК ПОЛЬЗОВАТЬСЯ»
# =====================================================================

def get_main_menu(role: str = "passenger", lang: str = "ru") -> ReplyKeyboardMarkup:
    t = LANGS.get(lang, LANGS["ru"])
    if role == "driver":
        return ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text=t["free_orders"]),
                    KeyboardButton(text=t["topup"]),
                ],
                [
                    KeyboardButton(text=t["profile"]),
                    KeyboardButton(text=t["balance"]),
                ],
                [
                    KeyboardButton(text=t["verification"]),
                    KeyboardButton(text=t["history"]),
                ],
                [
                    KeyboardButton(text=t["how_to_use"]),
                    KeyboardButton(text="🌐 Сменить язык / Jurnal")
                ],
            ],
            resize_keyboard=True,
        )
    else:
        return ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text=t["order_taxi"]),
                    KeyboardButton(text=t["order_later"]),
                ],
                [
                    KeyboardButton(text=t["profile"]),
                    KeyboardButton(text=t["balance"]),
                ],
                [
                    KeyboardButton(text=t["history"]),
                    KeyboardButton(text=t["become_driver"]),
                ],
                [
                    KeyboardButton(text=t["how_to_use"]),
                    KeyboardButton(text="🌐 Сменить язык / Jurnal")
                ],
            ],
            resize_keyboard=True,
        )


def get_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
                InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
            ]
        ]
    )


@router.message(F.text.in_([lang_dict["how_to_use"] for lang_dict in LANGS.values()]))
async def show_how_to_use(message: Message) -> None:
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row and row[0] else "ru"
            
    t = LANGS.get(lang, LANGS["ru"])
    await message.answer(t["how_to_use_text"], parse_mode="Markdown")


# =====================================================================
# 6. СТАРТ И ВЫБОР ЯЗЫКА / РЕГИСТРАЦИЯ
# =====================================================================

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Не указано"
    last_name = message.from_user.last_name or ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT role, lang, phone FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            
            # 1. Если пользователя вообще нет в базе — создаем запись БЕЗ языка и просим выбрать язык
            if not row:
                await db.execute(
                    "INSERT INTO users (user_id, role, lang, first_name, last_name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, "passenger", None, first_name, last_name, now),
                )
                await db.commit()
                
                # Показываем выбор языка (узбекский, русский, английский)
                await message.answer(
                    "Assalomu alaykum! Iltimos, tilni tanlang:\n\n"
                    "Здравствуйте! Пожалуйста, выберите язык:\n\n"
                    "Hello! Please select a language:",
                    reply_markup=get_language_keyboard()
                )
                return
            
            role, lang, phone = row

            # 2. Если язык еще не выбран — снова показываем кнопки выбора языка
            if not lang:
                await message.answer(
                    "Assalomu alaykum! Iltimos, tilni tanlang:\n\n"
                    "Здравствуйте! Пожалуйста, выберите язык:\n\n"
                    "Hello! Please select a language:",
                    reply_markup=get_language_keyboard()
                )
                return

            # 3. Если язык есть, но не указан телефон (регистрация не завершена) — просим телефон
            if not phone:
                phone_kb = ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="📱 Kontakt bilan bo'lishish", request_contact=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
                await message.answer(
                    f"**Yo'ldosh taxiga xush kelibsiz**, {first_name}!\n\n"
                    "Pastdagi tugmani bosing **yoki telefon raqamingizni o'zingiz tering** (misol uchun: `+998 91 773-51-52`):",
                    reply_markup=phone_kb,
                    parse_mode="Markdown"
                )
                await state.set_state(RegistrationStates.waiting_for_phone)
                return

            # 4. Если пользователь полностью зарегистрирован — открываем главное меню на его языке
            t = LANGS.get(lang, LANGS["ru"])
            await message.answer(
                f"{t['welcome']}\n\n{t['choose_action']}",
                reply_markup=get_main_menu(role, lang),
                parse_mode="Markdown",
            )


# =====================================================================
# ОБРАБОТКА ВЫБОРА ЯЗЫКА (КНОПКИ)
# =====================================================================

@router.callback_query(F.data.startswith("lang_"))
async def process_language_callback(callback: CallbackQuery, state: FSMContext) -> None:
    selected_lang = callback.data.split("_")[1] # 'uz', 'ru' или 'en'
    user_id = callback.from_user.id
    
    async with aiosqlite.connect(DB_NAME) as db:
        # Сохраняем выбранный язык в базу
        await db.execute(
            "UPDATE users SET lang = ? WHERE user_id = ?",
            (selected_lang, user_id)
        )
        await db.commit()
        
        # Проверяем статус пользователя (есть ли у него имя и роль)
        async with db.execute("SELECT role, first_name, phone FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            role = row[0] if row and row[0] else "passenger"
            first_name = row[1] if row else None
            has_phone = row[2] if row else None

    await callback.message.delete()
    
    # ЕСЛИ ПОЛЬЗОВАТЕЛЬ УЖЕ ЗАРЕГИСТРИРОВАН (у него есть имя в базе):
    # Просто меняем язык интерфейса и открываем главное меню, не трогая стейт!
    if first_name:
        t = LANGS.get(selected_lang, LANGS["ru"])
        await state.clear()
        await callback.message.answer(
            t["lang_changed"],
            reply_markup=get_main_menu(role, selected_lang)
        )
        return

    # ЕСЛИ ЭТО НОВЫЙ ПОЛЬЗОВАТЕЛЬ (имени нет) — запускаем регистрацию с шага ввода имени
    await state.set_state(RegistrationStates.waiting_for_full_name)
    
    if selected_lang == "uz":
        text = "📝 **Ro'yxatdan o'tish**\n\nIltimos, **Ism va Familiyangizni** kiriting:"
    elif selected_lang == "en":
        text = "📝 **Registration**\n\nPlease enter your **First and Last Name**:"
    else:
        text = "📝 **Регистрация в системе**\n\nПожалуйста, введите ваши **Имя и Фамилию**:"
        
    await callback.message.answer(text, parse_mode="Markdown")


# =====================================================================
# СОХРАНЕНИЕ КОНТАКТА
# =====================================================================

@router.message(RegistrationStates.waiting_for_phone, F.contact)
async def process_user_contact_button(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    phone = message.contact.phone_number

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id)
        )
        async with db.execute(
            "SELECT role, lang FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            role, lang = row if row else ("passenger", "ru")
        await db.commit()

    t = LANGS.get(lang, LANGS["ru"])
    
    success_text = {
        "uz": "✅ Ro'yxatdan o'tish muvaffaqiyatli yakunlandi!",
        "en": "✅ Registration successfully completed!",
        "ru": "✅ Регистрация успешно завершена!"
    }

    await message.answer(
        success_text.get(lang, success_text["ru"]),
        reply_markup=get_main_menu(role, lang)
    )
    await state.clear()

@router.message(F.text.func(lambda text: text and any(word in text.lower() for word in ["история", "safarlar", "tarixi"])))
async def show_trip_history(message: Message) -> None:
    user_id = message.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:
        # Узнаем выбранный язык пользователя из базы данных
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_lang = await cursor.fetchone()
            lang = user_lang[0] if user_lang and user_lang[0] in ["ru", "uz"] else "ru"

        # Ищем заказы
        async with db.execute(
            """
            SELECT order_id, pickup, destination, status, created_at 
            FROM orders 
            WHERE passenger_id = ? OR driver_id = ? 
            ORDER BY order_id DESC LIMIT 5
            """,
            (user_id, user_id)
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        if lang == "uz":
            await message.answer("📭 Sizda hali safarlar tarixi yo'q.")
        else:
            await message.answer("📭 У вас пока нет истории поездок.")
        return

    if lang == "uz":
        text = "📜 **Sizning oxirgi safarlaringiz tarixi:**\n\n"
    else:
        text = "📜 **История ваших последних поездок:**\n\n"

    for row in rows:
        order_id, pickup, destination, status, created_at = row
        
        if lang == "uz":
            status_text = {
                "pending": "⏳ Qidiruvda",
                "accepted": "🚗 Qabul qilingan",
                "completed": "✅ Yakunlangan",
                "cancelled": "❌ Bekor qilingan"
            }.get(status, status)

            text += (
                f"🆔 **Buyurtma #{order_id}**\n"
                f"📌 Holati: {status_text}\n"
                f"📍 Qayerdan: {pickup}\n"
                f"🏁 Qayerga: {destination}\n"
                f"🕒 Sana: {created_at}\n"
                f"----------------------------------\n"
            )
        else:
            status_text = {
                "pending": "⏳ В поиске",
                "accepted": "🚗 Принят",
                "completed": "✅ Завершен",
                "cancelled": "❌ Отменен"
            }.get(status, status)

            text += (
                f"🆔 **Заказ #{order_id}**\n"
                f"📌 Статус: {status_text}\n"
                f"📍 Откуда: {pickup}\n"
                f"🏁 Куда: {destination}\n"
                f"🕒 Дата: {created_at}\n"
                f"----------------------------------\n"
            )

    await message.answer(text, parse_mode="Markdown")


@router.message(RegistrationStates.waiting_for_phone, F.text)
async def process_user_contact_text(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    phone = message.text.strip()

    # Сохраняем введенный текст как номер телефона без лишних блокировок
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id)
        )
        async with db.execute(
            "SELECT role, lang FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            role, lang = row if row else ("passenger", "ru")
        await db.commit()

    t = LANGS.get(lang, LANGS["ru"])
    await message.answer(
        "✅ Регистрация успешно завершена!",
        reply_markup=get_main_menu(role, lang)
    )
    await state.clear()


@router.message(F.text == "🌐 Сменить язык / Tilni tanlash")
async def change_language_menu_btn(message: Message) -> None:
    await message.answer("🌐 Выберите язык / Tilni tanlang / Choose language:", reply_markup=get_language_keyboard())


# =====================================================================
# ЕДИНЫЙ ОБРАБОТЧИК ВЫБОРА ЯЗЫКА
# =====================================================================

@router.callback_query(F.data.startswith("lang_"))
async def process_language_callback(callback: CallbackQuery, state: FSMContext) -> None:
    selected_lang = callback.data.split("_")[1] # 'uz', 'ru' или 'en'
    user_id = callback.from_user.id
    
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Сохраняем выбранный язык в базу данных
        await db.execute(
            "UPDATE users SET lang = ? WHERE user_id = ?",
            (selected_lang, user_id)
        )
        await db.commit()
        
        # 2. Проверяем текущий статус пользователя в базе
        async with db.execute("SELECT role, first_name, phone FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            role = row[0] if row and row[0] else "passenger"
            first_name = row[1] if row else None
            phone = row[2] if row else None

    # Безопасно удаляем инлайн-кнопки выбора языка
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    # 3. ЕСЛИ ПОЛЬЗОВАТЕЛЬ УЖЕ ЗАРЕГИСТРИРОВАН (есть имя и телефон):
    # Очищаем стейт, меняем язык и мгновенно перестраиваем клавиатуру под новый язык!
    if first_name and phone:
        t = LANGS.get(selected_lang, LANGS["ru"])
        await state.clear()
        await callback.message.answer(
            f"✅ {t['lang_changed']}\n\n{t['choose_action']}",
            reply_markup=get_main_menu(role, selected_lang),
            parse_mode="Markdown"
        )
        return

    # 4. ЕСЛИ ЭТО НОВЫЙ ПОЛЬЗОВАТЕЛЬ (регистрация не завершена) — запускаем шаг ввода имени
    await state.set_state(RegistrationStates.waiting_for_full_name)
    
    if selected_lang == "uz":
        text = "📝 **Ro'yxatdan o'tish**\n\nIltimos, **Ism va Familiyangizni** kiriting:"
    elif selected_lang == "en":
        text = "📝 **Registration**\n\nPlease enter your **First and Last Name**:"
    else:
        text = "📝 **Регистрация в системе**\n\nПожалуйста, введите ваши **Имя и Фамилию**:"
        
    await callback.message.answer(text, parse_mode="Markdown")

@router.message(F.text.in_(["🚖 Стать водителем", "🚖 Haydovchi bo'lish", "🚖 Become a Driver"]))
async def switch_to_driver_mode(message: Message) -> None:
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row else "ru"
        await db.execute("UPDATE users SET role = 'driver' WHERE user_id = ?", (user_id,))
        await db.commit()

    t = LANGS.get(lang, LANGS["ru"])
    await message.answer(t["driver_activated"], reply_markup=get_main_menu("driver", lang))


@router.message(F.text.in_(["👤 Мой профиль", "👤 Mening profilim", "👤 My Profile"]))
async def show_user_profile(message: Message) -> None:
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT role, balance, verified, lang, first_name, last_name, phone FROM users WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row:
        role, balance, verified, lang, fname, lname, phone = row
        t = LANGS.get(lang, LANGS["ru"])
        role_str = "Водитель 🚖" if role == "driver" else "Пассажир 👤"
        verified_str = t["yes"] if verified == 1 else t["no"]
        name_str = f"{fname or ''} {lname or ''}".strip() or "Не указано"
        phone_str = phone or "Не указан"

        profile_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=t["delete_profile_btn"], callback_data="delete_my_profile")]
            ]
        )

        text = (
            f"{t['profile_title']}\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"👤 Имя: **{name_str}**\n"
            f"📞 Телефон: `{phone_str}`\n"
            f"📌 Роль: {role_str}\n"
            f"{t['balance_title']}: `{balance:.2f} сум`\n"
            f"{t['verified_status']}: {verified_str}"
        )
        await message.answer(text, reply_markup=profile_markup, parse_mode="Markdown")


@router.callback_query(F.data == "delete_my_profile")
async def delete_profile_callback(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await db.commit()

    await callback.message.edit_text("❌ Ваш профиль был полностью удален из системы. Введите /start для регистрации заново.")


# =====================================================================
# 7. АДМИН-ПАНЕЛЬ И ФУНКЦИИ (СТАТИСТИКА И РАССЫЛКА)
# =====================================================================

@router.message(Command("admin"))
async def admin_panel_entry(message: Message, state: FSMContext) -> None:
    await message.answer(
        "🔐 **Введите пароль администратора:**",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )
    await state.set_state(AdminStates.waiting_for_password)


@router.message(AdminStates.waiting_for_password)
async def verify_admin_password(message: Message, state: FSMContext) -> None:
    if message.text == ADMIN_PASSWORD:
        await state.clear()
        admin_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📢 Таргетированная рассылка", callback_data="admin_broadcast_menu")],
                [InlineKeyboardButton(text="📊 Статистика сервиса", callback_data="admin_stats_menu")],
                [InlineKeyboardButton(text="🎟 Добавить промокод", callback_data="admin_promo_menu")],
            ]
        )
        await message.answer(
            "👑 **Панель Администратора разблокирована!**",
            reply_markup=admin_keyboard,
            parse_mode="Markdown",
        )
    else:
        await message.answer("❌ Неверный пароль. Доступ отклонен.")
        await state.clear()


@router.callback_query(F.data == "admin_stats_menu")
async def admin_stats_callback(callback: CallbackQuery) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total_users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE role = 'driver'") as c:
            total_drivers = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM orders") as c:
            total_orders = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'") as c:
            completed_orders = (await c.fetchone())[0]

    stats_text = (
        f"📊 **Статистика сервиса Yo'ldosh Taxi**\n\n"
        f"👥 Всего пользователей: `{total_users}`\n"
        f"🚖 Зарегистрировано водителей: `{total_drivers}`\n"
        f"📦 Всего заказов создано: `{total_orders}`\n"
        f"🏁 Успешно завершено поездок: `{completed_orders}`"
    )
    await callback.message.edit_text(stats_text, parse_mode="Markdown")


@router.callback_query(F.data == "admin_broadcast_menu")
async def admin_broadcast_step_one(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("📢 Введите текст для рассылки всем пользователям бота:")
    await state.set_state(AdminStates.waiting_for_broadcast_text)


@router.message(AdminStates.waiting_for_broadcast_text)
async def admin_broadcast_execute(message: Message, state: FSMContext) -> None:
    broadcast_text = message.text
    await state.clear()
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()

    success_count = 0
    for u in users:
        try:
            await bot.send_message(u[0], f"📢 **Объявление сервиса:**\n\n{broadcast_text}", parse_mode="Markdown")
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"✅ Рассылка завершена успешно! Получателей: {success_count}")


# =====================================================================
# 8. ЗАКАЗЫ И СВОБОДНЫЕ ЗАКАЗЫ ДЛЯ ВОДИТЕЛЕЙ
# =====================================================================

@router.message(F.text.in_([
    "🚕 Заказать такси", "🕒 Заказать на потом", 
    "🚕 Taksi chaqirish", "🕒 Keyinga buyurtma berish", 
    "🚕 Order Taxi", "🕒 Order for Later"
]))
async def start_taxi_order(message: Message, state: FSMContext) -> None:
    is_scheduled = 1 if "потом" in message.text or "Keyinga" in message.text or "Later" in message.text else 0
    await state.update_data(is_scheduled=is_scheduled)
    await message.answer("📍 Укажите точный адрес отправления (откуда вас забрать):", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OrderStates.waiting_for_pickup)


@router.message(OrderStates.waiting_for_pickup)
async def process_order_pickup(message: Message, state: FSMContext) -> None:
    await state.update_data(pickup=message.text)
    await message.answer("🏁 Укажите точный адрес назначения (куда едем):")
    await state.set_state(OrderStates.waiting_for_destination)


@router.message(OrderStates.waiting_for_destination)
async def process_order_destination(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.update_data(destination=message.text)

    if data.get("is_scheduled") == 1:
        await message.answer("📅 Укажите дату и примерное время выезда (например: `26.11.2026 в 15:00`):", parse_mode="Markdown")
        await state.set_state(OrderStates.waiting_for_schedule_time)
    else:
        await state.update_data(schedule_time="Срочно сейчас")
        await message.answer("💬 Укажите комментарий для водителя (или напишите 'нет'):")
        await state.set_state(OrderStates.waiting_for_comment)


@router.message(OrderStates.waiting_for_schedule_time)
async def process_order_schedule_time(message: Message, state: FSMContext) -> None:
    await state.update_data(schedule_time=message.text)
    await message.answer("💬 Укажите комментарий для водителя (или напишите 'нет'):")
    await state.set_state(OrderStates.waiting_for_comment)


@router.message(OrderStates.waiting_for_comment)
async def finalize_order_creation(message: Message, state: FSMContext) -> None:
    comment = message.text
    data = await state.get_data()
    passenger_id = message.from_user.id
    pickup = data["pickup"]
    destination = data["destination"]
    is_scheduled = data["is_scheduled"]
    schedule_time = data["schedule_time"]
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            """
                INSERT INTO orders (passenger_id, pickup, destination, comment, is_scheduled, schedule_time, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (passenger_id, pickup, destination, comment, is_scheduled, schedule_time, created_at),
        )
        order_id = cursor.lastrowid
        await db.commit()

    cancel_markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel_order_{order_id}")]]
    )

    order_type_text = f"🕒 **ПРЕДВАРИТЕЛЬНЫЙ ЗАКАЗ** (Время: {schedule_time})" if is_scheduled else "🚀 **СРОЧНЫЙ ЗАКАЗ**"

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (passenger_id,)) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row else "ru"

    await message.answer(
        f"✅ Заказ **#{order_id}** успешно создан!\n\n{order_type_text}\n📍 Откуда: {pickup}\n🏁 Куда: {destination}\n💬 Комментарий: {comment}\n\n🔄 Поиск водителя...",
        reply_markup=cancel_markup,
        parse_mode="Markdown",
    )

    channel_markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🚖 Принять заказ", callback_data=f"accept_order_{order_id}")]]
    )
    try:
        await bot.send_message(
            CHANNEL_USERNAME,
            f"🆕 **Новый заказ #{order_id}**\n\n{order_type_text}\n📍 Откуда: {pickup}\n🏁 Куда: {destination}\n💬 Комментарий: {comment}",
            reply_markup=channel_markup,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Не удалось отправить в канал: {e}")

    await state.clear()

# 👇 ВСТАВЬ ЭТОТ БЛОК СЮДА 👇
@router.callback_query(F.data.startswith("cancel_order_"))
async def passenger_cancel_order_handler(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split("_")[2])
    logger.info(f"Попытка отмены заказа #{order_id} пассажиром.")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT status FROM orders WHERE order_id = ?", (order_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0] == "pending":
                await db.execute(
                    "UPDATE orders SET status = 'cancelled' WHERE order_id = ?",
                    (order_id,),
                )
                await db.commit()
                await callback.message.edit_text(
                    f"❌ Заказ #{order_id} был успешно отменен пассажиром."
                )
                logger.info(f"Заказ #{order_id} успешно отменен.")
            else:
                await callback.answer(
                    "⚠️ Заказ уже принят водителем!", 
                    show_alert=True
                )
# 👆 КОНЕЦ ВСТАВКИ 👆

@router.message(F.text.in_(["🚖 Свободные заказы", "🚖 Bo'sh buyurtmalar", "🚖 Free Orders"]))
async def show_free_orders_for_drivers(message: Message) -> None:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT order_id, pickup, destination, comment, schedule_time, is_scheduled FROM orders WHERE status = 'pending' ORDER BY order_id DESC LIMIT 5"
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("🚖 В данный момент свободных заказов нет.")
        return

    for row in rows:
        order_id, pickup, destination, comment, schedule_time, is_scheduled = row
        type_str = f"🕒 Предварительный ({schedule_time})" if is_scheduled else "🚀 Срочный"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🚖 Принять заказ", callback_data=f"accept_order_{order_id}")]]
        )
        await message.answer(
            f"📦 **Заказ #{order_id}** ({type_str})\n📍 Откуда: {pickup}\n🏁 Куда: {destination}\n💬 Комментарий: {comment}",
            reply_markup=kb,
            parse_mode="Markdown"
        )


@router.callback_query(F.data.startswith("cancel_order_"))
async def passenger_cancel_order_handler(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split("_")[2])
    logger.info(f"Попытка отмены заказа #{order_id} пассажиром.")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT status FROM orders WHERE order_id = ?", (order_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0] == "pending":
                await db.execute(
                    "UPDATE orders SET status = 'cancelled' WHERE order_id = ?",
                    (order_id,),
                )
                await db.commit()
                await callback.message.edit_text(
                    f"❌ Заказ #{order_id} был успешно отменен пассажиром."
                )
                logger.info(f"Заказ #{order_id} успешно отменен.")
            else:
                await callback.answer(
                    "⚠️ Заказ уже принят водителем или отменен!", 
                    show_alert=True
                )


@router.callback_query(F.data.startswith("accept_order_"))
async def driver_accept_order_handler(callback: CallbackQuery) -> None:
    try:
        parts = callback.data.split("_")
        if len(parts) < 3:
            await callback.answer("❌ Ошибка в данных заказа.", show_alert=True)
            return
            
        order_id = int(parts[2])
        driver_id = callback.from_user.id

        async with aiosqlite.connect(DB_NAME) as db:
            # Проверяем роль, верификацию, телефон, имя и фото верификации
            async with db.execute(
                "SELECT role, verified, phone, first_name, verification_photo, lang FROM users WHERE user_id = ?",
                (driver_id,)
            ) as cursor:
                user_row = await cursor.fetchone()
                
            if not user_row:
                await callback.answer("❌ Вы не зарегистрированы в системе. Нажмите /start", show_alert=True)
                return

            role, is_verified, phone, first_name, verification_photo, lang = user_row
            lang = lang or "ru"

            # 1. Проверка: роль водителя и заполненность профиля (имя, телефон)
            if role != "driver" or not phone or not first_name:
                incomplete_texts = {
                    "ru": "⚠️ Вы не завершили полную регистрацию водителя! Укажите имя и номер телефона.",
                    "uz": "⚠️ Siz to'liq haydovchi ro'yxatidan o'tmagansiz! Ism va telefon raqamingizni kiriting.",
                    "en": "⚠️ You have not completed full driver registration! Provide your name and phone."
                }
                await callback.answer(incomplete_texts.get(lang, incomplete_texts["ru"]), show_alert=True)
                return

            # 2. Проверка: наличие фото верификации и одобрение администратора (verified == 1)
            if not verification_photo or not is_verified or int(is_verified) != 1:
                not_verified_texts = {
                    "ru": "⚠️ Требуется полная верификация! Отправьте фото документов и дождитесь подтверждения администратора.",
                    "uz": "⚠️ To'liq verifikatsiya talab etiladi! Hujjatlar rasmini yuboring va tasdiqni kuting.",
                    "en": "⚠️ Full verification required! Send document photos and wait for admin approval."
                }
                await callback.answer(not_verified_texts.get(lang, not_verified_texts["ru"]), show_alert=True)
                return

            # Проверяем статус заказа
            async with db.execute("SELECT status, passenger_id, pickup, destination FROM orders WHERE order_id = ?", (order_id,)) as cursor:
                row = await cursor.fetchone()
                
            if not row:
                await callback.answer("❌ Заказ не найден в базе данных!", show_alert=True)
                return
                
            status, passenger_id, pickup, destination = row[0], row[1], row[2], row[3]
            
            if status != "pending":
                await callback.answer("❌ Этот заказ уже занят другим водителем или отменен!", show_alert=True)
                return
                
            # Обновляем статус заказа
            await db.execute(
                "UPDATE orders SET driver_id = ?, status = 'accepted' WHERE order_id = ?",
                (driver_id, order_id)
            )
            await db.commit()

        # 3. Полностью удаляем сообщение из канала, чтобы заказ исчез для остальных водителей
        try:
            await callback.message.delete()
        except Exception as e:
            logger.error(f"Не удалось удалить сообщение из канала: {e}")

        await callback.answer(f"✅ Вы успешно приняли заказ #{order_id}!", show_alert=True)

        # Отправляем водителю кнопку завершения поездки
        finish_btn_text = LANGS.get(lang, LANGS["ru"])["finish_trip_btn"]
        driver_trip_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=finish_btn_text)]],
            resize_keyboard=True
        )
        driver_msg = {
            "ru": f"🚖 **Вы приняли заказ #{order_id}**\n📍 Откуда: {pickup}\n🏁 Куда: {destination}\n\nКогда доставите пассажира, нажмите кнопку ниже:",
            "uz": f"🚖 **Siz #{order_id}-buyurtmani qabul qildingiz**\n📍 Qayerdan: {pickup}\n🏁 Qayerga: {destination}\n\nYo'lovchini manzilga yetkazgach, quyidagi tugmani bosing:",
            "en": f"🚖 **You accepted order #{order_id}**\n📍 From: {pickup}\n🏁 To: {destination}\n\nTap the button below once you complete the trip:"
        }
        await bot.send_message(
            driver_id,
            driver_msg.get(lang, driver_msg["ru"]),
            reply_markup=driver_trip_kb,
            parse_mode="Markdown"
        )

        # Запрашиваем геопозицию у пассажира
        location_markup = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Отправить мою геопозицию", request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        
        await bot.send_message(
            passenger_id,
            "🚗 Водитель принял ваш заказ! Отправьте свою текущую геопозицию для построения маршрута.",
            reply_markup=location_markup,
        )

    except Exception as e:
        logger.error(f"Ошибка в хендлере принятия заказа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при принятии заказа. Попробуйте еще раз.", show_alert=True)


@router.message(F.text.in_(["🏁 Завершить поездку", "🏁 Safarni yakunlash", "🏁 Complete Trip"]))
async def driver_finish_trip_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    driver_id = message.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (driver_id,)) as cursor:
            user_row = await cursor.fetchone()
        driver_lang = user_row[0] if user_row and user_row[0] else "ru"

        # Ищем активный заказ этого водителя
        async with db.execute(
            "SELECT order_id, passenger_id FROM orders WHERE driver_id = ? AND status = 'accepted' ORDER BY order_id DESC LIMIT 1",
            (driver_id,)
        ) as cursor:
            order_row = await cursor.fetchone()

        if not order_row:
            no_trip_msg = {
                "ru": "⚠️ У вас сейчас нет активной поездки для завершения.",
                "uz": "⚠️ Hozirda sizda yakunlash uchun faol safar yo'q.",
                "en": "⚠️ You don't have an active trip to complete right now."
            }
            await message.answer(no_trip_msg.get(driver_lang, no_trip_msg["ru"]))
            return

        order_id, passenger_id = order_row
        await db.execute("UPDATE orders SET status = 'completed' WHERE order_id = ?", (order_id,))
        await db.commit()

        # Узнаём язык пассажира для уведомления
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (passenger_id,)) as cursor:
            pass_row = await cursor.fetchone()
        pass_lang = pass_row[0] if pass_row and pass_row[0] else "ru"

    # Возвращаем водителю постоянное меню
    try:
        driver_kb = get_main_menu(role="driver", lang=driver_lang)
    except Exception:
        driver_kb = ReplyKeyboardRemove()

    done_driver_msg = {
        "ru": f"🏁 **Поездка #{order_id} успешно завершена!** Спасибо за работу с Yo'ldosh Taxi.",
        "uz": f"🏁 **#{order_id}-safar muvaffaqiyatli yakunlandi!** Yo'ldosh Taxi bilan ishlaganingiz uchun rahmat.",
        "en": f"🏁 **Trip #{order_id} completed successfully!** Thank you for driving with Yo'ldosh Taxi."
    }
    await message.answer(
        done_driver_msg.get(driver_lang, done_driver_msg["ru"]),
        reply_markup=driver_kb,
        parse_mode="Markdown"
    )

    # Уведомляем пассажира о завершении поездки и возвращаем его меню
    try:
        pass_kb = get_main_menu(role="passenger", lang=pass_lang)
    except Exception:
        pass_kb = ReplyKeyboardRemove()

    done_pass_msg = {
        "ru": f"🏁 **Ваша поездка #{order_id} завершена!** Спасибо, что выбрали Yo'ldosh Taxi.",
        "uz": f"🏁 **Sizning #{order_id}-safaringiz yakunlandi!** Yo'ldosh Taxi xizmatidan foydalanganingiz uchun rahmat.",
        "en": f"🏁 **Your trip #{order_id} has been completed!** Thank you for choosing Yo'ldosh Taxi."
    }
    try:
        await bot.send_message(
            passenger_id,
            done_pass_msg.get(pass_lang, done_pass_msg["ru"]),
            reply_markup=pass_kb,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пассажира {passenger_id} о завершении поездки: {e}")

# =====================================================================
# 9. ГЕОПОЗИЦИЯ И ЯНДЕКС КАРТЫ
# =====================================================================

@router.message(F.location)
async def passenger_location_receiver(message: Message) -> None:
    passenger_id = message.from_user.id
    lat = message.location.latitude
    lon = message.location.longitude

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT order_id, driver_id FROM orders WHERE passenger_id = ? AND status = 'accepted'",
            (passenger_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                order_id, driver_id = row[0], row[1]
                await db.execute("UPDATE orders SET status = 'active' WHERE order_id = ?", (order_id,))
                await db.commit()

                yandex_url = f"https://yandex.com/maps/?rtext=~{lat},{lon}&rtt=auto"
                active_markup = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🚨 ТРЕВОГА (SOS)", callback_data=f"trip_sos_{order_id}")],
                        [InlineKeyboardButton(text="🏁 Завершить поездку", callback_data=f"trip_finish_{order_id}")],
                    ]
                )

                async with aiosqlite.connect(DB_NAME) as db_l:
                    async with db_l.execute("SELECT lang FROM users WHERE user_id = ?", (passenger_id,)) as cursor_l:
                        row_l = await cursor_l.fetchone()
                        lang = row_l[0] if row_l else "ru"

                await bot.send_message(
                    driver_id,
                    f"📍 Геопозиция пассажира по заказу #{order_id}!\n\n🔗 [Открыть маршрут в Яндекс Картах]({yandex_url})",
                    reply_markup=active_markup,
                    parse_mode="Markdown",
                )
                await message.answer("✅ Геопозиция передана водителю.", reply_markup=get_main_menu("passenger", lang))


# =====================================================================
# ЗАВЕРШЕНИЕ ПОЕЗДКИ
# =====================================================================

@router.callback_query(F.data.startswith("trip_finish_"))
async def trip_finish_handler(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Получаем информацию о заказе
        async with db.execute("SELECT passenger_id, driver_id, status FROM orders WHERE order_id = ?", (order_id,)) as cursor:
            order_row = await cursor.fetchone()
            
        if not order_row:
            await callback.answer("⚠️ Ошибка: поездка не найдена.", show_alert=True)
            return

        p_id, d_id, status = order_row

        if status == 'completed':
            await callback.answer("ℹ️ Эта поездка уже завершена.", show_alert=True)
            return

        # 2. Обновляем статус заказа в базе данных
        await db.execute("UPDATE orders SET status = 'completed' WHERE order_id = ?", (order_id,))
        await db.commit()

        # 3. Узнаем язык пользователя, который нажал кнопку
        async with db.execute("SELECT role, lang FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_row = await cursor.fetchone()
            role = user_row[0] if user_row else "passenger"
            lang = user_row[1] if user_row else "ru"

    await callback.answer("✅ Поездка успешно завершена!", show_alert=True)
    
    # Тексты подтверждения на разных языках
    finish_texts = {
        "ru": f"🏁 **Поездка №{order_id} завершена.** Спасибо, что воспользовались Yo'ldosh Taxi!",
        "uz": f"🏁 **{order_id}-sonli safar yakunlandi.** Yo'ldosh Taxi'dan foydalanganingiz uchun rahmat!",
        "en": f"🏁 **Ride #{order_id} is completed.** Thank you for using Yo'ldosh Taxi!"
    }
    
    await callback.message.edit_text(
        finish_texts.get(lang, finish_texts["ru"]),
        parse_mode="Markdown"
    )
    
    # Отправляем главное меню пользователю
    t = LANGS.get(lang, LANGS["ru"])
    await callback.message.answer(
        t["choose_action"],
        reply_markup=get_main_menu(role, lang)
    )
    
    # Если завершил водитель, можно продублировать уведомление пассажиру (если он в сети)
    if user_id == d_id and p_id:
        try:
            async with aiosqlite.connect(DB_NAME) as db:
                async with db.execute("SELECT lang FROM users WHERE user_id = ?", (p_id,)) as cursor:
                    p_row = await cursor.fetchone()
                    p_lang = p_row[0] if p_row else "ru"
            p_text = {
                "ru": f"🏁 Водитель завершил поездку №{order_id}.",
                "uz": f"🏁 Haydovchi {order_id}-sonli safarni yakunladi.",
                "en": f"🏁 Driver has completed ride #{order_id}."
            }
            await callback.bot.send_message(p_id, p_text.get(p_lang, p_text["ru"]))
        except Exception:
            pass

    await state.clear()


# =====================================================================
# 11. ПОПОЛНЕНИЕ БАЛАНСА И ВЕРИФИКАЦИЯ (ПОЧИНЕННЫЕ ФОТО-ХЕНДЛЕРЫ)
# =====================================================================

@router.message(F.text.in_(["💰 Пополнить баланс", "💰 Balansni to'ldirish", "💰 Top Up Balance"]))
async def driver_topup_menu(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row else "ru"
    t = LANGS.get(lang, LANGS["ru"])
    await message.answer(t["topup_instructions"], reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
    await state.set_state(DriverStates.waiting_for_receipt)


@router.message(DriverStates.waiting_for_receipt, F.photo)
async def driver_receipt_receiver(message: Message, state: FSMContext) -> None:
    photo_id = message.photo[-1].file_id
    driver_id = message.from_user.id

    topup_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Подтвердить зачисление", callback_data=f"confirm_topup_{driver_id}")]]
    )
    
    try:
        await bot.send_photo(
            ADMIN_ID,
            photo_id,
            caption=f"💳 **Запрос на пополнение баланса водителя**\nID водителя: `{driver_id}`",
            reply_markup=topup_kb,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Не удалось отправить чек админу: {e}")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (driver_id,)) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row and row[0] in ["ru", "uz"] else "ru"

    msg_text = (
        "✅ Chek tekshirish uchun administratorga yuborildi!"
        if lang == "uz"
        else "✅ Чек успешно отправлен администратору на проверку!"
    )
    await message.answer(msg_text, reply_markup=get_main_menu("driver", lang))
    await state.clear()


@router.callback_query(F.data.startswith("confirm_topup_"))
async def admin_confirm_topup(callback: CallbackQuery) -> None:
    driver_id = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + 50000 WHERE user_id = ?", (driver_id,))
        await db.commit()

    await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ **БАЛАНС УСПЕШНО ПОПОЛНЕН**", parse_mode="Markdown")
    await bot.send_message(driver_id, "💰 Ваш баланс успешно пополнен администратором!")


@router.message(F.text.in_(["📸 Верификация", "📸 Verifikatsiya", "📸 Verification"]))
async def driver_verification_menu(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row else "ru"
    t = LANGS.get(lang, LANGS["ru"])
    await message.answer(t["verification_instructions"], reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
    await state.set_state(DriverStates.waiting_for_verification_photo)


@router.message(DriverStates.waiting_for_verification_photo, F.photo)
async def driver_verification_receiver(message: Message, state: FSMContext) -> None:
    photo_id = message.photo[-1].file_id
    driver_id = message.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET verification_photo = ? WHERE user_id = ?",
            (photo_id, driver_id)
        )
        async with db.execute(
            "SELECT lang, first_name, last_name, phone FROM users WHERE user_id = ?",
            (driver_id,)
        ) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row and row[0] else "ru"
            full_name = f"{row[1] or ''} {row[2] or ''}".strip() or "Не указано"
            phone = row[3] if row and row[3] else "Не указан"
        await db.commit()

    verif_kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve_driver_{driver_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_driver_{driver_id}")
        ]]
    )
    
    # Текст для админа с главным акцентом на телефон водителя
    await bot.send_photo(
        ADMIN_ID,
        photo_id,
        caption=(
            f"📸 **Запрос на верификацию водителя**\n\n"
            f"👤 Имя: {full_name}\n"
            f"📞 **Телефон:** `{phone}`\n"
            f"🆔 Telegram ID: `{driver_id}`"
        ),
        reply_markup=verif_kb,
        parse_mode="Markdown",
    )

    await message.answer("✅ Фото документов отправлено администратору на проверку.", reply_markup=get_main_menu("driver", lang))
    await state.clear()


@router.callback_query(F.data.startswith("approve_driver_"))
async def approve_driver_callback(callback: CallbackQuery) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    driver_id = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET verified = 1 WHERE user_id = ?", (driver_id,))
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (driver_id,)) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row and row[0] else "ru"
        await db.commit()

    await callback.message.edit_caption(
        caption=f"{callback.message.caption}\n\n✅ **ПОДТВЕРЖДЕНО АДМИНИСТРАТОРОМ**",
        parse_mode="Markdown"
    )
    await callback.answer("Водитель верифицирован!")

    notify_text = {
        "ru": "✅ Ваша верификация подтверждена администратором! Теперь ваш аккаунт имеет статус «Верифицирован».",
        "uz": "✅ Verifikatsiyangiz administrator tomonidan tasdiqlandi! Endi hisobingiz «Tasdiqlangan» maqomiga ega.",
        "en": "✅ Your verification has been approved by the admin! Your account is now marked as Verified."
    }
    try:
        await bot.send_message(driver_id, notify_text.get(lang, notify_text["ru"]))
    except Exception as e:
        logger.error(f"Не удалось уведомить водителя {driver_id}: {e}")


@router.callback_query(F.data.startswith("reject_driver_"))
async def reject_driver_callback(callback: CallbackQuery) -> None:
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    driver_id = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET verified = 0, verification_photo = NULL WHERE user_id = ?", (driver_id,))
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (driver_id,)) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row and row[0] else "ru"
        await db.commit()

    await callback.message.edit_caption(
        caption=f"{callback.message.caption}\n\n❌ **ОТКЛОНЕНО АДМИНИСТРАТОРОМ**",
        parse_mode="Markdown"
    )
    await callback.answer("Заявка отклонена.")

    notify_text = {
        "ru": "❌ Ваша заявка на верификацию отклонена. Пожалуйста, отправьте более четкое фото документов.",
        "uz": "❌ Verifikatsiya so'rovingiz rad etildi. Iltimos, hujjatlarning aniqroq rasmini qayta yuboring.",
        "en": "❌ Your verification request was rejected. Please submit a clearer photo of your documents."
    }
    try:
        await bot.send_message(driver_id, notify_text.get(lang, notify_text["ru"]))
    except Exception as e:
        logger.error(f"Не удалось уведомить водителя {driver_id}: {e}")


@router.callback_query(F.data.startswith("approve_driver_"))
async def admin_approve_driver(callback: CallbackQuery) -> None:
    driver_id = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET verified = 1 WHERE user_id = ?", (driver_id,))
        await db.commit()

    await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ **СТАТУС: ВЕРИФИЦИРОВАН**", parse_mode="Markdown")
    await bot.send_message(driver_id, "🎉 Поздравляем! Ваш аккаунт водителя успешно верифицирован.")


# =====================================================================
# 12. ПРОМОКОДЫ
# =====================================================================

@router.callback_query(F.data == "admin_promo_menu")
async def admin_promo_step_one(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.answer("🎟 Введите уникальный промокод:")
    await state.set_state(AdminStates.waiting_for_promo_code)


@router.message(AdminStates.waiting_for_promo_code)
async def admin_promo_step_two(message: Message, state: FSMContext) -> None:
    await state.update_data(promo_code=message.text)
    await message.answer("💰 Введите номинал скидки:")
    await state.set_state(AdminStates.waiting_for_promo_discount)


@router.message(AdminStates.waiting_for_promo_discount)
async def admin_promo_step_three(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    code = data["promo_code"]
    discount = float(message.text)

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO promos (code, discount, is_active) VALUES (?, ?, 1)", (code, discount))
        await db.commit()

    await message.answer(f"✅ Промокод `{code}` на скидку `{discount} сум` создан!")
    await state.clear()


# =====================================================================
# ХЕНДЛЕР КНОПКИ СМЕНИ ЯЗЫКА
# =====================================================================

@router.message(F.text.func(lambda text: text and "сменить язык" in text.lower()))
async def change_language_request(message: Message, state: FSMContext) -> None:
    await state.clear()
    
    if "uz" in message.text.lower():
        await message.answer(
            "Iltimos, yangi tilni tanlang:",
            reply_markup=get_language_keyboard()
        )
    else:
        await message.answer(
            "Пожалуйста, выберите новый язык:",
            reply_markup=get_language_keyboard()
        )


# =====================================================================
# СИСТЕМА ПОПОЛНЕНИЯ БАЛАНСА ЧЕРЕЗ ЧЕКИ И АДМИНА
# =====================================================================

class AdminTopUpStates(StatesGroup):
    waiting_for_amount = State()


# 1. Кнопка в главном меню или /topup для пользователя (показ реквизитов)
@router.message(F.text.in_(["💳 Пополнить баланс", "💳 Hisobni to'ldirish"]))
async def cmd_top_up_request(message: Message, state: FSMContext) -> None:
    card_number = "9860 3801 2345 6789"
    card_holder = "Abdumomin Abdurahmanov"

    text_msg = (
        "💳 <b>Пополнение баланса Yo'ldosh Taxi</b>\n\n"
        f"1. Переведите необходимую сумму на карту:\n"
        f"💳 <code>{card_number}</code> ({card_holder})\n\n"
        "2. После оплаты отправьте сюда <b>скриншот или фото чека</b>.\n"
        "Администратор проверит перевод, и средства зачислятся на ваш баланс!"
    )
    await message.answer(text_msg, parse_mode="HTML")


# 2. Получение чека (фото) от пользователя и пересылка админу
@router.message(F.photo)
async def user_send_receipt_handler(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    full_name = html.escape(message.from_user.full_name or "Не указано")
    username = f"@{html.escape(message.from_user.username)}" if message.from_user.username else "Не указан"
    photo_file_id = message.photo[-1].file_id

    phone = "Не указан"
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                phone = html.escape(str(row[0]))

    admin_caption = (
        f"💰 <b>Запрос на пополнение баланса!</b>\n\n"
        f"👤 <b>От:</b> {full_name}\n"
        f"🔗 <b>Username:</b> {username}\n"
        f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
        f"🆔 <b>ID пользователя:</b> <code>{user_id}</code>\n\n"
        f"👇 Нажмите кнопку ниже, чтобы подтвердить платеж и указать сумму:"
    )

    admin_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить пополнение", callback_data=f"topup_accept_{user_id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"topup_reject_{user_id}")]
        ]
    )

    try:
        await bot.send_photo(
            ADMIN_ID,
            photo=photo_file_id,
            caption=admin_caption,
            reply_markup=admin_kb,
            parse_mode="HTML"
        )
        await message.answer("✅ Чек успешно отправлен администрации! Ожидайте зачисления средств.")
    except Exception as e:
        logger.error(f"Не удалось отправить чек админу: {e}")
        await message.answer("⚠️ Не удалось отправить чек. Попробуйте позже.")


# 3. Админ нажал «✅ Подтвердить пополнение»
@router.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("topup_accept_"))
async def admin_accept_topup_callback(callback: CallbackQuery, state: FSMContext) -> None:
    target_user_id = int(callback.data.split("_")[2])

    await state.update_data(topup_target_id=target_user_id)
    await state.set_state(AdminTopUpStates.waiting_for_amount)

    await callback.message.answer(
        f"✍️ Введите сумму пополнения для пользователя (ID: <code>{target_user_id}</code>) цифрами:\n"
        f"<i>Например: 30000</i>",
        parse_mode="HTML"
    )
    await callback.answer()


# 4. Админ вводит сумму цифрами в чат
@router.message(F.from_user.id == ADMIN_ID, AdminTopUpStates.waiting_for_amount, F.text)
async def admin_enter_amount_handler(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    target_user_id = data.get("topup_target_id")
    await state.clear()

    if not target_user_id:
        await message.reply("⚠️ Ошибка: ID пользователя потерян. Нажмите кнопку подтверждения заново.")
        return

    clean_text = message.text.replace(" ", "").replace(",", "")
    if not clean_text.isdigit():
        await message.reply("❌ Ошибка! Сумма должна состоять только из цифр (например: 30000). Попробуйте снова, нажав на кнопку под чеком.")
        return

    amount = float(clean_text)

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, target_user_id)
        )
        await db.commit()

        async with db.execute("SELECT lang, balance FROM users WHERE user_id = ?", (target_user_id,)) as cursor:
            user_row = await cursor.fetchone()

    user_lang = user_row[0] if user_row and user_row[0] else "ru"
    new_balance = user_row[1] if user_row and user_row[1] is not None else amount

    success_texts = {
        "ru": f"✅ <b>Ваш баланс успешно пополнен!</b>\n\n💳 Зачислено: <b>{amount:,.0f} сум</b>\n💰 Текущий баланс: <b>{new_balance:,.0f} сум</b>",
        "uz": f"✅ <b>Hisobingiz muvaffaqiyatli to'ldirildi!</b>\n\n💳 Qo'shildi: <b>{amount:,.0f} so'm</b>\n💰 Joriy balans: <b>{new_balance:,.0f} so'm</b>",
        "en": f"✅ <b>Your balance has been topped up!</b>\n\n💳 Added: <b>{amount:,.0f} UZS</b>\n💰 Current balance: <b>{new_balance:,.0f} UZS</b>"
    }

    try:
        await bot.send_message(
            target_user_id,
            success_texts.get(user_lang, success_texts["ru"]),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {target_user_id} о пополнении: {e}")

    await message.reply(f"✅ Баланс пользователя <code>{target_user_id}</code> успешно пополнен на <b>{amount:,.0f} сум</b>!", parse_mode="HTML")


# 5. Админ нажал «❌ Отклонить»
@router.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("topup_reject_"))
async def admin_reject_topup_callback(callback: CallbackQuery) -> None:
    target_user_id = int(callback.data.split("_")[2])

    reject_texts = {
        "ru": "❌ <b>К сожалению, ваш платеж был отклонен администрацией.</b>\nЕсли у вас есть вопросы, обратитесь в поддержку /help.",
        "uz": "❌ <b>Afsuski, to'lovingiz ma'muriyat tomonidan rad etildi.</b>\nSavollar bo'lsa, /help orqali murojaat qiling.",
        "en": "❌ <b>Unfortunately, your payment was rejected by administration.</b>\nIf you have questions, contact support via /help."
    }

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (target_user_id,)) as cursor:
            row = await cursor.fetchone()
    user_lang = row[0] if row and row[0] else "ru"

    try:
        await bot.send_message(target_user_id, reject_texts.get(user_lang, reject_texts["ru"]), parse_mode="HTML")
        await callback.message.edit_caption(
            caption=f"{callback.message.caption}\n\n❌ <b>СТАТУС: Отклонено администратором</b>",
            parse_mode="HTML",
            reply_markup=None
        )
        await callback.answer("Платеж отклонен.", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при отклонении платежа: {e}")
        await callback.answer("⚠️ Ошибка при обработке.", show_alert=True)
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    app.router.add_get("/health", handle_health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"AIOHTTP веб-сервер запущен на порту {PORT}")
    return runner


from aiogram.types import BotCommand

# =====================================================================
# 14. ЗАПУСК
# =====================================================================

async def main() -> None:
    await init_db()
    
    # Регистрируем команды бота, чтобы они появлялись при вводе "/"
    await bot.set_my_commands([
        BotCommand(command="start", description="🚀 Запустить бота / Главное меню"),
        BotCommand(command="help", description="❓ Помощь и инструкция"),
    ])
    
    dp.include_router(router)
    runner = await start_web_server()
    
    logger.info("Запуск опроса Telegram API...")
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
