import os
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.filters import Command
import uvicorn

TOKEN = os.getenv("TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

app = FastAPI()


@dp.message(Command("start"))
async def start(msg):
    await msg.answer("🎣 Бот запущен!\nWebhook работает стабильно.")


@dp.message()
async def echo(msg):
    await msg.answer("Сообщение получено ✔")


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.get("/")
async def root():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=False
    )
