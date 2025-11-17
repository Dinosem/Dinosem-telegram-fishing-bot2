import asyncio
from fastapi import FastAPI, Request
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.filters import Command
import os

TOKEN = os.getenv("TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

app = FastAPI()

@dp.message(Command("start"))
async def start(msg):
    await msg.answer("🎣 Бот запущен через Webhook!\nГотов к игре!")

@dp.message()
async def echo(msg):
    await msg.answer("Получено сообщение ✔")

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/")
def home():
    return {"status": "ok"}

def start_fastapi():
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=False
    )

def main():
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, start_fastapi)
    loop.run_forever()

if __name__ == "__main__":
    main()
