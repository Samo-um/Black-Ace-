# ============================================================
# ♠️ BLACK ACE CASINO — SINCE 1976 • MACAU
# bot.py — ПОЛНАЯ ВЕРСИЯ, БЕЗ ОБРЕЗКИ
# GitHub: Samo-um / black-ace
# Приватный репозиторий
# ============================================================

import asyncio
import random
import sqlite3
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.storage.memory import MemoryStorage

# ================= CONFIG =================
TOKEN = os.getenv("BOT_TOKEN", "9169172553:AAGj2eAvkkmbUFaM_JrlebT9LIpXP-aWqu4")
ADMIN_ID = 8875607457
WEBAPP_URL = "https://samo-um.github.io/black-ace/"

CASINO_NAME = "♠️ BLACK ACE CASINO"
START_BALANCE = 1000
DAILY_BONUS = 500
VIP_THRESHOLD = 50000

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================= DATABASE =================
class Database:
    def __init__(self, path="black_ace.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.cur = self.conn.cursor()
        self._init()

    def _init(self):
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT, first_name TEXT,
                balance INTEGER DEFAULT 1000,
                level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0,
                billiard_wins INTEGER DEFAULT 0, billiard_losses INTEGER DEFAULT 0,
                billiard_games INTEGER DEFAULT 0,
                total_bet INTEGER DEFAULT 0, total_win INTEGER DEFAULT 0, total_lose INTEGER DEFAULT 0,
                biggest_win INTEGER DEFAULT 0, biggest_lose INTEGER DEFAULT 0,
                win_streak INTEGER DEFAULT 0, best_streak INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0, last_daily TEXT, created_at TEXT, referrer INTEGER DEFAULT 0
            )
        """)
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, game_type TEXT,
                bet INTEGER, result TEXT, win_amount INTEGER DEFAULT 0, lose_amount INTEGER DEFAULT 0,
                balance_before INTEGER, balance_after INTEGER, created_at TEXT
            )
        """)
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, amount INTEGER,
                reason TEXT, balance_before INTEGER, balance_after INTEGER, created_at TEXT
            )
        """)
        self.conn.commit()

    def get_user(self, user_id):
        self.cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = self.cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in self.cur.description]
        return dict(zip(cols, row))

    def create_user(self, user_id, username, first_name, referrer=0):
        now = datetime.now().isoformat()
        self.cur.execute("INSERT INTO users (user_id, username, first_name, balance, created_at, referrer) VALUES (?,?,?,?,?,?)",
                         (user_id, username, first_name, START_BALANCE, now, referrer))
        self.conn.commit()
        return self.get_user(user_id)

    def ensure_user(self, user_id, username, first_name):
        u = self.get_user(user_id)
        if not u:
            u = self.create_user(user_id, username, first_name)
        return u

    def change_balance(self, user_id, amount, reason="game"):
        user = self.get_user(user_id)
        before = user['balance']
        after = max(0, before + amount)
        self.cur.execute("UPDATE users SET balance=? WHERE user_id=?", (after, user_id))
        self.cur.execute("INSERT INTO transactions (user_id, type, amount, reason, balance_before, balance_after, created_at) VALUES (?,?,?,?,?,?,?)",
                         (user_id, "plus" if amount > 0 else "minus", amount, reason, before, after, datetime.now().isoformat()))
        self.conn.commit()
        if after >= VIP_THRESHOLD and not user['is_vip']:
            self.cur.execute("UPDATE users SET is_vip=1 WHERE user_id=?", (user_id,))
            self.conn.commit()
            return before, after, True
        return before, after, False

    def register_win(self, user_id, game_type, bet, win_amount):
        user = self.get_user(user_id)
        before = user['balance']
        after = before + win_amount
        self.cur.execute("UPDATE users SET balance=?, wins=wins+1, total_win=total_win+?, win_streak=win_streak+1, billiard_games=billiard_games+1 WHERE user_id=?", (after, win_amount, user_id))
        if game_type.startswith("billiard"):
            self.cur.execute("UPDATE users SET billiard_wins=billiard_wins+1 WHERE user_id=?", (user_id,))
        self.cur.execute("SELECT win_streak FROM users WHERE user_id=?", (user_id,))
        streak = self.cur.fetchone()[0]
        self.cur.execute("UPDATE users SET best_streak=MAX(best_streak,?), biggest_win=MAX(biggest_win,?) WHERE user_id=?", (streak, win_amount, user_id))
        self.cur.execute("INSERT INTO games (user_id, game_type, bet, result, win_amount, balance_before, balance_after, created_at) VALUES (?,?,?,'win',?,?,?,?)",
                         (user_id, game_type, bet, win_amount, before, after, datetime.now().isoformat()))
        self.cur.execute("INSERT INTO transactions (user_id, type, amount, reason, balance_before, balance_after, created_at) VALUES (?,'plus',?,?,?,?,?)",
                         (user_id, win_amount, f"win_{game_type}", before, after, datetime.now().isoformat()))
        self.cur.execute("UPDATE users SET xp=xp+100 WHERE user_id=?", (user_id,))
        self.cur.execute("UPDATE users SET level=xp/1000+1 WHERE user_id=?", (user_id,))
        self.conn.commit()
        return before, after

    def register_lose(self, user_id, game_type, bet):
        user = self.get_user(user_id)
        before = user['balance']
        after = before
        self.cur.execute("UPDATE users SET losses=losses+1, total_lose=total_lose+?, win_streak=0, billiard_games=billiard_games+1 WHERE user_id=?", (bet, user_id))
        if game_type.startswith("billiard"):
            self.cur.execute("UPDATE users SET billiard_losses=billiard_losses+1 WHERE user_id=?", (user_id,))
        self.cur.execute("UPDATE users SET biggest_lose=MAX(biggest_lose,?) WHERE user_id=?", (bet, user_id))
        self.cur.execute("INSERT INTO games (user_id, game_type, bet, result, lose_amount, balance_before, balance_after, created_at) VALUES (?,?,?,'lose',?,?,?,?)",
                         (user_id, game_type, bet, bet, before, after, datetime.now().isoformat()))
        self.cur.execute("UPDATE users SET xp=xp+20 WHERE user_id=?", (user_id,))
        self.conn.commit()
        return before, after

    def take_bet(self, user_id, bet, game_type):
        user = self.get_user(user_id)
        if user['balance'] < bet:
            return None, None, False
        before = user['balance']
        after = before - bet
        self.cur.execute("UPDATE users SET balance=?, total_bet=total_bet+? WHERE user_id=?", (after, bet, user_id))
        self.cur.execute("INSERT INTO transactions (user_id, type, amount, reason, balance_before, balance_after, created_at) VALUES (?,'minus',?,?,?,?,?)",
                         (user_id, -bet, f"bet_{game_type}", before, after, datetime.now().isoformat()))
        self.conn.commit()
        return before, after, True

    def get_top(self, limit=10):
        self.cur.execute("SELECT username, first_name, balance, wins, losses, level FROM users ORDER BY balance DESC LIMIT ?", (limit,))
        return self.cur.fetchall()

    def get_history(self, user_id, limit=10):
        self.cur.execute("SELECT game_type, bet, result, win_amount, lose_amount, created_at FROM games WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))
        return self.cur.fetchall()

    def can_daily(self, user_id):
        user = self.get_user(user_id)
        if not user['last_daily']:
            return True
        return datetime.now() - datetime.fromisoformat(user['last_daily']) > timedelta(hours=24)

    def claim_daily(self, user_id):
        self.cur.execute("UPDATE users SET last_daily=? WHERE user_id=?", (datetime.now().isoformat(), user_id))
        self.conn.commit()

db = Database()

# ================= BILLIARD ENGINE =================
BALLS = {1:"🟡 1",2:"🔵 2",3:"🔴 3",4:"🟣 4",5:"🟠 5",6:"🟢 6",7:"🟤 7",8:"⚫ 8",9:"🟡 9",10:"🔵 10",11:"🔴 11",12:"🟣 12",13:"🟠 13",14:"🟢 14",15:"🟤 15"}

class BilliardGame:
    def __init__(self, user_id, bet):
        self.user_id = user_id
        self.bet = bet
        self.balls_on_table = list(range(1,16))
        self.player_balls = []
        self.bot_balls = []
        self.player_type = ""
        self.current_turn = "player"
        self.moves = 0
        self.game_over = False

    def render(self):
        t = "🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩\n🟩  🎱 BLACK ACE  🟩\n🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩\n\n"
        if self.balls_on_table:
            t += "🎱 На столе:\n" + " ".join([BALLS[b] for b in self.balls_on_table[:8]]) + "\n"
            if len(self.balls_on_table) > 8:
                t += " ".join([BALLS[b] for b in self.balls_on_table[8:]]) + "\n"
            t += "\n"
        else:
            t += "🎱 Стол пуст!\n\n"
        t += f"👤 Твои: {', '.join([BALLS[b] for b in self.player_balls]) or '—'}\n"
        t += f"🤖 Бот: {', '.join([BALLS[b] for b in self.bot_balls]) or '—'}\n"
        t += f"💰 Ставка: {self.bet} 🪙 | Выигрыш будет: {self.bet*2} 🪙\n"
        t += f"🎯 Ход: {'ТЫ' if self.current_turn=='player' else 'БОТ'}\n"
        return t

    def shoot(self, power):
        self.moves += 1
        if not self.balls_on_table:
            return False, "Стол пуст"
        if 40 <= power <= 70:
            chance = 0.75
        elif 20 <= power < 40 or 70 < power <= 85:
            chance = 0.50
        else:
            chance = 0.25
        if random.random() < chance:
            ball = random.choice(self.balls_on_table)
            self.balls_on_table.remove(ball)
            if self.current_turn == "player":
                if not self.player_type:
                    self.player_type = "solid" if ball <= 7 else "striped" if ball > 8 else "black"
                self.player_balls.append(ball)
            else:
                self.bot_balls.append(ball)
            if ball == 8:
                self.game_over = True
                return True, "⚫ ЧЕРНЫЙ ШАР 8 ЗАБИТ!"
            return True, f"✅ Забит шар {BALLS[ball]}!"
        return False, "❌ Промах!"

    def check_winner(self):
        if 8 in self.player_balls:
            return "player"
        if 8 in self.bot_balls:
            return "bot"
        if not self.balls_on_table:
            return "player" if len(self.player_balls) > len(self.bot_balls) else "bot"
        return None

active_games: Dict[int, BilliardGame] = {}

# ================= KEYBOARDS =================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎱 ИГРАТЬ — MINI APP", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="🎱 БИЛЬЯРД В БОТЕ", callback_data="game_billiard"), InlineKeyboardButton(text="🎰 СЛОТЫ", callback_data="game_slots")],
        [InlineKeyboardButton(text="🎡 РУЛЕТКА", callback_data="game_roulette"), InlineKeyboardButton(text="💰 БАЛАНС", callback_data="balance")],
        [InlineKeyboardButton(text="🎁 БОНУС +500", callback_data="daily"), InlineKeyboardButton(text="🏆 ТОП", callback_data="top")],
        [InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile"), InlineKeyboardButton(text="📜 ИСТОРИЯ", callback_data="history")],
        [InlineKeyboardButton(text="❓ ПОМОЩЬ", callback_data="help")],
    ])

def billiard_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 СЛАБЫЙ 30", callback_data="shoot_30"), InlineKeyboardButton(text="🎯 СРЕДНИЙ 55", callback_data="shoot_55")],
        [InlineKeyboardButton(text="🔥 СИЛЬНЫЙ 80", callback_data="shoot_80"), InlineKeyboardButton(text="💥 МАКС 95", callback_data="shoot_95")],
        [InlineKeyboardButton(text="🏳️ СДАТЬСЯ", callback_data="giveup"), InlineKeyboardButton(text="🏠 МЕНЮ", callback_data="menu")],
    ])

def bet_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="50 🪙", callback_data="bet_50"), InlineKeyboardButton(text="100 🪙", callback_data="bet_100"), InlineKeyboardButton(text="250 🪙", callback_data="bet_250")],
        [InlineKeyboardButton(text="500 🪙", callback_data="bet_500"), InlineKeyboardButton(text="1000 🪙", callback_data="bet_1000"), InlineKeyboardButton(text="5000 🪙", callback_data="bet_5000")],
        [InlineKeyboardButton(text="⬅️ НАЗАД", callback_data="menu")],
    ])

WELCOME = """
♠️ <b>BLACK ACE CASINO — SINCE 1976 • MACAU</b>

