import telebot
from telebot import types
import sqlite3
import random

# ================= НАСТРОЙКИ =================
TOKEN = "7953334215:AAHqDRyba_ep8kmZIeTK26t72Ym6vC5JGi0"
ADMIN_ID = 5333130126
MIN_WITHDRAW = 30
REF_REWARD = 2

# Обязательные каналы (без админки)
REQUIRED_CHANNELS = ["@ApalloshaTgk"]

bot = telebot.TeleBot(TOKEN)

# ================= БАЗА =================
db = sqlite3.connect("bot.db", check_same_thread=False)
sql = db.cursor()

sql.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    inviter INTEGER,
    ref_rewarded INTEGER DEFAULT 0
)""")

sql.execute("""CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT,
    channel TEXT,
    reward INTEGER
)""")

sql.execute("""CREATE TABLE IF NOT EXISTS user_tasks (
    user_id INTEGER,
    task_id INTEGER,
    UNIQUE(user_id, task_id)
)""")

sql.execute("""CREATE TABLE IF NOT EXISTS withdraw_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    price TEXT,
    status TEXT,
    screenshot_id TEXT
)""")

db.commit()

# ================= СОСТОЯНИЯ =================
user_states = {}
admin_states = {}

# ================= КЛАВИАТУРЫ =================
def main_menu(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("👤 Профиль", "📢 Пригласить")
    kb.add("🎯 Задания", "💸 Вывод G")
    if uid == ADMIN_ID:
        kb.add("👮 Админка")
    return kb

def admin_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Задание", "➖ Задание")
    kb.add("💰 Заявки на вывод G", "📣 Рассылка")
    kb.add("⬅ Главное меню")
    return kb

# ================= START =================
@bot.message_handler(commands=["start"])
def start(message):
    args = message.text.split()
    inviter = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    if not sql.execute("SELECT id FROM users WHERE id=?", (message.from_user.id,)).fetchone():
        sql.execute("INSERT INTO users (id, inviter) VALUES (?, ?)", (message.from_user.id, inviter))
        db.commit()

    # Проверка подписки
    for ch in REQUIRED_CHANNELS:
        status = bot.get_chat_member(ch, message.from_user.id).status
        if status in ["left", "kicked"]:
            bot.send_message(message.chat.id, f"❗ Подпишись на {ch} и нажми /start")
            return

    bot.send_message(message.chat.id, "✅ Добро пожаловать!", reply_markup=main_menu(message.from_user.id))

# ================= ПРОФИЛЬ =================
@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile(message):
    uid = message.from_user.id
    balance = sql.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]
    refs = sql.execute("SELECT COUNT(*) FROM users WHERE inviter=?", (uid,)).fetchone()[0]
    tasks = sql.execute("SELECT COUNT(*) FROM user_tasks WHERE user_id=?", (uid,)).fetchone()[0]

    bot.send_message(message.chat.id,
        f"👤 Профиль\n\n🆔 ID: {uid}\n💰 Баланс: {balance} G\n👥 Рефералов: {refs}\n🎯 Заданий: {tasks}")

# ================= ПРИГЛАСИТЬ =================
@bot.message_handler(func=lambda m: m.text == "📢 Пригласить")
def invite(message):
    link = f"https://t.me/{bot.get_me().username}?start={message.from_user.id}"
    bot.send_message(message.chat.id,
        "📢 Пригласи друзей и зарабатывай G!\n\n"
        "За каждого реферала ты получаешь: 2 G\n\n"
        "⚠ Реферал засчитывается только после того,\n"
        "как он выполнит хотя бы одно задание.\n\n"
        f"Твоя ссылка:\n{link}")

# ================= ЗАДАНИЯ =================
@bot.message_handler(func=lambda m: m.text == "🎯 Задания")
def show_tasks(message):
    tasks = sql.execute("SELECT id FROM tasks").fetchall()
    if not tasks:
        bot.send_message(message.chat.id, "🎯 Заданий пока нет")
        return

    kb = types.InlineKeyboardMarkup()
    for t in tasks:
        kb.add(types.InlineKeyboardButton(f"Задание #{t[0]}", callback_data=f"task_{t[0]}"))

    bot.send_message(message.chat.id, "🎯 Доступные задания:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("task_"))
def open_task(call):
    task_id = int(call.data.split("_")[1])

    if sql.execute("SELECT 1 FROM user_tasks WHERE user_id=? AND task_id=?", (call.from_user.id, task_id)).fetchone():
        bot.answer_callback_query(call.id, "❌ Уже выполнено", show_alert=True)
        return

    text, channel = sql.execute("SELECT text, channel FROM tasks WHERE id=?", (task_id,)).fetchone()

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔗 Перейти в канал", url=f"https://t.me/{channel[1:]}"))
    kb.add(types.InlineKeyboardButton("✅ Проверить", callback_data=f"checktask_{task_id}"))

    bot.send_message(call.message.chat.id, text, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("checktask_"))
def check_task(call):
    task_id = int(call.data.split("_")[1])
    channel, reward = sql.execute("SELECT channel, reward FROM tasks WHERE id=?", (task_id,)).fetchone()

    status = bot.get_chat_member(channel, call.from_user.id).status
    if status in ["left", "kicked"]:
        bot.answer_callback_query(call.id, "❌ Ты не подписан", show_alert=True)
        return

    sql.execute("INSERT INTO user_tasks (user_id, task_id) VALUES (?, ?)", (call.from_user.id, task_id))
    sql.execute("UPDATE users SET balance = balance + ? WHERE id=?", (reward, call.from_user.id))

    inviter, rewarded = sql.execute("SELECT inviter, ref_rewarded FROM users WHERE id=?", (call.from_user.id,)).fetchone()
    if inviter and rewarded == 0:
        sql.execute("UPDATE users SET balance = balance + ? WHERE id=?", (REF_REWARD, inviter))
        sql.execute("UPDATE users SET ref_rewarded=1 WHERE id=?", (call.from_user.id,))
        bot.send_message(inviter, "🎉 Твой реферал выполнил задание!\nТы получил 2 G")

    db.commit()
    bot.send_message(call.message.chat.id, f"✅ Задание выполнено!\n💰 Ты получил {reward} G")

# ================= ВЫВОД =================
@bot.message_handler(func=lambda m: m.text == "💸 Вывод G")
def withdraw(message):
    balance = sql.execute("SELECT balance FROM users WHERE id=?", (message.from_user.id,)).fetchone()[0]

    if balance < MIN_WITHDRAW:
        bot.send_message(message.chat.id, "❌ Минимальный вывод: 30 G")
        return

    user_states[message.from_user.id] = "amount"
    bot.send_message(message.chat.id, "💸 Введи сумму:")

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id) == "amount")
def process_amount(message):
    if not message.text.isdigit():
        return bot.send_message(message.chat.id, "❌ Введи число")

    amount = int(message.text)
    balance = sql.execute("SELECT balance FROM users WHERE id=?", (message.from_user.id,)).fetchone()[0]

    if amount < MIN_WITHDRAW or amount > balance:
        return bot.send_message(message.chat.id, "❌ Неверная сумма")

    price = f"{amount}.{random.randint(1,99):02d}"

    sql.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amount, message.from_user.id))
    sql.execute("INSERT INTO withdraw_requests (user_id, amount, price, status) VALUES (?, ?, ?, 'waiting')",
                (message.from_user.id, amount, price))
    db.commit()

    user_states[message.from_user.id] = "screenshot"

    bot.send_message(message.chat.id, f"💸 Выставь скин за {price} G")
    bot.send_message(message.chat.id,
        "📌 Инструкция:\n\n"
        "1️⃣ Выставь скин с патерном по указаной цене\n"
        "2️⃣ Отправь скриншот\n"
        "3️⃣ Ожидай обработку\n\nУдачи 🍀")

@bot.message_handler(content_types=["photo"])
def screenshot(message):
    if user_states.get(message.from_user.id) != "screenshot":
        return

    file_id = message.photo[-1].file_id
    sql.execute("UPDATE withdraw_requests SET screenshot_id=? WHERE user_id=? AND status='waiting'",
                (file_id, message.from_user.id))
    db.commit()

    user_states.pop(message.from_user.id)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Принять", callback_data=f"approve_{message.from_user.id}"))
    kb.add(types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{message.from_user.id}"))

    bot.send_photo(ADMIN_ID, file_id,
                   caption=f"💸 Заявка на вывод\nID: {message.from_user.id}",
                   reply_markup=kb)

    bot.send_message(message.chat.id, "✅ Заявка отправлена")

# ================= АДМИНКА =================
@bot.message_handler(func=lambda m: m.text == "👮 Админка")
def admin(message):
    if message.from_user.id == ADMIN_ID:
        bot.send_message(message.chat.id, "👮 Админ-панель", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "⬅ Главное меню")
def back(message):
    bot.send_message(message.chat.id, "⬅ Главное меню", reply_markup=main_menu(message.from_user.id))

# ================= ЗАПУСК =================
print("Бот запущен...")
bot.infinity_polling()
