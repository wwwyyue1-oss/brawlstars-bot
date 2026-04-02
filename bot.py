"""
🎮 Brawl Stars Telegram Bot
Показує статистику гравців через офіційне Brawl Stars API
"""

import asyncio
import logging
import os
import urllib.parse
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# ─────────────────────────────────────────────
#  Налаштування (заповни перед запуском!)
# ─────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
BRAWLSTARS_API_KEY = os.environ["BRAWLSTARS_API_KEY"]

BS_API_BASE = "https://api.brawlstars.com/v1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ─────────────────────────────────────────────
#  FSM стан: очікування тега
# ─────────────────────────────────────────────
class Form(StatesGroup):
    waiting_tag = State()


# ─────────────────────────────────────────────
#  Brawl Stars API helper
# ─────────────────────────────────────────────
HEADERS = {
    "Authorization": f"Bearer {BRAWLSTARS_API_KEY}",
    "Accept": "application/json",
}


def normalize_tag(tag: str) -> str:
    """Додає '#' якщо немає, переводить у верхній регістр."""
    tag = tag.strip().upper()
    if not tag.startswith("#"):
        tag = "#" + tag
    return tag


async def fetch_player(tag: str) -> Optional[dict]:
    encoded = urllib.parse.quote(tag, safe="")
    url = f"{BS_API_BASE}/players/{encoded}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status == 200:
                return await resp.json()
            log.warning("BS API %s → %s", url, resp.status)
            return None


async def fetch_battlelog(tag: str) -> Optional[list]:
    encoded = urllib.parse.quote(tag, safe="")
    url = f"{BS_API_BASE}/players/{encoded}/battlelog"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("items", [])
            return None


# ─────────────────────────────────────────────
#  Форматери
# ─────────────────────────────────────────────
RANK_EMOJI = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]


def format_player(p: dict) -> str:
    name = p.get("name", "?")
    tag = p.get("tag", "?")
    trophies = p.get("trophies", 0)
    highest = p.get("highestTrophies", 0)
    level = p.get("expLevel", 0)
    victories_3v3 = p.get("3vs3Victories", 0)
    solo_wins = p.get("soloVictories", 0)
    duo_wins = p.get("duoVictories", 0)
    club = p.get("club", {})
    club_name = club.get("name", "немає") if club else "немає"

    brawlers = p.get("brawlers", [])
    total_brawlers = len(brawlers)
    sorted_b = sorted(brawlers, key=lambda x: x.get("trophies", 0), reverse=True)
    top_brawlers = ""
    for i, b in enumerate(sorted_b[:5]):
        emoji = RANK_EMOJI[i]
        top_brawlers += (
            f"  {emoji} {b['name'].title()} — "
            f"🏆 {b['trophies']} (макс: {b['highestTrophies']}) | "
            f"⚡ {b['power']} рівень\n"
        )

    lines = [
        f"🎮 <b>{name}</b>  <code>{tag}</code>",
        f"",
        f"🏆 Трофеї: <b>{trophies:,}</b>  (рекорд: {highest:,})",
        f"⭐ Рівень досвіду: <b>{level}</b>",
        f"🎖 Клуб: <b>{club_name}</b>",
        f"",
        f"🎯 Перемоги 3v3: <b>{victories_3v3:,}</b>",
        f"👤 Соло (Showdown): <b>{solo_wins:,}</b>",
        f"👥 Дуо (Showdown): <b>{duo_wins:,}</b>",
        f"",
        f"🦸 Бравлерів розблоковано: <b>{total_brawlers}</b>",
        f"",
        f"🔝 Топ-5 бравлерів:",
        top_brawlers.rstrip(),
    ]
    return "\n".join(lines)


RESULT_EMOJI = {"victory": "✅ Перемога", "defeat": "❌ Поразка", "draw": "🤝 Нічия"}
MODE_NAMES = {
    "brawlBall": "⚽ Brawl Ball",
    "gemGrab": "💎 Gem Grab",
    "heist": "💰 Heist",
    "bounty": "⭐ Bounty",
    "siege": "🤖 Siege",
    "hotZone": "🔥 Hot Zone",
    "knockout": "🥊 Knockout",
    "wipeout": "💥 Wipeout",
    "showdown": "☠️ Solo Showdown",
    "duoShowdown": "👥 Duo Showdown",
    "basketBrawl": "🏀 Basket Brawl",
    "volley": "🏐 Volleybrawl",
    "snowtelBrawl": "🏨 Snowtel Throwdown",
    "unknown": "❓ Невідомо",
}


