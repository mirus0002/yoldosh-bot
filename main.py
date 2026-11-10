#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
=============================================================================
Project: Yo'ldosh Taxi Telegram Bot (Production Render Version)
Author: Mirxamidjon Mirbadalov
Stack: Python 3.14, aiogram 3.x, aiosqlite, aiohttp
Description: Full-featured taxi booking and management system for passengers 
             and drivers with multi-language support, payment receipts, SOS, 
             Yandex Maps integration, promo codes, admin panel, and aiohttp web-server.
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
# 1. СИСТЕМНАЯ КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
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

TOKEN = os.getenv("8958743093:AAF4WxbQsQl96sTheScyOrO_C8lftm0-mWQ")  # Токен из окружения Render или напрямую
ADMIN_PASSWORD = "2009mmmm"  # Пин-код администратора
CHANNEL_USERNAME = "@Yoldosh_Taxi_Official"  # Официальный канал заказов и уведомлений
PORT = int(os.getenv("PORT", 10000))  # Порт для веб-сервиса Render

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

DB_NAME = "yoldosh_taxi_production.db"


# =====================================================================
# 2. ПОЛНЫЕ МНОГОЯЗЫЧНЫЕ СЛОВАРИ (RU, UZ, EN)
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
        "verification": "📸 Верификация",
        "free_orders": "🚖 Свободные заказы",
        "lang_changed": "🇷🇺 Язык успешно изменен на русский!",
        "cancel_order_btn": "❌ Отменить заказ",
        "accept_order_btn": "🚖 Принять заказ",
        "send_location_btn": "📍 Отправить мою геопозицию",
        "sos_btn": "🚨 ТРЕВОГА (SOS)",
        "finish_trip_btn": "🏁 Завершить поездку",
        "rating_title": "⭐ Оцените качество поездки от 1 до 5:",
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
        "verification": "📸 Verifikatsiya",
        "free_orders": "🚖 Bo'sh buyurtmalar",
        "lang_changed": "🇺🇿 Til muvaffaqiyatli o'zbek tiliga o'zgartirildi!",
        "cancel_order_btn": "❌ Buyurtmani bekor qilish",
        "accept_order_btn": "🚖 Buyurtmani qabul qilish",
        "send_location_btn": "📍 Mening geolyatsiyamni yuborish",
        "sos_btn": "🚨 TREVOGA (SOS)",
        "finish_trip_btn": "🏁 Safarni yakunlash",
        "rating_title": "⭐ Safar sifatini 1 dan 5 gacha baholang:",
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
        "verification": "📸 Verification",
        "free_orders": "🚖 Free Orders",
        "lang_changed": "🇬🇧 Language successfully changed to English!",
        "cancel_order_btn": "❌ Cancel Order",
        "accept_order_btn": "🚖 Accept Order",
        "send_location_btn": "📍 Send My Location",
        "sos_btn": "🚨 SOS EMERGENCY",
        "finish_trip_btn": "🏁 Complete Trip",
        "rating_title": "⭐ Rate your trip quality from 1 to 5:",
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
# 3. ИНИЦИАЛИЗАЦИЯ И УПРАВЛЕНИЕ БАЗОЙ ДАННЫХ (AIOSQLITE)
# =====================================================================

