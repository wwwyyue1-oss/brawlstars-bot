import asyncio
import logging
import os
import urllib.parse

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
BRAWLSTARS_API_KEY = os.environ["BRAWLSTARS_API_KEY"]
BS_BASE = "https://api.brawlstars.com/v1"
HEADERS = {"Authorization": f"Bearer {BRAWLSTARS_API_KEY}"}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class Form(StatesGroup):
    waiting_tag = State()


async def get_player(tag: str):
    tag = tag.strip().upper()
    if not tag.startswith("#"):
        tag = "#" + tag
    encoded = urllib.parse.quote(tag, safe="")
    url = f"{BS_BASE}/players/{encoded}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=HEADERS) as r:
            if r.status == 200:
                return await r.json(), tag
            return None, tag


async def get_battles(tag: str):
    encoded = urllib.parse.quote(tag, safe="")
    url = f"{BS_BASE}/players/{encoded}/battlelog"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=HEADERS) as r:
            if r.status == 200:
                data = await r.json()
                return data.get("items", [])
            return None


def player_text(p: dict) -> str:
    brawlers = sorted(p.get("brawlers", []), key=lambda x: x.get("trophies", 0), reverse=True)
    top = ""
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, b in enumerate(brawlers[:5]):
        top += f"  {medals[i]} {b['name'].title()} — {b['trophies']} 🏆 | ⚡{b['power']}\n"

    club = p.get("club", {})
    club_name = club.get("name", "немає") if club else "немає"

    return (
        f"🎮 <b>{p.get('name')}</b> <code>{p.get('tag')}</code>\n\n"
        f"🏆 Трофеї: <b>{p.get('trophies', 0):,}</b> (рекорд: {p.get('highestTrophies', 0):,})\n"
        f"⭐ Рівень: <b>{p.get('expLevel', 0)}</b>\n"
        f"🎖 Клуб: <b>{club_name}</b>\n\n"
        f"🎯 Перемоги 3v3: <b>{p.get('3vs3Victories', 0):,}</b>\n"
        f"👤 Соло: <b>{p.get('soloVictories', 0):,}</b>\n"
        f"👥 Дуо: <b>{p.get('duoVictories', 0):,}</b>\n\n"
        f"🦸 Бравлерів: <b>{len(brawlers)}</b>\n\n"
        f"🔝 Топ-5:\n{top}"
    )


def battles_text(battles: list) -> str:
    if not battles:
        return "😕 Бойовий журнал порожній."
    modes = {
        "brawlBall": "⚽ Brawl Ball", "gemGrab": "💎 Gem Grab",
        "heist": "💰 Heist", "bounty": "⭐ Bounty",
        "hotZone": "🔥 Hot Zone", "knockout": "🥊 Knockout",
        "showdown": "☠️ Showdown", "duoShowdown": "👥 Duo Showdown",
    }
    results = {"victory": "✅ Перемога", "defeat": "❌ Поразка", "draw": "🤝 Нічия"}
    text = "⚔️ <b>Останні бої:</b>\n\n"
    for b in battles[:5]:
        event = b.get("event", {})
        battle = b.get("battle", {})
        mode = modes.get(event.get("mode", ""), event.get("mode", "?"))
        map_name = event.get("map", "?")
        result = results.get(battle.get("result", ""), "❓")
        tc = battle.get("trophyChange")
        tc_str = f" ({'+' if tc and tc >= 0 else ''}{tc} 🏆)" if tc is not None else ""
        text += f"{mode} — {map_name}\n{result}{tc_str}\n\n"
    return text


def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Переглянути статистику", callback_data="ask_tag")],
    ])


def kb_player(tag: str):
    t = tag.replace("#", "")
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚔️ Бої", callback_data=f"battles:{t}"),
            InlineKeyboardButton(text="🔄 Оновити", callback_data=f"refresh:{t}"),
        ],
        [InlineKeyboardButton(text="🔍 Інший гравець", callback_data="ask_tag")],
    ])


@dp.message(CommandStart())
async def start(msg: Message):
    await msg.answer(
        "👋 Привіт! Надішли свій тег гравця Brawl Stars\n"
        "або натисни кнопку нижче 👇",
        reply_markup=kb_main(),
    )


@dp.message(Command("stats"))
@dp.callback_query(F.data == "ask_tag")
async def ask_tag(event, state: FSMContext):
    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()
    await state.set_state(Form.waiting_tag)
    await msg.answer("🏷 Введи тег гравця (наприклад: <code>#ABC123</code>):", parse_mode="HTML")


@dp.message(Form.waiting_tag)
async def handle_tag(msg: Message, state: FSMContext):
    await state.clear()
    wait = await msg.answer("⏳ Завантажую...")
    player, tag = await get_player(msg.text)
    await wait.delete()
    if not player:
        await msg.answer("❌ Гравця не знайдено. Перевір тег і спробуй ще раз.", reply_markup=kb_main())
        return
    await msg.answer(player_text(player), parse_mode="HTML", reply_markup=kb_player(tag))


@dp.callback_query(F.data.startswith("refresh:"))
async def refresh(call: CallbackQuery):
    await call.answer("🔄 Оновлюю...")
    tag = "#" + call.data.split(":", 1)[1]
    player, tag = await get_player(tag)
    if not player:
        await call.message.answer("❌ Не вдалося оновити.")
        return
    try:
        await call.message.edit_text(player_text(player), parse_mode="HTML", reply_markup=kb_player(tag))
    except Exception:
        await call.message.answer(player_text(player), parse_mode="HTML", reply_markup=kb_player(tag))


@dp.callback_query(F.data.startswith("battles:"))
async def battles(call: CallbackQuery):
    await call.answer()
    tag = "#" + call.data.split(":", 1)[1]
    wait = await call.message.answer("⏳ Завантажую бої...")
    data = await get_battles(tag)
    await wait.delete()
    await call.message.answer(battles_text(data or []), parse_mode="HTML")


async def main():
    logging.info("Бот запускається...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
