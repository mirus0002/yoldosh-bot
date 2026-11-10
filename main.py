import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.filters import Command
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

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Конфигурация
TOKEN = "YOUR_BOT_TOKEN_HERE"  # Замени на токен своего бота
ADMIN_PASSWORD = "2009mmmm"
CHANNEL_USERNAME = "@Yoldosh_Taxi_Official"

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

DB_NAME = "yoldosh_taxi.db"


# --- БАЗА ДАННЫх (aiosqlite) ---
async def init_db():
  async with aiosqlite.connect(DB_NAME) as db:
    # Пользователи
    await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                role TEXT DEFAULT 'passenger', -- 'passenger' или 'driver'
                lang TEXT DEFAULT 'ru',
                phone TEXT,
                balance REAL DEFAULT 0.0,
                verified INTEGER DEFAULT 0, -- 0 - не верифицирован, 1 - верифицирован
                verification_photo TEXT
            )
        """)
    # Заказы
    await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                passenger_id INTEGER,
                driver_id INTEGER,
                pickup TEXT,
                destination TEXT,
                comment TEXT,
                status TEXT DEFAULT 'pending', -- pending, accepted, active, completed, cancelled
                is_scheduled INTEGER DEFAULT 0,
                schedule_time TEXT,
                created_at TEXT
            )
        """)
    # Промокоды
    await db.execute("""
            CREATE TABLE IF NOT EXISTS promos (
                code TEXT PRIMARY KEY,
                discount REAL
            )
        """)
    # История поездок
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


# --- FSM СОСТОЯНИЯ ---
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
  waiting_for_broadcast = State()
  waiting_for_promo_code = State()
  waiting_for_promo_discount = State()


class RatingStates(StatesGroup):
  waiting_for_rating = State()


# --- КЛАВИАТУРЫ ---
def main_menu(role="passenger"):
  if role == "driver":
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🚖 Свободные заказы"),
                KeyboardButton(text="💰 Пополнить баланс"),
            ],
            [
                KeyboardButton(text="👤 Мой профиль"),
                KeyboardButton(text="📸 Верификация"),
            ],
            [KeyboardButton(text="📋 История поездок")],
        ],
        resize_keyboard=True,
    )
  else:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🚕 Заказать такси"),
                KeyboardButton(text="🕒 Заказать на потом"),
            ],
            [
                KeyboardButton(text="👤 Мой профиль"),
                KeyboardButton(text="📋 История поездок"),
            ],
            [KeyboardButton(text="🚖 Стать водителем")],
        ],
        resize_keyboard=True,
    )


# --- СТАРТ И РЕГИСТРАЦИЯ ---
@router.message(Command("start"))
async def cmd_start(message: Message):
  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT role FROM users WHERE user_id = ?", (message.from_user.id,)
    ) as cursor:
      row = await cursor.fetchone()
      if not row:
        await db.execute(
            "INSERT INTO users (user_id, role) VALUES (?, ?)",
            (message.from_user.id, "passenger"),
        )
        await db.commit()
        role = "passenger"
      else:
        role = row[0]

  await message.answer(
      f"🚖 Добро пожаловать в **Yo'ldosh Taxi**!\nВыберите действие:",
      reply_markup=main_menu(role),
      parse_mode="Markdown",
  )


# Переключение роли на водителя
@router.message(F.text == "🚖 Стать водителем")
async def become_driver(message: Message):
  async with aiosqlite.connect(DB_NAME) as db:
    await db.execute(
        "UPDATE users SET role = 'driver' WHERE user_id = ?",
        (message.from_user.id,),
    )
    await db.commit()
  await message.answer(
      "✅ Режим водителя активирован!", reply_markup=main_menu("driver")
  )


# --- АДМИН-ПАНЕЛЬ (Доступна каждому по паролю 2009mmmm) ---
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
  await message.answer(
      "🔐 Введите пароль администратора:", reply_markup=ReplyKeyboardRemove()
  )
  await state.set_state(AdminStates.waiting_for_password)