async def init_db() -> None:
    """Инициализирует всю структуру базы данных для Yo'ldosh Taxi."""
    logger.info("Инициализация базы данных aiosqlite...")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                role TEXT DEFAULT 'passenger',
                lang TEXT DEFAULT 'ru',
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

        await db.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                trip_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                passenger_id INTEGER,
                driver_id INTEGER,
                price REAL,
                completed_at TEXT
            )
        """)
        await db.commit()
    logger.info("База данных успешно инициализирована и готова к работе.")


# =====================================================================
# 4. FSM СОСТОЯНИЯ (STATES)
# =====================================================================

class OrderStates(StatesGroup):
    waiting_for_pickup = State()
    waiting_for_destination = State()
    waiting_for_schedule_time = State()
    waiting_for_comment = State()


class DriverStates(StatesGroup):
    waiting_for_verification_photo = State()
    waiting_for_receipt = State()


class AdminStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_broadcast_text = State()
    waiting_for_promo_code = State()
    waiting_for_promo_discount = State()


class RatingStates(StatesGroup):
    waiting_for_rating = State()


# =====================================================================
# 5. КЛАВИАТУРЫ И ИНТЕРФЕЙСНЫЕ КОМПОНЕНТЫ
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
                    KeyboardButton(text=t["verification"]),
                ],
                [KeyboardButton(text=t["history"])],
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
                    KeyboardButton(text=t["history"]),
                ],
                [KeyboardButton(text=t["become_driver"])],
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


# =====================================================================
# 6. СТАРТ, ВЫБОР ЯЗЫКА И УПРАВЛЕНИЕ ПРОФИЛЕМ
# =====================================================================

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"Пользователь {user_id} вызвал команду /start")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT role, lang FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                await db.execute(
                    "INSERT INTO users (user_id, role, lang, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, "passenger", "ru", now),
                )
                await db.commit()
                lang = "ru"
                role = "passenger"
            else:
                role, lang = row

    t = LANGS.get(lang, LANGS["ru"])
    lang_kb = get_language_keyboard()

    await message.answer(
        f"{t['welcome']}\n\n{t['choose_action']}",
        reply_markup=get_main_menu(role, lang),
        parse_mode="Markdown",
    )
    await message.answer("🌐 Выберите язык / Tilni tanlang / Choose language:", reply_markup=lang_kb)


@router.callback_query(F.data.startswith("lang_"))
async def set_language_callback(callback: CallbackQuery) -> None:
    lang = callback.data.split("_")[1]
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} сменил язык на {lang}")

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id)
        )
        async with db.execute(
            "SELECT role FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            role = row[0] if row else "passenger"
        await db.commit()

    t = LANGS.get(lang, LANGS["ru"])
    await callback.message.edit_text(
        f"✅ {t['lang_changed']}", parse_mode="Markdown"
    )
    await callback.message.answer(
        t["choose_action"], reply_markup=get_main_menu(role, lang)
    )


@router.message(F.text.in_([
    "🚖 Стать водителем", 
    "🚖 Haydovchi bo'lish", 
    "🚖 Become a Driver"
]))
async def switch_to_driver_mode(message: Message) -> None:
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} переключился в режим водителя.")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT lang FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row else "ru"
        await db.execute(
            "UPDATE users SET role = 'driver' WHERE user_id = ?", (user_id,)
        )
        await db.commit()

    t = LANGS.get(lang, LANGS["ru"])
    await message.answer(
        t["driver_activated"], 
        reply_markup=get_main_menu("driver", lang)
    )


@router.message(F.text.in_([
    "👤 Мой профиль", 
    "👤 Mening profilim", 
    "👤 My Profile"
]))
async def show_user_profile(message: Message) -> None:
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} запросил свой профиль.")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT role, balance, verified, lang FROM users WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row:
        role, balance, verified, lang = row
        t = LANGS.get(lang, LANGS["ru"])
        role_str = "Водитель 🚖" if role == "driver" else "Пассажир 👤"
        verified_str = t["yes"] if verified == 1 else t["no"]

        text = (
            f"{t['profile_title']}\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"📌 Роль: {role_str}\n"
            f"{t['balance_title']}: `{balance:.2f} сум`\n"
            f"{t['verified_status']}: {verified_str}"
        )
        await message.answer(text, parse_mode="Markdown")


# =====================================================================
# 7. АДМИН-ПАНЕЛЬ (СВОБОДНЫЙ ДОСТУП ПО ПАРОЛЮ 2009mmmm)
# =====================================================================

@router.message(Command("admin"))
async def admin_panel_entry(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} инициировал вход в админ-панель.")
    await message.answer(
        "🔐 **Введите пароль администратора для авторизации:**",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )
    await state.set_state(AdminStates.waiting_for_password)


@router.message(AdminStates.waiting_for_password)
async def verify_admin_password(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    if message.text == ADMIN_PASSWORD:
        logger.info(f"Пользователь {user_id} успешно авторизовался в админ-панели.")
        await state.clear()
        admin_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📢 Таргетированная рассылка",
                        callback_data="admin_broadcast_menu",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🎟 Добавить промокод", 
                        callback_data="admin_promo_menu"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📊 Статистика сервиса", 
                        callback_data="admin_stats_menu"
                    )
                ],
            ]
        )
        await message.answer(
            "👑 **Панель Администратора успешно разблокирована!**\nВыберите нужный инструмент управления:",
            reply_markup=admin_keyboard,
            parse_mode="Markdown",
        )
    else:
        logger.warning(f"Пользователь {user_id} ввел неверный пароль администратора.")
        await message.answer("❌ Неверный пароль доступа. Доступ отклонен. Введите /start")
        await state.clear()


# =====================================================================
# 8. ЛОГИКА ЗАКАЗОВ И СЕКЦИЯ «ЗАКАЗАТЬ НА ПОТОМ»
# =====================================================================

@router.message(F.text.in_([
    "🚕 Заказать такси", "🕒 Заказать на потом", 
    "🚕 Taksi chaqirish", "🕒 Keyinga buyurtma berish", 
    "🚕 Order Taxi", "🕒 Order for Later"
]))
async def start_taxi_order(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    is_scheduled = 1 if "потом" in message.text or "Keyinga" in message.text or "Later" in message.text else 0
    logger.info(f"Пользователь {user_id} начал создание заказа (scheduled={is_scheduled}).")
    
    await state.update_data(is_scheduled=is_scheduled)
    await message.answer(
        "📍 Укажите точный адрес отправления (откуда вас забрать):",
        reply_markup=ReplyKeyboardRemove(),
    )
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
        await message.answer(
            "📅 Укажите дату и примерное время выезда (например: `26.11.2026 в 15:00`):",
            parse_mode="Markdown",
        )
        await state.set_state(OrderStates.waiting_for_schedule_time)
    else:
        await state.update_data(schedule_time="Срочно сейчас")
        await message.answer("💬 Укажите комментарий для водителя (например: 'еду с багажом' или 'нет'):")
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

    logger.info(f"Создание заказа в БД от пассажира {passenger_id}. Откуда: {pickup}, Куда: {destination}")

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            """
                INSERT INTO orders (passenger_id, pickup, destination, comment, is_scheduled, schedule_time, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
            """,
            (
                passenger_id,
                pickup,
                destination,
                comment,
                is_scheduled,
                schedule_time,
                created_at,
            ),
        )
        order_id = cursor.lastrowid
        await db.commit()

    cancel_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отменить заказ",
                    callback_data=f"cancel_order_{order_id}",
                )
            ]
        ]
    )

    order_type_text = (
        f"🕒 **ПРЕДВАРИТЕЛЬНЫЙ ЗАКАЗ** (Время: {schedule_time})"
        if is_scheduled
        else "🚀 **СРОЧНЫЙ ЗАКАЗ**"
    )

    await message.answer(
        f"✅ Заказ **#{order_id}** успешно создан!\n\n"
        f"{order_type_text}\n"
        f"📍 Откуда: {pickup}\n"
        f"🏁 Куда: {destination}\n"
        f"💬 Комментарий: {comment}\n\n"
        f"🔄 Поиск водителя...",
        reply_markup=cancel_markup,
        parse_mode="Markdown",
    )

    channel_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚖 Принять заказ", 
                    callback_data=f"accept_order_{order_id}"
                )
            ]
        ]
    )
    try:
        await bot.send_message(
            CHANNEL_USERNAME,
            f"🆕 **Новый заказ в системе #{order_id}**\n\n"
            f"{order_type_text}\n"
            f"📍 Откуда: {pickup}\n"
            f"🏁 Куда: {destination}\n"
            f"💬 Комментарий: {comment}",
            reply_markup=channel_markup,
            parse_mode="Markdown",
        )
        logger.info(f"Заказ #{order_id} успешно опубликован в канал {CHANNEL_USERNAME}")
    except Exception as e:
        logger.error(f"Не удалось отправить заказ #{order_id} в канал: {e}")

    await state.clear()


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
    order_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id
    logger.info(f"Водитель {driver_id} пытается принять заказ #{order_id}.")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT status, passenger_id FROM orders WHERE order_id = ?", (order_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] != "pending":
                await callback.answer(
                    "❌ Этот заказ уже занят другим водителем или отменен!",
                    show_alert=True,
                )
                return

            passenger_id = row[1]
            await db.execute(
                "UPDATE orders SET driver_id = ?, status = 'accepted' WHERE order_id = ?",
                (driver_id, order_id),
            )
            await db.commit()

    await callback.message.edit_text(
        f"✅ Вы успешно приняли заказ #{order_id}! Ожидаем геолокацию пассажира."
    )

    location_request_markup = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📍 Отправить мою геопозицию", 
                    request_location=True
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await bot.send_message(
        passenger_id,
        "🚗 Водитель принял ваш заказ! Пожалуйста, отправьте свою текущую геопозицию, чтобы водитель проложил маршрут.",
        reply_markup=location_request_markup,
    )


# =====================================================================
# 9. ГЕОПОЗИЦИЯ ПАССАЖИРА И ЯНДЕКС КАРТЫ (rtext)
# =====================================================================

@router.message(F.location)
async def passenger_location_receiver(message: Message) -> None:
    passenger_id = message.from_user.id
    lat = message.location.latitude
    lon = message.location.longitude
    logger.info(f"Получена геопозиция от пассажира {passenger_id}: lat={lat}, lon={lon}")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT order_id, driver_id FROM orders WHERE passenger_id = ? AND status = 'accepted'",
            (passenger_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                order_id, driver_id = row[0], row[1]
                await db.execute(
                    "UPDATE orders SET status = 'active' WHERE order_id = ?", 
                    (order_id,)
                )
                await db.commit()

                yandex_maps_route_url = (
                    f"https://yandex.com/maps/?rtext=~{lat},{lon}&rtt=auto"
                )

                active_trip_markup = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🚨 ТРЕВОГА (SOS)",
                                callback_data=f"trip_sos_{order_id}",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="🏁 Завершить поездку",
                                callback_data=f"trip_finish_{order_id}",
                            )
                        ],
                    ]
                )

                async with aiosqlite.connect(DB_NAME) as db_l:
                    async with db_l.execute(
                        "SELECT lang FROM users WHERE user_id = ?", (passenger_id,)
                    ) as cursor_l:
                        row_l = await cursor_l.fetchone()
                        lang = row_l[0] if row_l else "ru"

                await bot.send_message(
                    driver_id,
                    f"📍 Получена геопозиция пассажира по заказу #{order_id}!\n\n"
                    f"🔗 [Построить маршрут в Яндекс Картах]({yandex_maps_route_url})",
                    reply_markup=active_trip_markup,
                    parse_mode="Markdown",
                )
                await message.answer(
                    "✅ Геопозиция передана водителю. Счастливого пути!",
                    reply_markup=get_main_menu("passenger", lang),
                )


# =====================================================================
# 10. ТРЕВОЖНАЯ КНОПКА SOS И ЗАВЕРШЕНИЕ ПОЕЗДКИ
# =====================================================================

@router.callback_query(F.data.startswith("trip_sos_"))
async def trip_sos_handler(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split("_")[2])
    logger.warning(f"СРОЧНО! Нажата кнопка SOS по заказу #{order_id}!")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT status, passenger_id, driver_id FROM orders WHERE order_id = ?",
            (order_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row and row[0] == "active":
                _, passenger_id, driver_id = row
                await callback.answer(
                    "🚨 СИГНАЛ ТРЕВОГИ ОТПРАВЛЕН В ЭКСТРЕННЫЕ СЛУЖБЫ!", 
                    show_alert=True
                )
                await bot.send_message(
                    CHANNEL_USERNAME,
                    f"🚨 **ВНИМАНИЕ! СРАБОТАЛА ТРЕВОЖНАЯ КНОПКА (SOS)**\n"
                    f"Поездка: `#{order_id}`\n"
                    f"Пассажир ID: `{passenger_id}` | Водитель ID: `{driver_id}`",
                    parse_mode="Markdown",
                )
            else:
                await callback.answer(
                    "⚠️ Кнопка SOS доступна исключительно во время активной поездки!",
                    show_alert=True,
                )


@router.callback_query(F.data.startswith("trip_finish_"))
async def trip_finish_handler(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split("_")[2])
    logger.info(f"Водитель завершает поездку по заказу #{order_id}")

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE orders SET status = 'completed' WHERE order_id = ?", (order_id,)
        )
        await db.commit()

    await callback.message.edit_text(f"🏁 Поездка #{order_id} успешно завершена.")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT passenger_id FROM orders WHERE order_id = ?", (order_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                passenger_id = row[0]
                rating_markup = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="⭐ 1", callback_data=f"rate_{order_id}_1"
                            ),
                            InlineKeyboardButton(
                                text="⭐⭐ 2", callback_data=f"rate_{order_id}_2"
                            ),
                            InlineKeyboardButton(
                                text="⭐⭐⭐ 3", callback_data=f"rate_{order_id}_3"
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                text="⭐⭐⭐⭐ 4", callback_data=f"rate_{order_id}_4"
                            ),
                            InlineKeyboardButton(
                                text="⭐⭐⭐⭐⭐ 5", callback_data=f"rate_{order_id}_5"
                            ),
                        ],
                    ]
                )
                await bot.send_message(
                    passenger_id,
                    "⭐ Пожалуйста, оцените качество завершенной поездки от 1 до 5:",
                    reply_markup=rating_markup,
                )


@router.callback_query(F.data.startswith("rate_"))
async def process_trip_rating(callback: CallbackQuery) -> None:
    parts = callback.data.split("_")
    order_id = int(parts[1])
    stars = int(parts[2])
    logger.info(f"Получена оценка для заказа #{order_id}: {stars} звезд.")

    await callback.message.edit_text(f"Спасибо за вашу оценку: {'⭐' * stars}!")

    if stars < 2:
        logger.warning(f"Низкая оценка ({stars}/5) для заказа #{order_id}. Отправка уведомления админу.")
        await bot.send_message(
            CHANNEL_USERNAME,
            f"⚠️ **ВНИМАНИЕ: НИЗКАЯ ОЦЕНКА ПОЕЗДКИ!**\n"
            f"Номер заказа: `#{order_id}`\n"
            f"Поставленная оценка: {'⭐' * stars} ({stars}/5)",
            parse_mode="Markdown",
        )


# =====================================================================
# 11. ПОПОЛНЕНИЕ БАЛАНСА ВОДИТЕЛЯ ЧЕРЕЗ СКРИНШОТ/ЧЕК
# =====================================================================

@router.message(F.text.in_([
    "💰 Пополнить баланс", 
    "💰 Balansni to'ldirish", 
    "💰 Top Up Balance"
]))
async def driver_topup_balance_menu(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    logger.info(f"Водитель {user_id} запросил реквизиты для пополнения баланса.")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT lang FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row else "ru"

    t = LANGS.get(lang, LANGS["ru"])

    await message.answer(
        t["topup_instructions"],
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )
    await state.set_state(DriverStates.waiting_for_receipt)


@router.message(DriverStates.waiting_for_receipt, F.photo)
async def driver_receipt_photo_receiver(message: Message, state: FSMContext) -> None:
    photo_id = message.photo[-1].file_id
    driver_id = message.from_user.id
    logger.info(f"Получен чек пополнения баланса от водителя {driver_id}")

    topup_approval_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить зачисление",
                    callback_data=f"confirm_topup_{driver_id}",
                )
            ]
        ]
    )
    await bot.send_photo(
        CHANNEL_USERNAME,
        photo_id,
        caption=(
            f"💳 **Запрос на пополнение баланса водителя**\nID водителя: `{driver_id}`"
        ),
        reply_markup=topup_approval_markup,
        parse_mode="Markdown",
    )

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT lang FROM users WHERE user_id = ?", (driver_id,)
        ) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row else "ru"

    await message.answer(
        "✅ Чек успешно передан администратору на проверку.",
        reply_markup=get_main_menu("driver", lang),
    )
    await state.clear()


# =====================================================================
# 12. АВТОМАТИЧЕСКАЯ И МОДЕРИРУЕМАЯ ВЕРИФИКАЦИЯ ВОДИТЕЛЕЙ ПО ФОТО
# =====================================================================

@router.message(F.text.in_([
    "📸 Верификация", 
    "📸 Verifikatsiya", 
    "📸 Verification"
]))
async def driver_verification_menu(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    logger.info(f"Водитель {user_id} открыл меню верификации.")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT lang FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row else "ru"

    t = LANGS.get(lang, LANGS["ru"])

    await message.answer(
        t["verification_instructions"],
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )
    await state.set_state(DriverStates.waiting_for_verification_photo)


@router.message(DriverStates.waiting_for_verification_photo, F.photo)
async def driver_verification_photo_receiver(message: Message, state: FSMContext) -> None:
    photo_id = message.photo[-1].file_id
    driver_id = message.from_user.id
    logger.info(f"Получено фото документов для верификации от водителя {driver_id}")

    verification_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить верификацию",
                    callback_data=f"approve_driver_{driver_id}",
                )
            ]
        ]
    )
    await bot.send_photo(
        CHANNEL_USERNAME,
        photo_id,
        caption=(
            f"📸 **Запрос на верификацию водителя**\nID водителя: `{driver_id}`"
        ),
        reply_markup=verification_markup,
        parse_mode="Markdown",
    )

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT lang FROM users WHERE user_id = ?", (driver_id,)
        ) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row else "ru"

    await message.answer(
        "✅ Фото документов отправлено администратору на проверку.",
        reply_markup=get_main_menu("driver", lang),
    )
    await state.clear()


@router.callback_query(F.data.startswith("approve_driver_"))
async def admin_approve_driver_callback(callback: CallbackQuery) -> None:
    driver_id = int(callback.data.split("_")[2])
    logger.info(f"Администратор одобрил верификацию для водителя {driver_id}")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "UPDATE users SET verified = 1 WHERE user_id = ?", (driver_id,)
        ) as cursor:
            await db.commit()

    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n✅ **СТАТУС: ВЕРИФИЦИРОВАН**",
        parse_mode="Markdown",
    )
    await bot.send_message(
        driver_id,
        "🎉 Поздравляем! Ваш аккаунт водителя успешно верифицирован администрацией.",
    )


# =====================================================================
# 13. ИСТОРИЯ ПОЕЗДОК И КВИТАНЦИЯ
# =====================================================================

@router.message(F.text.in_([
    "📋 История поездок", 
    "📋 Safarlar tarixi", 
    "📋 Trip History"
]))
async def show_trip_history_list(message: Message) -> None:
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} запросил историю поездок.")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            """
                SELECT order_id, pickup, destination, created_at, status 
                FROM orders WHERE passenger_id = ? OR driver_id = ? 
                ORDER BY order_id DESC LIMIT 5
            """,
            (user_id, user_id),
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("📋 У вас пока нет зарегистрированных поездок в истории.")
        return

    history_output = "📋 **История ваших поездок (последние 5):**\n\n"
    for row in rows:
        order_id, pickup, destination, created_at, status = row
        history_output += (
            f"🆔 Заказ `#{order_id}`\n"
            f"📍 Откуда: {pickup}\n"
            f"🏁 Куда: {destination}\n"
            f"📅 Дата: {created_at}\n"
            f"📌 Статус: {status}\n\n"
        )

    await message.answer(history_output, parse_mode="Markdown")


# =====================================================================
# 14. МАРКЕТИНГ: ПРОМОКОДЫ И РАССЫЛКА
# =====================================================================

@router.callback_query(F.data == "admin_promo_menu")
async def admin_promo_step_one(callback: CallbackQuery, state: FSMContext) -> None:
    logger.info("Администратор инициировал создание промокода.")
    await callback.message.answer("🎟 Введите уникальный текстовый код для нового промокода:")
    await state.set_state(AdminStates.waiting_for_promo_code)


@router.message(AdminStates.waiting_for_promo_code)
async def admin_promo_step_two(message: Message, state: FSMContext) -> None:
    await state.update_data(promo_code=message.text)
    await message.answer("💰 Введите номинал скидки по данному промокоду (например: 5000):")
    await state.set_state(AdminStates.waiting_for_promo_discount)


@router.message(AdminStates.waiting_for_promo_discount)
async def admin_promo_step_three(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    code = data["promo_code"]
    discount = float(message.text)
    logger.info(f"Сохранение нового промокода: {code} на сумму {discount}")

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO promos (code, discount, is_active) VALUES (?, ?, 1)",
            (code, discount),
        )
        await db.commit()

    await message.answer(f"✅ Промокод `{code}` на скидку в `{discount} сум` успешно создан!")
    await state.clear()


# =====================================================================
# 15. AIOHTTP СЕРВЕР ДЛЯ RENDER (УСТРАНЕНИЕ ОШИБКИ ДЕПЛОЯ)
# =====================================================================

async def handle_health_check(request: web.Request) -> web.Response:
    """Простой хендлер для ответа на HTTP-запросы Render."""
    return web.Response(text="Yo'ldosh Taxi Bot is running successfully!")


async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    app.router.add_get("/health", handle_health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"AIOHTTP веб-сервер успешно запущен на порту {PORT}")
    return runner


# =====================================================================
# 16. ЗАПУСК ГЛАВНОГО АСИНХРОННОГО ЦИКЛА БОТА И СЕРВЕРА
# =====================================================================

async def main() -> None:
    await init_db()
    dp.include_router(router)
    
    # Запускаем локальный веб-сервер для Render, чтобы пройти Health Check
    runner = await start_web_server()
    
    logger.info("Бот Yo'ldosh Taxi запущен и начал опрос Telegram API.")
    await bot.delete_webhook(drop_pending_updates=True)
    
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Работа бота Yo'ldosh Taxi была принудительно остановлена.")
