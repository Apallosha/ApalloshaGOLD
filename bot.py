import telebot
from telebot import types
import sqlite3
import random
import time

# ================= НАСТРОЙКИ =================

TOKEN = "7953334215:AAHqDRyba_ep8kmZIeTK26t72Ym6vC5JGi0"
ADMIN_ID = 5333130126
MIN_WITHDRAW = 30
REF_REWARD = 2

bot = telebot.TeleBot(TOKEN)

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
    ref_rewarded INTEGER DEFAULT 0,
    captcha_passed INTEGER DEFAULT 0
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
    kb.add(types.InlineKeyboardButton("⬅ Главное меню", callback_data="back_menu"))
    return kb

# ================= КАПЧА =================

captcha_emojis = ["🍎", "🍌", "🍇", "🍍"]

@bot.message_handler(commands=["start"])
def start(message):
    args = message.text.split()
    inviter = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    if not sql.execute("SELECT id FROM users WHERE id=?", (message.from_user.id,)).fetchone():
        sql.execute("INSERT INTO users (id, inviter) VALUES (?, ?)", (message.from_user.id, inviter))
        db.commit()

    emoji = random.choice(captcha_emojis)
    user_states[message.from_user.id] = f"captcha_{emoji}"

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for e in captcha_emojis:
        kb.add(e)

    bot.send_message(message.chat.id, f"Нажми на: {emoji}", reply_markup=kb)

@bot.message_handler(func=lambda m: m.from_user.id in user_states and user_states[m.from_user.id].startswith("captcha_"))
def captcha_check(message):
    correct = user_states[message.from_user.id].split("_")[1]
    if message.text == correct:
        sql.execute("UPDATE users SET captcha_passed=1 WHERE id=?", (message.from_user.id,))
        db.commit()
        user_states.pop(message.from_user.id)
        show_main_menu(message)
    else:
        bot.send_message(message.chat.id, "❌ Неверно, попробуй ещё")

# ================= ГЛАВНОЕ МЕНЮ =================

def show_main_menu(message):
    text = "✅ Готово! Выбери действие 👇"
    if message.from_user.id == ADMIN_ID:
        bot.send_message(message.chat.id, text, reply_markup=admin_keyboard())
    else:
        bot.send_message(message.chat.id, text, reply_markup=user_keyboard())

# ================= ПРОФИЛЬ =================

@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile(message):
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
    link = f"https://t.me/{bot.get_me().username}?start={message.from_user.id}"
    bot.send_message(
        message.chat.id,
        "📢 Пригласи друзей и зарабатывай G! За каждого реферала ты получаешь: 2 G\n\n"
        "⚠ Реферал засчитывается только после того как он выполнит хотя бы одно задание.\n\n"
        f"Твоя ссылка:\n{link}"
    )

# ================= АДМИНКА =================

@bot.message_handler(func=lambda m: m.text == "👮 Админка")
def open_admin(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(message.chat.id, "👮 Админ-панель:", reply_markup=admin_panel())

@bot.callback_query_handler(func=lambda c: c.data == "back_menu")
def back_menu(call):
    show_main_menu(call.message)

# ================= РАССЫЛКА =================

@bot.callback_query_handler(func=lambda c: c.data == "broadcast")
def start_broadcast(call):
    admin_states[call.from_user.id] = "broadcast"
    bot.send_message(call.message.chat.id, "📣 Введи текст рассылки:")

@bot.message_handler(func=lambda m: admin_states.get(m.from_user.id) == "broadcast")
def process_broadcast(message):
    users = sql.execute("SELECT id FROM users").fetchall()
    for u in users:
        try:
            bot.send_message(u[0], message.text)
        except:
            pass
    admin_states.pop(message.from_user.id)
    bot.send_message(message.chat.id, "✅ Рассылка отправлена")

# ================= ЗАПУСК =================

print("Бот запущен...")
bot.infinity_polling()