def format_battles(battles: list) -> str:
    if not battles:
        return "😕 Бойовий журнал порожній або недоступний."
    lines = ["⚔️ <b>Останні 5 боїв:</b>\n"]
    for b in battles[:5]:
        event = b.get("event", {})
        battle = b.get("battle", {})
        mode_key = event.get("mode", "unknown")
        mode = MODE_NAMES.get(mode_key, mode_key)
        map_name = event.get("map", "?")
        result_key = battle.get("result", "")
        result = RESULT_EMOJI.get(result_key, f"❓ {result_key}")
        trophy_change = battle.get("trophyChange", None)
        trophy_str = ""
        if trophy_change is not None:
            sign = "+" if trophy_change >= 0 else ""
            trophy_str = f"  ({sign}{trophy_change} 🏆)"
        brawler = ""
        # find own brawler in teams
        teams = battle.get("teams", [])
        for team in teams:
            for player in team:
                if player.get("brawler"):
                    brawler = player["brawler"].get("name", "").title()
                    break
            if brawler:
                break
        lines.append(
            f"{mode}\n"
            f"🗺 {map_name}\n"
            f"{result}{trophy_str}\n"
        )
    return "\n".join(lines)


# ─────────────────────────────────────────────
#  Клавіатури
# ─────────────────────────────────────────────
def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Переглянути статистику", callback_data="ask_tag")],
        [InlineKeyboardButton(text="ℹ️ Допомога", callback_data="help")],
    ])


def player_keyboard(tag: str) -> InlineKeyboardMarkup:
    safe_tag = tag.replace("#", "")
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚔️ Останні бої", callback_data=f"battles:{safe_tag}"),
            InlineKeyboardButton(text="🔄 Оновити", callback_data=f"refresh:{safe_tag}"),
        ],
        [InlineKeyboardButton(text="🔍 Інший гравець", callback_data="ask_tag")],
    ])


# ─────────────────────────────────────────────
#  Хендлери
# ─────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(msg: Message):
    await msg.answer(
        "👋 Привіт! Я бот для перегляду статистики в <b>Brawl Stars</b>.\n\n"
        "Надішли свій тег гравця (наприклад: <code>#ABC123</code>) "
        "або скористайся кнопкою нижче.",
        parse_mode="HTML",
        reply_markup=main_keyboard(),
    )


@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📖 <b>Як використовувати бота:</b>\n\n"
        "1️⃣ Надішли команду /stats або натисни кнопку\n"
        "2️⃣ Введи свій тег гравця (з # або без)\n"
        "3️⃣ Отримай повну статистику!\n\n"
        "🏷 Тег знаходиться у профілі гравця в грі.\n\n"
        "<b>Команди:</b>\n"
        "/start — головне меню\n"
        "/stats — ввести тег гравця\n"
        "/help — ця довідка",
        parse_mode="HTML",
    )


@dp.message(Command("stats"))
@dp.callback_query(F.data == "ask_tag")
async def ask_tag(event, state: FSMContext):
    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()
    await state.set_state(Form.waiting_tag)
    await msg.answer(
        "🏷 Введи тег гравця Brawl Stars:\n"
        "<i>Наприклад: <code>#ABC123</code> або просто <code>ABC123</code></i>",
        parse_mode="HTML",
    )


@dp.message(Form.waiting_tag)
async def handle_tag(msg: Message, state: FSMContext):
    await state.clear()
    tag = normalize_tag(msg.text.strip())
    await show_stats(msg, tag)


@dp.callback_query(F.data.startswith("refresh:"))
async def cb_refresh(call: CallbackQuery):
    await call.answer("🔄 Оновлюю...")
    tag = "#" + call.data.split(":", 1)[1]
    await show_stats(call.message, tag, edit=True)


@dp.callback_query(F.data.startswith("battles:"))
async def cb_battles(call: CallbackQuery):
    await call.answer()
    tag = "#" + call.data.split(":", 1)[1]
    wait = await call.message.answer("⏳ Завантажую бойовий журнал...")
    battles = await fetch_battlelog(tag)
    await wait.delete()
    if battles is None:
        await call.message.answer("❌ Не вдалося отримати бойовий журнал.")
        return
    await call.message.answer(format_battles(battles), parse_mode="HTML")


@dp.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery):
    await call.answer()
    await cmd_help(call.message)


async def show_stats(msg: Message, tag: str, edit: bool = False):
    wait = await msg.answer("⏳ Отримую дані...")
    player = await fetch_player(tag)
    await wait.delete()

    if player is None:
        await msg.answer(
            f"❌ Гравця з тегом <code>{tag}</code> не знайдено.\n"
            "Перевір правильність тегу та спробуй ще раз.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Спробувати знову", callback_data="ask_tag")]
            ]),
        )
        return

    text = format_player(player)
    keyboard = player_keyboard(tag)
    if edit:
        try:
            await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ─────────────────────────────────────────────
#  Запуск
# ─────────────────────────────────────────────
async def main():
    log.info("🚀 Бот запускається...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
