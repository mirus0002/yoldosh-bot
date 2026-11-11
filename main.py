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
        "verification": "📸 Верификация",
        "free_orders": "🚖 Свободные заказы",
        "lang_changed": "🇷🇺 Язык успешно изменен на русский!",
        "cancel_order_btn": "❌ Отменить заказ",
        "accept_order_btn": "🚖 Принять заказ",
        "send_location_btn": "📍 Отправить мою геопозицию",
        "sos_btn": "🚨 ТРЕВОГА (SOS)",
        "finish_trip_btn": "🏁 Завершить поездку",
        "delete_profile_btn": "❌ Удалить профиль",
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
        "delete_profile_btn": "❌ Profilni o'chirish",
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
        "delete_profile_btn": "❌ Delete Profile",
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


class DriverStates(StatesGroup):
    waiting_for_verification_photo = State()
    waiting_for_receipt = State()


class AdminStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_broadcast_text = State()
    waiting_for_promo_code = State()
    waiting_for_promo_discount = State()


class RegistrationStates(StatesGroup):
    waiting_for_phone = State()


# =====================================================================
# 5. КЛАВИАТУРЫ
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
                [
                    KeyboardButton(text=t["history"]),
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
                    KeyboardButton(text=t["history"]),
                ],
                [
                    KeyboardButton(text=t["become_driver"]),
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


# =====================================================================
# 6. СТАРТ И РЕГИСТРАЦИЯ КОНТАКТА
# =====================================================================

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    user_id = message.from_user.id
    first_name = message.from_user.first_name or "Не указано"
    last_name = message.from_user.last_name or ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT role, lang, phone FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                await db.execute(
                    "INSERT INTO users (user_id, role, lang, first_name, last_name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, "passenger", "ru", first_name, last_name, now),
                )
                await db.commit()
                
                # Запросим номер телефона
                phone_kb = ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
                await message.answer(
                    f"🚖 Добро пожаловать в **Yo'ldosh Taxi**, {first_name}!\n\n"
                    "Пожалуйста, поделитесь вашим номером телефона для завершения регистрации:",
                    reply_markup=phone_kb,
                    parse_mode="Markdown"
                )
                await state.set_state(RegistrationStates.waiting_for_phone)
                return
            else:
                role, lang, phone = row

    t = LANGS.get(lang, LANGS["ru"])
    await message.answer(
        f"{t['welcome']}\n\n{t['choose_action']}",
        reply_markup=get_main_menu(role, lang),
        parse_mode="Markdown",
    )


@router.message(RegistrationStates.waiting_for_phone, F.contact)
async def process_user_contact(message: Message, state: FSMContext) -> None:
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
    await message.answer(
        "✅ Регистрация успешно завершена!",
        reply_markup=get_main_menu(role, lang)
    )
    await state.clear()


@router.message(F.text == "🌐 Сменить язык / Jurnal")
async def change_language_menu_btn(message: Message) -> None:
    await message.answer("🌐 Выберите язык / Tilni tanlang / Choose language:", reply_markup=get_language_keyboard())


@router.callback_query(F.data.startswith("lang_"))
async def set_language_callback(callback: CallbackQuery) -> None:
    lang = callback.data.split("_")[1]
    user_id = callback.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id))
        async with db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            role = row[0] if row else "passenger"
        await db.commit()

    t = LANGS.get(lang, LANGS["ru"])
    await callback.message.edit_text(f"✅ {t['lang_changed']}", parse_mode="Markdown")
    await callback.message.answer(t["choose_action"], reply_markup=get_main_menu(role, lang))


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
                    "⚠️ Заказ уже принят водителем или отменен!", 
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
    order_id = int(callback.data.split("_")[2])
    driver_id = callback.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT status, passenger_id FROM orders WHERE order_id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] != "pending":
                await callback.answer("❌ Этот заказ уже занят или отменен!", show_alert=True)
                return
            passenger_id = row[1]
            await db.execute("UPDATE orders SET driver_id = ?, status = 'accepted' WHERE order_id = ?", (driver_id, order_id))
            await db.commit()

    await callback.message.edit_text(f"✅ Вы успешно приняли заказ #{order_id}!")

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
# 10. SOS И ЗАВЕРШЕНИЕ ПОЕЗДКИ
# =====================================================================

@router.callback_query(F.data.startswith("trip_sos_"))
async def trip_sos_handler(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT passenger_id, driver_id FROM orders WHERE order_id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                p_id, d_id = row
                await callback.answer("🚨 ТРЕВОГА ОТПРАВЛЕНА!", show_alert=True)
                await bot.send_message(
                    CHANNEL_USERNAME,
                    f"🚨 **ТРЕВОГА (SOS) ПО ПОЕЗДКЕ #{order_id}**\nПассажир ID: `{p_id}` | Водитель ID: `{d_id}`",
                    parse_mode="Markdown"
                )


@router.callback_query(F.data.startswith("trip_finish_"))
async def trip_finish_handler(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE orders SET status = 'completed' WHERE order_id = ?", (order_id,))
        await db.commit()

    await callback.message.edit_text(f"🏁 Поездка #{order_id} успешно завершена.")


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
    await bot.send_photo(
        ADMIN_ID,
        photo_id,
        caption=f"💳 **Запрос на пополнение баланса водителя**\nID водителя: `{driver_id}`",
        reply_markup=topup_kb,
        parse_mode="Markdown",
    )

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (driver_id,)) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row else "ru"

    await message.answer("✅ Чек успешно отправлен администратору на проверку!", reply_markup=get_main_menu("driver", lang))
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

    verif_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Подтвердить верификацию", callback_data=f"approve_driver_{driver_id}")]]
    )
    await bot.send_photo(
        ADMIN_ID,
        photo_id,
        caption=f"📸 **Запрос на верификацию водителя**\nID водителя: `{driver_id}`",
        reply_markup=verif_kb,
        parse_mode="Markdown",
    )

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT lang FROM users WHERE user_id = ?", (driver_id,)) as cursor:
            row = await cursor.fetchone()
            lang = row[0] if row else "ru"

    await message.answer("✅ Фото документов отправлено администратору на проверку.", reply_markup=get_main_menu("driver", lang))
    await state.clear()


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
# 13. AIOHTTP СЕРВЕР ДЛЯ RENDER
# =====================================================================

async def handle_health_check(request: web.Request) -> web.Response:
    return web.Response(text="Yo'ldosh Taxi Bot is running successfully!")


async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    app.router.add_get("/health", handle_health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"AIOHTTP веб-сервер запущен на порту {PORT}")
    return runner


# =====================================================================
# 14. ЗАПУСК
# =====================================================================

async def main() -> None:
    await init_db()
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