🎱 Бильярд | 🎰 Слоты | 🎡 Рулетка

<b>Как работают деньги:</b>
✅ <b>ВЫИГРАЛ</b> → монеты <b>ПРИХОДЯТ</b> (+ставка x2)
❌ <b>ПРОИГРАЛ</b> → монеты <b>УХОДЯТ</b> (-ставка)
🎁 Бонус каждый день +500 🪙

👇 Выбери игру:
"""

# ================= HANDLERS =================
@dp.message(CommandStart())
async def start_handler(message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "", message.from_user.first_name)
    if len(message.text.split()) > 1:
        try:
            ref = int(message.text.split()[1])
            if ref != message.from_user.id:
                db.change_balance(ref, 200, "referral")
                try:
                    await bot.send_message(ref, "🎉 По твоей ссылке пришел игрок! +200 🪙 ПРИШЛО")
                except:
                    pass
        except:
            pass
    await message.answer(WELCOME, reply_markup=main_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "menu")
async def menu_cb(call: CallbackQuery):
    await call.message.edit_text(WELCOME, reply_markup=main_kb(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "help")
async def help_cb(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ МЕНЮ", callback_data="menu")]])
    await call.message.edit_text("<b>❓ КАК ИГРАТЬ</b>\n\n🎱 <b>Бильярд:</b> Ставка → Бей → Забей 8 = ПОБЕДА\n✅ Победа: +ставка x2 ПРИШЛО\n❌ Поражение: -ставка УШЛО\n\n🎰 <b>Слоты:</b> 3 одинаковых = x5, 3 💎 = x10\n🎡 <b>Рулетка:</b> Цвет = x2, зеро = x14\n\n💰 Старт 1000 🪙 | 🎁 Бонус 500 🪙", reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "balance")
async def balance_cb(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    text = f"💰 <b>ТВОЙ БАЛАНС</b>\n\n🪙 Баланс: <b>{u['balance']} 🪙</b>\n⭐ Уровень: {u['level']} | XP: {u['xp']}\n🏆 Побед: {u['wins']} | Поражений: {u['losses']}\n🔥 Серия: {u['win_streak']} | Лучшая: {u['best_streak']}\n🎱 Бильярд: {u['billiard_wins']} / {u['billiard_losses']}\n💸 Ставок: {u['total_bet']} 🪙\n✅ Выиграно: {u['total_win']} 🪙\n❌ Проиграно: {u['total_lose']} 🪙\n👑 VIP: {'ДА ✅' if u['is_vip'] else 'НЕТ ❌'}\n\nРефералка: <code>https://t.me/BlackAceBot?start={call.from_user.id}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📜 ИСТОРИЯ", callback_data="history")],[InlineKeyboardButton(text="⬅️ МЕНЮ", callback_data="menu")]])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "history")
async def history_cb(call: CallbackQuery):
    hist = db.get_history(call.from_user.id, 10)
    if not hist:
        text = "📜 История пуста. Сыграй первую игру!"
    else:
        text = "📜 <b>ПОСЛЕДНИЕ 10 ИГР</b>\n\n"
        for g, b, r, w, l, _ in hist:
            if r == "win":
                text += f"✅ {g} | {b} | <b>+{w} 🪙 ПРИШЛО</b>\n"
            else:
                text += f"❌ {g} | {b} | <b>-{l} 🪙 УШЛО</b>\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ МЕНЮ", callback_data="menu")]])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "daily")
async def daily_cb(call: CallbackQuery):
    if db.can_daily(call.from_user.id):
        db.claim_daily(call.from_user.id)
        before, after, _ = db.change_balance(call.from_user.id, DAILY_BONUS, "daily")
        await call.answer(f"🎁 +{DAILY_BONUS} 🪙 ПРИШЛО! Баланс: {before} → {after}", show_alert=True)
    else:
        await call.answer("⏳ Бонус уже взят! Приходи завтра.", show_alert=True)
    await menu_cb(call)

@dp.callback_query(F.data == "top")
async def top_cb(call: CallbackQuery):
    top = db.get_top(10)
    medals = ["🥇","🥈","🥉","4.","5.","6.","7.","8.","9.","10."]
    text = "🏆 <b>ТОП-10</b>\n\n"
    for i, (u, f, b, w, l, lv) in enumerate(top):
        text += f"{medals[i]} @{u or f} — {b} 🪙 | ✅{w} ❌{l}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ МЕНЮ", callback_data="menu")]])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "profile")
async def profile_cb(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    wr = u['wins']/(u['wins']+u['losses'])*100 if u['wins']+u['losses']>0 else 0
    text = f"👤 <b>ПРОФИЛЬ</b>\n🆔 {u['user_id']} | {u['first_name']}\n💰 Баланс: {u['balance']} 🪙\n⭐ Уровень {u['level']} | XP {u['xp']}\n🏆 Винрейт: {wr:.1f}%\n🔥 Серия: {u['win_streak']} | Лучшая: {u['best_streak']}\n💰 Макс выигрыш: {u['biggest_win']} 🪙\n💸 Макс проигрыш: {u['biggest_lose']} 🪙"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ МЕНЮ", callback_data="menu")]])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "game_billiard")
async def billiard_start(call: CallbackQuery):
    await call.message.edit_text("🎱 <b>БИЛЬЯРД</b>\n\nВыбери ставку:\n\n✅ Выиграл → <b>+ставка x2 ПРИШЛО</b>\n❌ Проиграл → <b>-ставка УШЛО</b>", reply_markup=bet_kb(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("bet_"))
async def bet_cb(call: CallbackQuery):
    bet = int(call.data.split("_")[1])
    user = db.get_user(call.from_user.id)
    if user['balance'] < bet:
        await call.answer(f"❌ Не хватает! Баланс: {user['balance']} 🪙", show_alert=True)
        return
    before, after, ok = db.take_bet(call.from_user.id, bet, "billiard")
    if not ok:
        return
    game = BilliardGame(call.from_user.id, bet)
    active_games[call.from_user.id] = game
    text = f"🎱 <b>ИГРА НАЧАЛАСЬ!</b>\n💸 Ставка -{bet} 🪙 УШЛО\n💰 Баланс: {before} → {after} 🪙\n\n" + game.render() + "\n🎯 <b>ВАШ ХОД, ВАШ КИЙ</b>"
    await call.message.edit_text(text, reply_markup=billiard_kb(), parse_mode="HTML")
    await call.answer(f"💸 -{bet} 🪙 ставка ушла")

@dp.callback_query(F.data.startswith("shoot_"))
async def shoot_cb(call: CallbackQuery):
    uid = call.from_user.id
    if uid not in active_games:
        await call.answer("❌ Игра не найдена", show_alert=True)
        return
    game = active_games[uid]
    power = int(call.data.split("_")[1])
    success, msg = game.shoot(power)
    text = f"{msg}\n\n" + game.render()
    winner = game.check_winner()
    if winner:
        await finish_billiard(call, game, winner, text)
        return
    game.current_turn = "bot"
    await call.message.edit_text(text + "\n\n🤖 Ход бота...", reply_markup=billiard_kb(), parse_mode="HTML")
    await asyncio.sleep(1.2)
    bot_success, bot_msg = game.shoot(random.randint(30, 80))
    game    game.current_turn = "player"
    winner2 = game.check_winner()
    text2 = f"🤖 Бот: {bot_msg}\n\n" + game.render()
    if winner2:
        await finish_billiard(call, game, winner2, text2)
        return
    text2 += "\n🎯 <b>ВАШ ХОД, ВАШ КИЙ</b>"
    await call.message.edit_text(text2, reply_markup=billiard_kb(), parse_mode="HTML")
    await call.answer(msg)

async def finish_billiard(call: CallbackQuery, game: BilliardGame, winner: str, base_text: str):
    uid = call.from_user.id
    game.game_over = True
    if winner == "player":
        win_amount = game.bet * 2
        before, after = db.register_win(uid, "billiard", game.bet, win_amount)
        text = base_text + f"\n\n🎉 <b>ТЫ ВЫИГРАЛ!</b>\n\n💰 Ставка: {game.bet} 🪙\n✅ <b>+{win_amount} 🪙 ПРИШЛО!</b>\n💰 Баланс: {before} → {after} 🪙\n🔥 Чистый профит: +{win_amount - game.bet} 🪙"
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎱 ЕЩЕ РАЗ", callback_data="game_billiard")],[InlineKeyboardButton(text="🏠 МЕНЮ", callback_data="menu")]]), parse_mode="HTML")
        await call.answer(f"🎉 +{win_amount} 🪙 ПРИШЛО!", show_alert=True)
    else:
        before, after = db.register_lose(uid, "billiard", game.bet)
        user = db.get_user(uid)
        text = base_text + f"\n\n😢 <b>ТЫ ПРОИГРАЛ</b>\n\n💸 Ставка: {game.bet} 🪙\n❌ <b>-{game.bet} 🪙 УШЛО</b>\n💰 Баланс: {user['balance']} 🪙"
        await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎱 РЕВАНШ", callback_data="game_billiard")],[InlineKeyboardButton(text="🏠 МЕНЮ", callback_data="menu")]]), parse_mode="HTML")
        await call.answer(f"😢 -{game.bet} 🪙 УШЛО", show_alert=True)
    if uid in active_games:
        del active_games[uid]

@dp.callback_query(F.data == "giveup")
async def giveup_cb(call: CallbackQuery):
    uid = call.from_user.id
    if uid in active_games:
        game = active_games[uid]
        db.register_lose(uid, "billiard", game.bet)
        del active_games[uid]
        await call.message.edit_text(f"🏳️ Ты сдался.\n❌ -{game.bet} 🪙 УШЛО", reply_markup=main_kb())
    else:
        await call.message.edit_text("🏳️ Игра завершена", reply_markup=main_kb())
    await call.answer()

@dp.callback_query(F.data == "game_slots")
async def slots_menu(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎰 КРУТИТЬ 100 🪙", callback_data="spin_100")],[InlineKeyboardButton(text="🎰 КРУТИТЬ 500 🪙", callback_data="spin_500")],[InlineKeyboardButton(text="⬅️ МЕНЮ", callback_data="menu")]])
    await call.message.edit_text("🎰 <b>СЛОТЫ</b>\n\n✅ 3 одинаковых = +x5 ПРИШЛО\n❌ Не совпало = -ставка УШЛО", reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("spin_"))
async def spin_cb(call: CallbackQuery):
    bet = int(call.data.split("_")[1])
    uid = call.from_user.id
    user = db.get_user(uid)
    if user['balance'] < bet:
        await call.answer("❌ Не хватает!", show_alert=True)
        return
    db.take_bet(uid, bet, "slots")
    symbols = ["🍒","🍋","⭐","💎","♠️","👑","🎰"]
    result = [random.choice(symbols) for _ in range(3)]
    res_str = " | ".join(result)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎰 ЕЩЕ РАЗ", callback_data="game_slots")],[InlineKeyboardButton(text="⬅️ МЕНЮ", callback_data="menu")]])
    if result[0] == result[1] == result[2]:
        mult = 10 if result[0] == "💎" else 7 if result[0] == "👑" else 5
        win = bet * mult
        before, after = db.register_win(uid, "slots", bet, win)
        await call.message.edit_text(f"🎰 <b>{res_str}</b>\n\n🎉 <b>ДЖЕКПОТ x{mult}!</b>\n✅ <b>+{win} 🪙 ПРИШЛО!</b>\n💰 Баланс: {before} → {after} 🪙", reply_markup=kb, parse_mode="HTML")
        await call.answer(f"🎉 +{win} 🪙!", show_alert=True)
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        win = bet * 2
        before, after = db.register_win(uid, "slots", bet, win)
        await call.message.edit_text(f"🎰 <b>{res_str}</b>\n\n😍 Два совпали!\n✅ <b>+{win} 🪙 ПРИШЛО</b>\n💰 Баланс: {before} → {after} 🪙", reply_markup=kb, parse_mode="HTML")
        await call.answer(f"+{win} 🪙 ПРИШЛО")
    else:
        db.register_lose(uid, "slots", bet)
        user2 = db.get_user(uid)
        await call.message.edit_text(f"🎰 <b>{res_str}</b>\n\n😢 Не повезло\n❌ <b>-{bet} 🪙 УШЛО</b>\n💰 Баланс: {user2['balance']} 🪙", reply_markup=kb, parse_mode="HTML")
        await call.answer(f"-{bet} 🪙 УШЛО", show_alert=True)

@dp.callback_query(F.data == "game_roulette")
async def roulette_menu(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔴 КРАСНОЕ x2", callback_data="roulette_red"), InlineKeyboardButton(text="⚫ ЧЕРНОЕ x2", callback_data="roulette_black")],[InlineKeyboardButton(text="🟢 ЗЕЛЕНОЕ 0 x14", callback_data="roulette_green")],[InlineKeyboardButton(text="⬅️ МЕНЮ", callback_data="menu")]])
    await call.message.edit_text("🎡 <b>РУЛЕТКА</b>\nСтавка 100 🪙\n✅ Угадал → +ПРИШЛО\n❌ Не угадал → -УШЛО", reply_markup=kb, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("roulette_"))
async def roulette_play(call: CallbackQuery):
    choice = call.data.split("_")[1]
    uid = call.from_user.id
    user = db.get_user(uid)
    if user['balance'] < 100:
        await call.answer("❌ Не хватает!", show_alert=True)
        return
    db.take_bet(uid, 100, "roulette")
    roll = random.randint(0, 36)
    color = "green" if roll == 0 else "black" if roll % 2 == 0 else "red"
    emoji = "🟢" if color == "green" else "⚫" if color == "black" else "🔴"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ МЕНЮ", callback_data="menu")]])
    if choice == color:
        mult = 14 if color == "green" else 2
        win = 100 * mult
        before, after = db.register_win(uid, "roulette", 100, win)
        await call.message.edit_text(f"🎡 Выпало: {emoji} {roll}\n\n🎉 <b>УГАДАЛ!</b>\n✅ +{win} 🪙 ПРИШЛО\n💰 Баланс: {before} → {after} 🪙", reply_markup=kb, parse_mode="HTML")
        await call.answer(f"+{win} 🪙 ПРИШЛО!", show_alert=True)
    else:
        db.register_lose(uid, "roulette", 100)
        user2 = db.get_user(uid)
        await call.message.edit_text(f"🎡 Выпало: {emoji} {roll}\n\n😢 Не угадал\n❌ -100 🪙 УШЛО\n💰 Баланс: {user2['balance']} 🪙", reply_markup=kb, parse_mode="HTML")
        await call.answer("-100 🪙 УШЛО", show_alert=True)

@dp.message(F.web_app_data)
async def on_webapp(m: Message):
    try:
        data = json.loads(m.web_app_data.data)
    except:
        await m.answer("Ошибка данных Mini App")
        return
    uid = m.from_user.id
    db.ensure_user(uid, m.from_user.username or "", m.from_user.first_name)
    if data.get("type") == "game_end":
        win = data.get("win", False)
        bet = data.get("bet", 100)
        win_amount = data.get("winAmount", 0)
        if win:
            before, after = db.register_win(uid, "billiard_miniapp", bet, win_amount)
            await m.answer(f"🎉 <b>ТЫ ВЫИГРАЛ В MINI APP!</b>\n\n💸 Ставка: {bet} 🪙\n✅ <b>+{win_amount} 🪙 ПРИШЛО!</b>\n💰 Баланс: {before} → {after} 🪙", parse_mode="HTML", reply_markup=main_kb())
        else:
            before, after = db.register_lose(uid, "billiard_miniapp", bet)
            mini_balance = data.get("balance", db.get_user(uid)['balance'])
            db.cur.execute("UPDATE users SET balance=? WHERE user_id=?", (mini_balance, uid))
            db.conn.commit()
            await m.answer(f"😢 <b>ТЫ ПРОИГРАЛ В MINI APP</b>\n\n💸 Ставка: {bet} 🪙\n❌ <b>-{bet} 🪙 УШЛО</b>\n💰 Баланс: {mini_balance} 🪙", parse_mode="HTML", reply_markup=main_kb())

@dp.message(Command("add"))
async def add_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, uid, amount = message.text.split()
        before, after, _ = db.change_balance(int(uid), int(amount), "admin_add")
        await message.answer(f"✅ Выдано {amount} 🪙\nБаланс {uid}: {before} → {after}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nФормат: /add user_id amount")

@dp.message(Command("remove"))
async def remove_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, uid, amount = message.text.split()
        before, after, _ = db.change_balance(int(uid), -int(amount), "admin_remove")
        await message.answer(f"❌ Забрано {amount} 🪙\nБаланс {uid}: {before} → {after}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}\nФормат: /remove user_id amount")

@dp.message(Command("stats"))
async def stats_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    db.cur.execute("SELECT COUNT(*), SUM(balance), SUM(total_win), SUM(total_lose) FROM users")
    total_users, total_bal, total_win, total_lose = db.cur.fetchone()
    await message.answer(f"📊 Статистика:\n👥 Пользователей: {total_users}\n💰 Всего монет: {total_bal}\n✅ Всего выиграно: {total_win}\n❌ Всего проиграно: {total_lose}")

async def main():
    print(f"♠️ {CASINO_NAME} запущен...")
    print(f"🌐 Mini App: {WEBAPP_URL}")
    print("✅ Выигрыш = +ПРИШЛО | Проигрыш = -УШЛО")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
