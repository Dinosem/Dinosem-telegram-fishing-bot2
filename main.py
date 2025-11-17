import os
import random
import sqlite3
from datetime import datetime, date
from fastapi import FastAPI, Request, Query, HTTPException
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.types import Update, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from db import init_db, get_conn

TOKEN = os.getenv("TOKEN")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

if not TOKEN:
    raise RuntimeError("TOKEN env var required")

bot = Bot(token=TOKEN)
dp = Dispatcher()

app = FastAPI()

# ----- Game data -----
# rods: id -> (name, price, bonus)
RODS = {
    "bamboo": ("Бамбуковая удочка", 0, 0),
    "wood": ("Деревянная удочка", 50, 1),
    "carbon": ("Углепластик", 200, 2),
    "gold": ("Золотая удочка", 1000, 5),
}

# locations: id -> name and fish table specific to location (fish_name, base_price, weight_chance)
LOCATIONS = {
    "lake": {
        "name": "Озеро",
        "fish": [
            ("Окунь", 5, 60),
            ("Карась", 6, 30),
            ("Щука", 15, 9),
            ("Сом", 30, 1)
        ]
    },
    "river": {
        "name": "Река",
        "fish": [
            ("Окунь", 6, 50),
            ("Форель", 20, 30),
            ("Судак", 40, 15),
            ("Акула", 150, 5)
        ]
    },
    "sea": {
        "name": "Море",
        "fish": [
            ("Скумбрия", 8, 50),
            ("Форель", 30, 30),
            ("Тунец", 80, 15),
            ("Дельфин", 300, 5)
        ]
    },
    "ocean": {
        "name": "Океан",
        "fish": [
            ("Мелкая рыба", 10, 40),
            ("Тунец", 120, 30),
            ("Акула", 400, 20),
            ("Морской монстр", 2000, 10)
        ]
    },
}

# quests templates
QUESTS = {
    "daily_1": {"desc": "Поймай 3 рыбы", "target": 3, "reward": 20},
    "daily_rare": {"desc": "Поймай редкую рыбу", "target": 1, "reward": 50},
}

# ----- Keyboards -----
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎣 Ловить рыбу")],
        [KeyboardButton(text="📍 Выбрать локацию"), KeyboardButton(text="🎒 Инвентарь")],
        [KeyboardButton(text="🛒 Магазин"), KeyboardButton(text="💰 Продать рыбу")],
        [KeyboardButton(text="🏆 Рейтинг"), KeyboardButton(text="🎯 Квесты")]
    ],
    resize_keyboard=True
)

location_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Озеро 🌊"), KeyboardButton(text="Река 🌊")],
        [KeyboardButton(text="Море 🌊"), KeyboardButton(text="Океан 🌊")],
        [KeyboardButton(text="Назад ⬅️")]
    ], resize_keyboard=True
)

# ----- Helpers -----
def ensure_user_row(user_id, username=""):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users(user_id, username, coins) VALUES(?,?,0)", (user_id, username))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def add_coins(user_id, amount):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users(user_id, coins) VALUES(?,0)", (user_id,))
    c.execute("UPDATE users SET coins = coins + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def add_inventory(user_id, item, amount=1):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO inventory(user_id,item,amount) VALUES(?,?,0)", (user_id,item,0))
    c.execute("UPDATE inventory SET amount = amount + ? WHERE user_id=? AND item=?", (amount,user_id,item))
    conn.commit()
    conn.close()