@router.message(AdminStates.waiting_for_password)
async def process_admin_password(message: Message, state: FSMContext):
  if message.text == ADMIN_PASSWORD:
    await state.clear()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Таргетированная рассылка",
                    callback_data="admin_broadcast",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎟 Добавить промокод", callback_data="admin_promo"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Статистика", callback_data="admin_stats"
                )
            ],
        ]
    )
    await message.answer(
        "👑 **Панель администратора успешно открыта!**\nВыберите действие:",
        reply_markup=kb,
        parse_mode="Markdown",
    )
  else:
    await message.answer("❌ Неверный пароль. Попробуйте снова или /start")
    await state.clear()


# --- ЗАКАЗ ТАКСИ И «ЗАКАЗАТЬ НА ПОТОМ» ---
@router.message(F.text.in_(["🚕 Заказать такси", "🕒 Заказать на потом"]))
async def start_order(message: Message, state: FSMContext):
  is_scheduled = 1 if "потом" in message.text else 0
  await state.update_data(is_scheduled=is_scheduled)
  await message.answer(
      "📍 Укажите адрес отправления (откуда вас забрать):",
      reply_markup=ReplyKeyboardRemove(),
  )
  await state.set_state(OrderStates.waiting_for_pickup)


@router.message(OrderStates.waiting_for_pickup)
async def process_pickup(message: Message, state: FSMContext):
  await state.update_data(pickup=message.text)
  await message.answer("🏁 Укажите адрес назначения (куда едем):")
  await state.set_state(OrderStates.waiting_for_destination)


@router.message(OrderStates.waiting_for_destination)
async def process_destination(message: Message, state: FSMContext):
  data = await state.get_data()
  if data.get("is_scheduled") == 1:
    await state.update_data(destination=message.text)
    await message.answer(
        "📅 Укажите дату и примерное время выезда (например: 25.11.2026 в 14:30):"
    )
    await state.set_state(OrderStates.waiting_for_schedule_time)
  else:
    await state.update_data(destination=message.text, schedule_time="Срочно")
    await message.answer("💬 Укажите комментарий к заказу (или напишите 'нет'):")
    await state.set_state(OrderStates.waiting_for_comment)


@router.message(OrderStates.waiting_for_schedule_time)
async def process_schedule_time(message: Message, state: FSMContext):
  await state.update_data(schedule_time=message.text)
  await message.answer("💬 Укажите комментарий к заказу (или напишите 'нет'):")
  await state.set_state(OrderStates.waiting_for_comment)


