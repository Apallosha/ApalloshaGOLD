import telebot
from telebot import types
import sqlite3
import random
import time

# ================= НАСТРОЙКИ =================

TOKEN = "ВСТАВЬ_СЮДА_ТОКЕН"
ADMIN_ID = 5333130126
MIN_WITHDRAW = 30
REF_REWARD = 2

bot = telebot.TeleBot(TOKEN)

# ================= КАПЧА =================

captcha_users = {}
EMOJIS = ["🍎", "🍌", "🍇", "🍒", "🍍", "🥝"]

def send_captcha(user_id, chat_id):
    correct = random.choice(EMOJIS)
    options = random.sample(EMOJIS, 4)
    if correct not in options:
        options[0] = correct

    captcha_users[user_id] = correct

    kb = types.InlineKeyboardMarkup()
    for e in options:
        kb.add(types.InlineKeyboardButton(e, callback_data=f"captcha_{e}"))

    bot.send_message(
        chat_id,
        f"🔐 Подтверди, что ты не бот\n\nНажми на: {correct}",
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("captcha_"))
def check_captcha(call):
    user_id = call.from_user.id
    chosen = call.data.split("_")[1]
    correct = captcha_users.get(user_id)

    if not correct:
        return

    if chosen == correct:
        captcha_users.pop(user_id)
        bot.answer_callback_query(call.id, "✅ Успешно!")
        show_main_menu(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ Неверно. Попробуй ещё раз", show_alert=True)
        send_captcha(user_id, call.message.chat.id)

# ================= АНТИ-ФЛУД =================

user_cooldown = {}

def anti_flood(user_id, delay=2):
    now = time.time()
    last = user_cooldown.get(user_id, 0)
    if now - last < delay:
        return False
    user_cooldown[user_id] = now
    return True

# ================= БАЗА =================

db = sqlite3.connect("bot.db", check_same_thread=False)
sql = db.cursor()

sql.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    inviter INTEGER,
    ref_rewarded INTEGER DEFAULT 0
)
""")

sql.execute("""
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT
)
""")

sql.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT,
    channel TEXT,
    reward INTEGER
)
""")

sql.execute("""
CREATE TABLE IF NOT EXISTS user_tasks (
    user_id INTEGER,
    task_id INTEGER,
    UNIQUE(user_id, task_id)
)
""")

sql.execute("""
CREATE TABLE IF NOT EXISTS withdraw_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    price TEXT,
    status TEXT,
    screenshot_id TEXT
)
""")

db.commit()

# ================= СОСТОЯНИЯ =================

user_states = {}
admin_states = {}
broadcast_state = {}

# ================= КЛАВИАТУРЫ =================

def user_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👤 Профиль", "📢 Пригласить")
    kb.add("🎯 Задания", "💸 Вывод G")
    return kb

def admin_keyboard():
    kb = user_keyboard()
    kb.add("👮 Админка")
    return kb

def admin_panel():
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ Канал", callback_data="add_channel"),
        types.InlineKeyboardButton("➖ Канал", callback_data="del_channel")
    )
    kb.add(
        types.InlineKeyboardButton("➕ Задание", callback_data="add_task"),
        types.InlineKeyboardButton("➖ Задание", callback_data="del_task")
    )
    kb.add(types.InlineKeyboardButton("📋 Список каналов", callback_data="list_channels"))
    kb.add(types.InlineKeyboardButton("💰 Заявки на вывод G", callback_data="withdraw_requests"))
    kb.add(types.InlineKeyboardButton("📣 Рассылка", callback_data="broadcast"))
    kb.add(types.InlineKeyboardButton("⬅ Главное меню", callback_data="back_main"))
    return kb

