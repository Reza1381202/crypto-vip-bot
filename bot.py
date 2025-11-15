import sqlite3
import requests
import asyncio
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

TOKEN = "BOT_TOKEN_HERE"  # ← توکن رباتی که از BotFather گرفتی رو اینجا بزن

# ---------- Database ----------
conn = sqlite3.connect("vipbot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    is_vip INTEGER DEFAULT 0,
    vip_expire TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    symbol TEXT,
    target REAL,
    direction TEXT
)
""")

conn.commit()

# ---------- Utility ----------
def get_price(symbol="BTCUSDT"):
    r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}").json()
    return float(r["price"])

def is_vip(user_id):
    cur.execute("SELECT is_vip, vip_expire FROM users WHERE user_id=?", (user_id,))
    data = cur.fetchone()
    if not data:
        return False
    vip, exp = data
    if vip == 1 and exp and datetime.now() < datetime.fromisoformat(exp):
        return True
    return False

def add_user(user_id):
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

# ---------- Start ----------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    add_user(user_id)

    if is_vip(user_id):
        keyboard = [
            [InlineKeyboardButton("📈 قیمت حرفه‌ای", callback_data="pro_price")],
            [InlineKeyboardButton("🚨 هشدارهای نامحدود", callback_data="alert")],
            [InlineKeyboardButton("⚙️ مدیریت اشتراک", callback_data="vip_info")],
        ]
        text = "🎉 خوش اومدی! شما کاربر VIP هستی."
    else:
        keyboard = [
            [InlineKeyboardButton("📈 قیمت لحظه‌ای", callback_data="price")],
            [InlineKeyboardButton("⏰ ایجاد هشدار رایگان", callback_data="alert")],
            [InlineKeyboardButton("💎 خرید VIP", callback_data="vip_buy")],
        ]
        text = "سلام! برای امکانات کامل می‌تونی VIP بشی ✨"

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- Buttons ----------
async def button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.message.chat_id

    await q.answer()

    if q.data == "price":
        btc = get_price("BTCUSDT")
        eth = get_price("ETHUSDT")
        await q.edit_message_text(f"BTC: {btc:,}\nETH: {eth:,}")

    elif q.data == "pro_price":
        btc = get_price("BTCUSDT")
        eth = get_price("ETHUSDT")
        xrp = get_price("XRPUSDT")
        await q.edit_message_text(f"🔥 قیمت حرفه‌ای:\nBTC: {btc:,}\nETH:{eth:,}\nXRP:{xrp:,}")

    elif q.data == "vip_buy":
        keyboard = [
            [InlineKeyboardButton("ماهانه 100 هزار", callback_data="buy_1m")],
            [InlineKeyboardButton("سه ماهه 180 هزار", callback_data="buy_3m")],
            [InlineKeyboardButton("یک‌ساله 500 هزار", callback_data="buy_12m")],
        ]
        await q.edit_message_text("پلن VIP را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif q.data == "buy_1m":
        cur.execute("UPDATE users SET is_vip=1, vip_expire=? WHERE user_id=?", (
            (datetime.now() + timedelta(days=30)).isoformat(), user_id))
        conn.commit()
        await q.edit_message_text("✔️ VIP ماهانه فعال شد!")

    elif q.data == "buy_3m":
        cur.execute("UPDATE users SET is_vip=1, vip_expire=? WHERE user_id=?", (
            (datetime.now() + timedelta(days=90)).isoformat(), user_id))
        conn.commit()
        await q.edit_message_text("✔️ VIP سه‌ماهه فعال شد!")

    elif q.data == "buy_12m":
        cur.execute("UPDATE users SET is_vip=1, vip_expire=? WHERE user_id=?", (
            (datetime.now() + timedelta(days=365)).isoformat(), user_id))
        conn.commit()
        await q.edit_message_text("✔️ VIP یک‌ساله فعال شد!")

    elif q.data == "vip_info":
        cur.execute("SELECT vip_expire FROM users WHERE user_id=?", (user_id,))
        exp = cur.fetchone()
        await q.edit_message_text(f"🔒 تاریخ انقضا: {exp[0]}")

# ---------- Alerts ----------
async def sendalert(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    args = ctx.args

    if not is_vip(user_id):
        cur.execute("SELECT COUNT(*) FROM alerts WHERE user_id=?", (user_id,))
        if cur.fetchone()[0] >= 1:
            await update.message.reply_text("🚫 فقط ۱ هشدار برای کاربران رایگان مجاز است.")
            return

    if len(args) < 3:
        await update.message.reply_text("فرمت صحیح:\n/sendalert BTCUSDT 30000 up")
        return

    symbol = args[0].upper()
    target = float(args[1])
    direction = args[2]

    cur.execute("INSERT INTO alerts (user_id, symbol, target, direction) VALUES (?, ?, ?, ?)",
                (user_id, symbol, target, direction))
    conn.commit()

    await update.message.reply_text("✔️ هشدار ثبت شد.")

# ---------- Alert Checker ----------
async def check_alerts(app):
    while True:
        cur.execute("SELECT * FROM alerts")
        rows = cur.fetchall()

        for row in rows:
            aid, user_id, symbol, target, direction = row
            price = get_price(symbol)

            if (direction == "up" and price >= target) or \
               (direction == "down" and price <= target):

                await app.bot.send_message(user_id, f"🔥 هشدار فعال شد!\n{symbol}: {price:,}")

                cur.execute("DELETE FROM alerts WHERE id=?", (aid,))
                conn.commit()

        await asyncio.sleep(3)

# ---------- MAIN ----------
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sendalert", sendalert))
    app.add_handler(CallbackQueryHandler(button))

    asyncio.create_task(check_alerts(app))

    await app.run_polling()

asyncio.run(main())