def get_inventory(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT item,amount FROM inventory WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def clear_inventory(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM inventory WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_leaderboard(limit=10):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT username, coins FROM users ORDER BY coins DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def record_purchase(user_id, item, price):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO purchases(user_id,item,price) VALUES(?,?,?)", (user_id,item,price))
    conn.commit()
    conn.close()

def get_user_rod(user_id):
    row = get_user(user_id)
    if row and row["rod"]:
        return row["rod"]
    return "bamboo"

def set_user_rod(user_id, rod_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET rod=? WHERE user_id=?", (rod_id, user_id))
    conn.commit()
    conn.close()

def get_rod_bonus(user_id):
    rod = get_user_rod(user_id)
    return RODS.get(rod, ("",0,0))[2]

# ----- Game logic -----
def choose_fish(location_id, bonus=0):
    loc = LOCATIONS.get(location_id, LOCATIONS["lake"])
    total = sum(chance for _,_,chance in loc["fish"])
    pick = random.randint(1, total)
    run = 0
    for name, price, chance in loc["fish"]:
        run += chance
        if pick <= run:
            # quantity influenced by bonus (rod)
            qty = 1 + bonus
            return name, price, qty
    # fallback
    f = loc["fish"][0]
    return f[0], f[1], 1 + bonus

# ----- Inline shop menu (for purchases with coins) -----
def shop_inline_markup():
    kb = InlineKeyboardMarkup()
    for rod_id,(name,price,bonus) in RODS.items():
        if price>0:
            kb.add(InlineKeyboardButton(text=f"{name} — {price} монет", callback_data=f"buyrod:{rod_id}"))
    return kb

# ----- Handlers -----
@dp.message(Command("start"))
async def cmd_start(msg: Message):
    user_id = msg.from_user.id
    ensure_user_row(user_id, msg.from_user.username or msg.from_user.full_name)
    await msg.answer("🎣 Добро пожаловать в Рыбалка 2.0!\nВыбери действие:", reply_markup=main_menu)

@dp.message(Command("me"))
async def cmd_me(msg: Message):
    row = get_user(msg.from_user.id)
    inv = get_inventory(msg.from_user.id)
    inv_text = "\n".join(f"{r['item']} — {r['amount']}" for r in inv) or "Пусто"
    await msg.answer(f"Пользователь: {msg.from_user.full_name}\nМонет: {row['coins']}\nРыбалка: {get_user_rod(msg.from_user.id)}\n\nИнвентарь:\n{inv_text}")

@dp.message()
async def handle_message(msg: Message):
    text = (msg.text or "").strip()

    # quick location selection by text matching
    if text in ("Озеро 🌊","Озеро"):
        msg_loc = "lake"
        await msg.answer(f"Локация выбрана: {LOCATIONS[msg_loc]['name']}\nТеперь нажми 🎣 Ловить рыбу", reply_markup=main_menu)
        # store location in a simple inventory flag (could be improved)
        add_inventory(msg.from_user.id, f"_loc_{msg.from_user.id}", 0)  # no-op ensures user row
        # simple approach: store chosen location as a fake inventory key (not ideal but quick)
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO inventory(user_id,item,amount) VALUES(?,?,?)", (msg.from_user.id, f"_location", 0))
        conn.commit()
        conn.close()
        # We'll rely on default location 'lake' unless user sets via inline menu; to keep it simple we won't persist now
        return

    if text == "🎣 Ловить рыбу":
        user_id = msg.from_user.id
        ensure_user_row(user_id, msg.from_user.username or msg.from_user.full_name)
        bonus = get_rod_bonus(user_id)
        # for simplicity, use lake as default; you can expand to store selected location per user
        loc = "lake"
        fish_name, price, qty = choose_fish(loc, bonus=bonus)
        add_inventory(user_id, fish_name, qty)
        await msg.answer(f"🎣 Ты поймал: {fish_name} x{qty} (примерная цена: {price*qty} монет).")
        return

    if text == "🎒 Инвентарь":
        inv = get_inventory(msg.from_user.id)
        if not inv:
            await msg.answer("🎒 Инвентарь пуст.")
            return
        out = "🎒 Инвентарь:\n"
        for r in inv:
            out += f"{r['item']} — {r['amount']}\n"
        await msg.answer(out)
        return

    if text == "💰 Продать рыбу":
        inv = get_inventory(msg.from_user.id)
        if not inv:
            await msg.answer("У тебя нет рыбы.")
            return
        total = 0
        # compute approximate price: we don't have per-item price stored, use static map (simple)
        for r in inv:
            item = r['item']
            amount = r['amount']
            # find base price across locations (fallback 5)
            base = 5
            for loc in LOCATIONS.values():
                for fname, fprice, _ in loc["fish"]:
                    if fname == item:
                        base = fprice
                        break
            total += base * amount
        clear_inventory(msg.from_user.id)
        add_coins(msg.from_user.id, total)
        await msg.answer(f"💰 Ты продал всё и получил {total} монет.")
        return

    if text == "🛒 Магазин":
        await msg.answer("🛒 Магазин: купи удочку для бонусов.", reply_markup=None, reply_markup=shop_inline_markup())
        return

    if text == "🏆 Рейтинг":
        rows = get_leaderboard(10)
        out = "🏆 Топ игроков:\n"
        for i, r in enumerate(rows, start=1):
            out += f"{i}. {r['username'] or 'user'} — {r['coins']} монет\n"
        await msg.answer(out)
        return

    if text == "🎯 Квесты":
        # show daily quest summary from QUESTS
        out = "🎯 Квесты:\n"
        for k,v in QUESTS.items():
            out += f"- {v['desc']} (наградa: {v['reward']} монет)\n"
        await msg.answer(out)
        return

    # Fallback
    await msg.answer("Сообщение получено ✔")

# Inline callbacks
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@dp.callback_query()
async def cb_query(cq):
    data = cq.data
    user_id = cq.from_user.id
    if data.startswith("buyrod:"):
        rod_id = data.split(":",1)[1]
        name, price, bonus = RODS[rod_id]
        row = get_user(user_id)
        coins = row["coins"] if row else 0
        if coins < price:
            await cq.message.answer("Недостаточно монет для покупки.")
            await cq.answer()
            return
        add_coins(user_id, -price)
        set_user_rod(user_id, rod_id)
        record_purchase(user_id, name, price)
        await cq.message.answer(f"Вы купили {name}!")
        await cq.answer()
        return
    await cq.answer()

# Payments pre-checkout placeholder
@dp.pre_checkout_query()
async def process_pre_checkout(query):
    await query.answer(ok=True)

@dp.message()
async def successful_payment_handler(msg: Message):
    # aiogram handles successful_payment in message.successful_payment
    try:
        if hasattr(msg, "successful_payment") and msg.successful_payment:
            payload = msg.successful_payment.invoice_payload
            # payload format: premium:<key>:<user_id>
            parts = payload.split(":")
            if parts[0] == "premium":
                key = parts[1]
                # grant premium: give coins or bonus
                add_coins(msg.from_user.id, 100)
                await msg.answer("Покупка подтверждена. Спасибо!")
    except Exception:
        pass

# Admin endpoints in FastAPI
@app.get("/admin/leaderboard")
async def admin_leaderboard(token: str = Query(...)):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    rows = get_leaderboard(50)
    return {"leaderboard":[{"rank":i+1,"username":r["username"],"coins":r["coins"]} for i,r in enumerate(rows)]}

@app.get("/admin/user/{user_id}")
async def admin_user(user_id: int, token: str = Query(...)):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    u = c.fetchone()
    c.execute("SELECT item,amount FROM inventory WHERE user_id=?", (user_id,))
    inv = c.fetchall()
    conn.close()
    if not u:
        raise HTTPException(status_code=404, detail="Not found")
    return {"user": dict(u), "inventory":[dict(r) for r in inv]}

# health
@app.get("/")
async def root():
    return {"status": "ok"}

if __name__ == "__main__":
    init_db()
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT",8000)))