@router.message(OrderStates.waiting_for_comment)
async def process_comment(message: Message, state: FSMContext):
  data = await state.get_data()
  comment = message.text
  passenger_id = message.from_user.id
  pickup = data["pickup"]
  destination = data["destination"]
  is_scheduled = data["is_scheduled"]
  schedule_time = data["schedule_time"]
  created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  async with aiosqlite.connect(DB_NAME) as db:
    cursor = await db.execute(
        """
            INSERT INTO orders (passenger_id, pickup, destination, comment, is_scheduled, schedule_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
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

  # Кнопка отмены заказа (пока водитель не принял)
  cancel_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="❌ Отменить заказ", callback_data=f"cancel_order_{order_id}"
              )
          ]
      ]
  )

  order_type_text = (
      f"🕒 **ПРЕДВАРИТЕЛЬНЫЙ ЗАКАЗ** ({schedule_time})"
      if is_scheduled
      else "🚀 **СРОЧНЫЙ ЗАКАЗ**"
  )

  await message.answer(
      f"✅ Заказ №{order_id} успешно создан!\n\n"
      f"{order_type_text}\n"
      f"📍 Откуда: {pickup}\n"
      f"🏁 Куда: {destination}\n"
      f"💬 Комментарий: {comment}\n\n"
      f"Ожидаем водителя...",
      reply_markup=cancel_kb,
      parse_mode="Markdown",
  )

  # Авторассылка в канал @Yoldosh_Taxi_Official
  channel_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🚖 Принять заказ", callback_data=f"accept_order_{order_id}"
              )
          ]
      ]
  )
  try:
    await bot.send_message(
        CHANNEL_USERNAME,
        f"🆕 **Новый заказ #{order_id}**\n\n"
        f"{order_type_text}\n"
        f"📍 Откуда: {pickup}\n"
        f"🏁 Куда: {destination}\n"
        f"💬 Комментарий: {comment}",
        reply_markup=channel_kb,
        parse_mode="Markdown",
    )
  except Exception as e:
    logging.error(f"Не удалось отправить в канал: {e}")

  await state.clear()


# Отмена заказа пассажиром
@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order_handler(callback: CallbackQuery):
  order_id = int(callback.data.split("_")[2])
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
        await callback.message.edit_text(f"❌ Заказ #{order_id} был отменен.")
      else:
        await callback.answer(
            "Заказ уже принят водителем или отменен!", show_alert=True
        )


# Принятие заказа водителем
@router.callback_query(F.data.startswith("accept_order_"))
async def accept_order_handler(callback: CallbackQuery):
  order_id = int(callback.data.split("_")[2])
  driver_id = callback.from_user.id

  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT status, passenger_id FROM orders WHERE order_id = ?", (order_id,)
    ) as cursor:
      row = await cursor.fetchone()
      if not row or row[0] != "pending":
        await callback.answer(
            "❌ Этот заказ уже занят или отменен!", show_alert=True
        )
        return

      passenger_id = row[1]
      await db.execute(
          "UPDATE orders SET driver_id = ?, status = 'accepted' WHERE order_id = ?",
          (driver_id, order_id),
      )
      await db.commit()

  await callback.message.edit_text(
      f"✅ Вы успешно приняли заказ #{order_id}!"
  )

  # Запрос геопозиции у пассажира для отправки водителю + Яндекс Карты (rtext)
  loc_kb = ReplyKeyboardMarkup(
      keyboard=[
          [
              KeyboardButton(
                  text="📍 Отправить мою геопозицию", request_location=True
              )
          ]
      ],
      resize_keyboard=True,
      one_time_keyboard=True,
  )
  await bot.send_message(
      passenger_id,
      "🚗 Водитель принял ваш заказ! Пожалуйста, отправьте свою геопозицию,"
      " чтобы водитель смог построить маршрут.",
      reply_markup=loc_kb,
  )


# --- ГЕОЛОКАЦИЯ И МАРШРУТ ЯНДЕКС КАРТЫ ---
@router.message(F.location)
async def handle_passenger_location(message: Message):
  passenger_id = message.from_user.id
  lat = message.location.latitude
  lon = message.location.longitude

  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT order_id, driver_id FROM orders WHERE passenger_id = ? AND status ="
        " 'accepted'",
        (passenger_id,),
    ) as cursor:
      row = await cursor.fetchone()
      if row:
        order_id, driver_id = row[0], row[1]
        # Обновляем статус заказа на 'active' (активная поездка)
        await db.execute(
            "UPDATE orders SET status = 'active' WHERE order_id = ?", (order_id,)
        )
        await db.commit()

        # Ссылка на Яндекс Карты с параметром rtext
        yandex_maps_url = (
            f"https://yandex.com/maps/?rtext=~{lat},{lon}&rtt=auto"
        )

        sos_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🚨 ТРЕВОГА (SOS)",
                        callback_data=f"sos_trip_{order_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🏁 Завершить поездку",
                        callback_data=f"finish_trip_{order_id}",
                    )
                ],
            ]
        )

        await bot.send_message(
            driver_id,
            f"📍 Получена геопозиция пассажира по заказу #{order_id}!\n\n"
            f"🔗 [Открыть маршрут в Яндекс Картах]({yandex_maps_url})",
            reply_markup=sos_kb,
            parse_mode="Markdown",
        )
        await message.answer(
            "✅ Геопозиция отправлена водителю. Счастливого пути!",
            reply_markup=main_menu("passenger"),
        )


# --- ТРЕВОЖНАЯ КНОПКА SOS (Только во время активной поездки) ---
@router.callback_query(F.data.startswith("sos_trip_"))
async def sos_trip_handler(callback: CallbackQuery):
  order_id = int(callback.data.split("_")[2])
  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT status, passenger_id, driver_id FROM orders WHERE order_id = ?",
        (order_id,),
    ) as cursor:
      row = await cursor.fetchone()
      if row and row[0] == "active":
        _, passenger_id, driver_id = row
        # Уведомляем админов и экстренные службы
        await callback.answer(
            "🚨 СИГНАЛ ТРЕВОГИ ОТПРАВЛЕН!", show_alert=True
        )
        # Отправляем тревожное оповещение
        alert_text = (
            f"🚨 **ВНИМАНИЕ! СИГНАЛ ТРЕВОГИ (SOS) ПО ПОЕЗДКЕ #{order_id}**!\n"
            f"Пассажир: {passenger_id}, Водитель: {driver_id}"
        )
        await bot.send_message(CHANNEL_USERNAME, alert_text, parse_mode="Markdown")
      else:
        await callback.answer(
            "Кнопка SOS доступна только во время активной поездки!",
            show_alert=True,
        )


# Завершение поездки и оценка
@router.callback_query(F.data.startswith("finish_trip_"))
async def finish_trip_handler(callback: CallbackQuery):
  order_id = int(callback.data.split("_")[2])
  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "UPDATE orders SET status = 'completed' WHERE order_id = ?", (order_id,)
    ) as cursor:
      await db.commit()

  await callback.message.edit_text(
      f"✅ Поездка #{order_id} успешно завершена!"
  )

  # Запрос оценки у пассажира
  async with aiosqlite.connect(DB_NAME) as db:
    async with db.execute(
        "SELECT passenger_id FROM orders WHERE order_id = ?", (order_id,)
    ) as cursor:
      row = await cursor.fetchone()
      if row:
        passenger_id = row[0]
        rating_kb = InlineKeyboardMarkup(
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
            "⭐ Оцените качество поездки от 1 до 5:",
            reply_markup=rating_kb,
        )


# Обработка оценки (< 2 звезд -> уведомление админу)
@router.callback_query(F.data.startswith("rate_"))
async def process_rating(callback: CallbackQuery):
  parts = callback.data.split("_")
  order_id = int(parts[1])
  stars = int(parts[2])

  await callback.message.edit_text(
      f"Спасибо за вашу оценку: {'⭐' * stars}!"
  )

  if stars < 2:
    # Уведомление админу
    await bot.send_message(
        CHANNEL_USERNAME,
        f"⚠️ **ВНИМАНИЕ! Низкая оценка поездки #{order_id}**\nОценка:"
        f" {'⭐' * stars} ({stars}/5)",
        parse_mode="Markdown",
    )


# --- ПОПОЛНЕНИЕ БАЛАНСА ВОДИТЕЛЯ ЧЕРЕЗ ЧЕК ---
@router.message(F.text == "💰 Пополнить баланс")
async def topup_balance(message: Message, state: FSMContext):
  card_number = "4023060518850838"
  holder_name = "MIRXAMIDJON MIRBADALOV"
  phone_sup = "+998 91 773-51-52"

  await message.answer(
      f"💳 **Пополнение баланса водителя**\n\n"
      f"Переведите сумму на карту:\n`{card_number}`\n"
      f"Имя: {holder_name}\n"
      f"Поддержка: {phone_sup}\n\n"
      f"📸 Отправьте скриншот/чек перевода в этот чат для подтверждения.",
      parse_mode="Markdown",
      reply_markup=ReplyKeyboardRemove(),
  )
  await state.set_state(DriverStates.waiting_for_receipt)


@router.message(DriverStates.waiting_for_receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext):
  photo_id = message.photo[-1].file_id
  driver_id = message.from_user.id

  approval_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Подтвердить пополнение",
                  callback_data=f"approve_topup_{driver_id}",
              )
          ]
      ]
  )
  await bot.send_photo(
      CHANNEL_USERNAME,
      photo_id,
      caption=(
          f"💳 **Запрос на пополнение баланса**\nВодитель ID: `{driver_id}`"
      ),
      reply_markup=approval_kb,
      parse_mode="Markdown",
  )

  await message.answer(
      "✅ Чек отправлен на проверку администратору. Баланс пополнится в течение"
      " нескольких минут.",
      reply_markup=main_menu("driver"),
  )
  await state.clear()


# --- ВЕРИФИКАЦИЯ ВОДИТЕЛЯ ПО ФОТО ---
@router.message(F.text == "📸 Верификация")
async def start_verification(message: Message, state: FSMContext):
  await message.answer(
      "📸 Отправьте фото вашего водительского удостоверения или документов для"
      " верификации:",
      reply_markup=ReplyKeyboardRemove(),
  )
  await state.set_state(DriverStates.waiting_for_verification_photo)


@router.message(DriverStates.waiting_for_verification_photo, F.photo)
async def receive_verification_photo(message: Message, state: FSMContext):
  photo_id = message.photo[-1].file_id
  driver_id = message.from_user.id

  verify_kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="✅ Верифицировать",
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
      reply_markup=verify_kb,
      parse_mode="Markdown",
  )

  await message.answer(
      "✅ Фото отправлено на проверку администратору.",
      reply_markup=main_menu("driver"),
  )
  await state.clear()


# Подтверждение верификации админом через канал
@router.callback_query(F.data.startswith("approve_driver_"))
async def approve_driver_handler(callback: CallbackQuery):
  driver_id = int(callback.data.split("_")[2])
  async with aiosqlite.connect(DB_NAME) as db:
    await db.execute(
        "UPDATE users SET verified = 1 WHERE user_id = ?", (driver_id,)
    )
    await db.commit()
  await callback.message.edit_caption(
      caption=callback.message.caption + "\n\n✅ **ВЕРИФИЦИРОВАН**",
      parse_mode="Markdown",
  )
  await bot.send_message(
      driver_id,
      "🎉 Поздравляем! Ваша верификация успешно пройдена администратором.",
  )


# --- ИСТОРИЯ ПОЕЗДОК И КВИТАНЦИЯ ---
@router.message(F.text == "📋 История поездок")
async def trip_history(message: Message):
  user_id = message.from_user.id
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
    await message.answer("📋 У вас пока нет завершенных поездок.")
    return

  text = "📋 **Ваша история поездок (последние 5):**\n\n"
  for row in rows:
    order_id, pickup, destination, created_at, status = row
    text += (
        f"🆔 Заказ #{order_id}\n📍 Откуда: {pickup}\n🏁 Куда:"
        f" {destination}\n📅 Дата: {created_at}\nСтатус: {status}\n\n"
    )

  await message.answer(text, parse_mode="Markdown")


# --- МАРКЕТИНГ (Рассылка и промокоды) ---
@router.callback_query(F.data == "admin_promo")
async def admin_promo_start(callback: CallbackQuery, state: FSMContext):
  await callback.message.answer("🎟 Введите текст/код нового промокода:")
  await state.set_state(AdminStates.waiting_for_promo_code)


@router.message(AdminStates.waiting_for_promo_code)
async def admin_promo_code(message: Message, state: FSMContext):
  await state.update_data(promo_code=message.text)
  await message.answer(
      "💰 Введите сумму скидки по этому промокоду (например, 5000):"
  )
  await state.set_state(AdminStates.waiting_for_promo_discount)


@router.message(AdminStates.waiting_for_promo_discount)
async def admin_promo_discount(message: Message, state: FSMContext):
  data = await state.get_data()
  code = data["promo_code"]
  discount = float(message.text)

  async with aiosqlite.connect(DB_NAME) as db:
    await db.execute(
        "INSERT OR REPLACE INTO promos (code, discount) VALUES (?, ?)",
        (code, discount),
    )
    await db.commit()

  await message.answer(
      f"✅ Промокод `{code}` на скидку `{discount}` успешно создан!"
  )
  await state.clear()


# --- ЗАПУСК БОТА ---
async def main():
  await init_db()
  logging.info("Бот Yo'ldosh Taxi запущен и готов к работе!")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