def channels_keyboard():
    kb = types.InlineKeyboardMarkup()
    for ch in sql.execute("SELECT username FROM channels").fetchall():
        kb.add(types.InlineKeyboardButton(f"🔗 {ch[0]}", url=f"https://t.me/{ch[0][1:]}"))
    kb.add(types.InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub"))
    return kb

# ================= /START =================

@bot.message_handler(commands=["start"])
def start(message):
    args = message.text.split()
    inviter = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    if not sql.execute("SELECT id FROM users WHERE id=?", (message.from_user.id,)).fetchone():
        sql.execute("INSERT INTO users (id, inviter) VALUES (?, ?)", (message.from_user.id, inviter))
        db.commit()

    send_captcha(message.from_user.id, message.chat.id)

def show_main_menu(message):
    text = "✅ Готово! Выбери действие 👇"
    if message.from_user.id == ADMIN_ID:
        bot.send_message(message.chat.id, text, reply_markup=admin_keyboard())
    else:
        bot.send_message(message.chat.id, text, reply_markup=user_keyboard())

@bot.callback_query_handler(func=lambda c: c.data == "check_sub")
def check_sub(call):
    for ch in sql.execute("SELECT username FROM channels").fetchall():
        status = bot.get_chat_member(ch[0], call.from_user.id).status
        if status in ["left", "kicked"]:
            bot.answer_callback_query(call.id, "❌ Подпишись на все каналы", show_alert=True)
            return
    show_main_menu(call.message)

# ================= ПРОФИЛЬ =================

@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile(message):
    if message.from_user.id in captcha_users:
        return

    uid = message.from_user.id
    balance = sql.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]
    refs = sql.execute("SELECT COUNT(*) FROM users WHERE inviter=?", (uid,)).fetchone()[0]
    tasks = sql.execute("SELECT COUNT(*) FROM user_tasks WHERE user_id=?", (uid,)).fetchone()[0]

    bot.send_message(
        message.chat.id,
        f"👤 Профиль\n\n"
        f"🆔 ID: {uid}\n"
        f"💰 Баланс: {balance} G\n"
        f"👥 Рефералов: {refs}\n"
        f"🎯 Заданий выполнено: {tasks}"
    )

# ================= ПРИГЛАСИТЬ =================

@bot.message_handler(func=lambda m: m.text == "📢 Пригласить")
def invite(message):
    if message.from_user.id in captcha_users:
        return

    link = f"https://t.me/{bot.get_me().username}?start={message.from_user.id}"
    bot.send_message(
        message.chat.id,
        "📢 Пригласи друзей и зарабатывай G!\n\n"
        "За каждого реферала ты получаешь: 2 G\n\n"
        "⚠ Реферал засчитывается только после того,\n"
        "как он выполнит хотя бы одно задание.\n\n"
        f"Твоя ссылка:\n{link}"
    )

# ================= ЗАДАНИЯ =================

@bot.message_handler(func=lambda m: m.text == "🎯 Задания")
def show_tasks(message):
    if message.from_user.id in captcha_users:
        return

    tasks = sql.execute("SELECT id FROM tasks").fetchall()
    if not tasks:
        bot.send_message(message.chat.id, "🎯 Заданий пока нет")
        return

    kb = types.InlineKeyboardMarkup()
    for t in tasks:
        kb.add(types.InlineKeyboardButton(f"Задание #{t[0]}", callback_data=f"task_{t[0]}"))

    bot.send_message(message.chat.id, "🎯 Доступные задания:", reply_markup=kb)

# ================= ВЫВОД =================

@bot.message_handler(func=lambda m: m.text == "💸 Вывод G")
def withdraw_start(message):
    if message.from_user.id in captcha_users:
        return

    balance = sql.execute("SELECT balance FROM users WHERE id=?", (message.from_user.id,)).fetchone()[0]

    if balance < MIN_WITHDRAW:
        bot.send_message(message.chat.id, "❌ Минимальный вывод: 30 G")
        return

    user_states[message.from_user.id] = "enter_amount"
    bot.send_message(message.chat.id, "💸 Введи сумму для вывода:")

# ================= АДМИНКА =================

@bot.message_handler(func=lambda m: m.text == "👮 Админка")
def open_admin(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(message.chat.id, "👮 Админ-панель:", reply_markup=admin_panel())

@bot.callback_query_handler(func=lambda c: c.data == "back_main")
def back_main(call):
    show_main_menu(call.message)

# ================= ЗАПУСК =================

print("Бот запущен...")
bot.infinity_polling()
