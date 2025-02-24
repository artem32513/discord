import discord
from discord.ext import commands, tasks
import asyncio
import json
import os
import random
import sqlite3
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from typing import Optional

# Настройка логирования
handler = RotatingFileHandler("bot.log", maxBytes=5*1024*1024, backupCount=3)
logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger()

# Загрузка конфигурации
try:
    with open("config.json", "r") as file:
        config = json.load(file)
        TOKEN = config.get("TOKEN")
        if not TOKEN:
            raise ValueError("Токен бота не указан в config.json!")
        PREFIX = config.get("PREFIX", "!")
        ROLES_CONFIG = config.get("roles", {})
        WELCOME_CHANNEL = config.get("welcome_channel", "🔔new-person🔔")
        ROLES_CHANNEL = config.get("roles_channel", "🎭getting-roles🎭")
        ADMIN_CHANNEL = config.get("admin_channel", "🔧developer🔧")
except FileNotFoundError:
    logger.error("Файл config.json не найден!")
    exit(1)
except ValueError as e:
    logger.error(str(e))
    exit(1)

# Подключение к базе данных
conn = sqlite3.connect('bot_data.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        xp INTEGER DEFAULT 0,
        gold INTEGER DEFAULT 0,
        crystals INTEGER DEFAULT 0,
        last_daily TIMESTAMP,
        daily_streak INTEGER DEFAULT 0,
        last_mine TIMESTAMP,
        last_work TIMESTAMP,
        last_profit TIMESTAMP,
        inventory TEXT DEFAULT '[]',
        muted_until TIMESTAMP DEFAULT NULL
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS gear (
        user_id INTEGER PRIMARY KEY,
        pickaxe_level INTEGER DEFAULT 0,
        helmet_level INTEGER DEFAULT 0,
        gloves_level INTEGER DEFAULT 0,
        boots_level INTEGER DEFAULT 0
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS cases (
        case_id TEXT PRIMARY KEY,
        cost INTEGER,
        rewards TEXT
    )
''')
conn.commit()

# Функции базы данных
def get_user_data(user_id):
    cursor.execute('SELECT xp, gold, last_daily, inventory, crystals, daily_streak, last_mine, last_work, last_profit, muted_until FROM users WHERE user_id = ?', (user_id,))
    return cursor.fetchone() or (0, 0, None, '[]', 0, 0, None, None, None, None)

def update_user_data(user_id, xp=None, gold=None, last_daily=None, inventory=None, crystals=None, daily_streak=None, last_mine=None, last_work=None, last_profit=None, muted_until=None):
    with conn:
        cursor.execute('INSERT OR IGNORE INTO users (user_id, xp, gold, inventory, crystals) VALUES (?, 0, 0, ?, 0)', (user_id, '[]'))
        if xp is not None:
            cursor.execute('UPDATE users SET xp = xp + ? WHERE user_id = ?', (xp, user_id))
        if gold is not None:
            cursor.execute('UPDATE users SET gold = gold + ? WHERE user_id = ?', (gold, user_id))
        if last_daily is not None:
            cursor.execute('UPDATE users SET last_daily = ? WHERE user_id = ?', (last_daily, user_id))
        if inventory is not None:
            cursor.execute('UPDATE users SET inventory = ? WHERE user_id = ?', (json.dumps(inventory), user_id))
        if crystals is not None:
            cursor.execute('UPDATE users SET crystals = crystals + ? WHERE user_id = ?', (crystals, user_id))
        if daily_streak is not None:
            cursor.execute('UPDATE users SET daily_streak = ? WHERE user_id = ?', (daily_streak, user_id))
        if last_mine is not None:
            cursor.execute('UPDATE users SET last_mine = ? WHERE user_id = ?', (last_mine, user_id))
        if last_work is not None:
            cursor.execute('UPDATE users SET last_work = ? WHERE user_id = ?', (last_work, user_id))
        if last_profit is not None:
            cursor.execute('UPDATE users SET last_profit = ? WHERE user_id = ?', (last_profit, user_id))
        if muted_until is not None:
            cursor.execute('UPDATE users SET muted_until = ? WHERE user_id = ?', (muted_until, user_id))

def get_gear(user_id):
    cursor.execute('SELECT pickaxe_level, helmet_level, gloves_level, boots_level FROM gear WHERE user_id = ?', (user_id,))
    return cursor.fetchone() or (0, 0, 0, 0)

def update_gear(user_id, pickaxe_level=None, helmet_level=None, gloves_level=None, boots_level=None):
    with conn:
        cursor.execute('INSERT OR IGNORE INTO gear (user_id) VALUES (?)', (user_id,))
        if pickaxe_level is not None:
            cursor.execute('UPDATE gear SET pickaxe_level = ? WHERE user_id = ?', (pickaxe_level, user_id))
        if helmet_level is not None:
            cursor.execute('UPDATE gear SET helmet_level = ? WHERE user_id = ?', (helmet_level, user_id))
        if gloves_level is not None:
            cursor.execute('UPDATE gear SET gloves_level = ? WHERE user_id = ?', (gloves_level, user_id))
        if boots_level is not None:
            cursor.execute('UPDATE gear SET boots_level = ? WHERE user_id = ?', (boots_level, user_id))

def init_cases():
    cursor.execute('DELETE FROM cases')  # Очистка старых кейсов
    cases = [
        ("common_case", 50, json.dumps([(10, 0.5), (20, 0.3), (30, 0.2)])),  # Золото, вероятность
        ("rare_case", 100, json.dumps([(50, 0.4), (100, 0.3), (150, 0.2), (200, 0.1)])),
        ("legendary_case", 200, json.dumps([(100, 0.3), (200, 0.2), (300, 0.3), (500, 0.2)]))
    ]
    cursor.executemany('INSERT OR IGNORE INTO cases (case_id, cost, rewards) VALUES (?, ?, ?)', cases)
    conn.commit()

init_cases()  # Инициализация кейсов при запуске

def get_case_rewards(case_id):
    cursor.execute('SELECT rewards FROM cases WHERE case_id = ?', (case_id,))
    rewards = cursor.fetchone()
    return json.loads(rewards[0]) if rewards else []

# Экономика
def get_gear_cost(level):
    return int(50 * (1.5 ** level))

def check_cooldown(last_time, cooldown_seconds, action_name):
    now = datetime.utcnow()
    if last_time and (now - datetime.fromisoformat(last_time)).total_seconds() < cooldown_seconds:
        remaining = int(cooldown_seconds - (now - datetime.fromisoformat(last_time)).total_seconds())
        hours = remaining // 3600
        minutes = remaining % 3600 // 60
        seconds = remaining % 60
        return False, f"Подождите {hours} ч {minutes} мин {seconds} сек перед следующей {action_name}!"
    return True, None

# Настройка бота
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# Глобальные переменные
last_message_time = {}
voice_activity = {}
daily_quests = {}  # Хранение ежедневных заданий для пользователей

# Цвета и эмодзи
COLORS = {
    "default": discord.Color.blue(),
    "success": discord.Color.green(),
    "error": discord.Color.red(),
    "gold": discord.Color.gold(),
    "purple": discord.Color.purple(),
    "orange": discord.Color.orange(),
    "rainbow": discord.Color.from_rgb(255, 105, 180)  # Розовый для стиля
}
EMOJIS = {
    "gold": "🪙", "crystals": "💎", "mine": "⛏", "work": "👷", "profit": "💸",
    "daily": "🎁", "profile": "👤", "gear": "⚒", "rps": "🆚", "blackjack": "🃏",
    "transfer": "💸", "give": "🎁", "buyrole": "🏷", "cooldowns": "⏳", "mute": "🔇",
    "ban": "🚫", "clear": "🧹", "leaderboards": "🏆", "cases": "🎰", "help": "❓"
}

# Представления (кнопки и меню)
class ProfileView(discord.ui.View):
    @discord.ui.button(label="Профиль", style=discord.ButtonStyle.green, emoji=EMOJIS["profile"])
    async def profile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_profile(interaction.user, interaction)

class GearView(discord.ui.View):
    async def upgrade(self, interaction, gear_name):
        gear_map = {"pickaxe": "pickaxe_level", "helmet": "helmet_level", "gloves": "gloves_level", "boots": "boots_level"}
        _, _, _, _, crystals, _, _, _, _ = get_user_data(interaction.user.id)
        current_level = dict(zip(gear_map.values(), get_gear(interaction.user.id)))[gear_map[gear_name]]
        cost = get_gear_cost(current_level)
        if crystals < cost:
            await interaction.response.send_message(embed=discord.Embed(title="❌ Недостаточно", description=f"Нужно {cost} {EMOJIS['crystals']}!", color=COLORS["error"]), ephemeral=True)
            return
        update_user_data(interaction.user.id, crystals=-cost)
        update_gear(interaction.user.id, **{gear_map[gear_name]: current_level + 1})
        await interaction.response.send_message(embed=discord.Embed(title="✅ Улучшено", description=f"{gear_name.capitalize()} теперь уровня {current_level + 1}!", color=COLORS["success"]), ephemeral=True)

    @discord.ui.button(label="Кирка", style=discord.ButtonStyle.blurple, emoji=EMOJIS["mine"])
    async def pickaxe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.upgrade(interaction, "pickaxe")

    @discord.ui.button(label="Шлем", style=discord.ButtonStyle.blurple, emoji="⛑")
    async def helmet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.upgrade(interaction, "helmet")

    @discord.ui.button(label="Перчатки", style=discord.ButtonStyle.blurple, emoji="🧤")
    async def gloves(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.upgrade(interaction, "gloves")

    @discord.ui.button(label="Ботинки", style=discord.ButtonStyle.blurple, emoji="👢")
    async def boots(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.upgrade(interaction, "boots")

class ActionView(discord.ui.View):
    @discord.ui.button(label="Добыть", style=discord.ButtonStyle.green, emoji=EMOJIS["mine"])
    async def mine(self, interaction: discord.Interaction, button: discord.ui.Button):
        await mine(interaction.user, interaction)

    @discord.ui.button(label="Работать", style=discord.ButtonStyle.green, emoji=EMOJIS["work"])
    async def work(self, interaction: discord.Interaction, button: discord.ui.Button):
        await work(interaction.user, interaction)

    @discord.ui.button(label="Прибыль", style=discord.ButtonStyle.green, emoji=EMOJIS["profit"])
    async def profit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await profit(interaction.user, interaction)

    @discord.ui.button(label="Продать", style=discord.ButtonStyle.red, emoji="💰")
    async def sell(self, interaction: discord.Interaction, button: discord.ui.Button):
        await sell_crystals(interaction.user, interaction, 100)

    @discord.ui.button(label="Ежедневка", style=discord.ButtonStyle.grey, emoji=EMOJIS["daily"])
    async def daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        await daily(interaction.user, interaction)

class ModerationView(discord.ui.View):
    @discord.ui.button(label="Замутить", style=discord.ButtonStyle.red, emoji=EMOJIS["mute"])
    async def mute(self, interaction: discord.Interaction, button: discord.ui.Button):
        await mute_member(interaction.user, interaction)

    @discord.ui.button(label="Размутить", style=discord.ButtonStyle.green, emoji="🔊")
    async def unmute(self, interaction: discord.Interaction, button: discord.ui.Button):
        await unmute_member(interaction.user, interaction)

    @discord.ui.button(label="Забанить", style=discord.ButtonStyle.red, emoji=EMOJIS["ban"])
    async def ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await ban_member(interaction.user, interaction)

    @discord.ui.button(label="Разбанить", style=discord.ButtonStyle.green, emoji="✅")
    async def unban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await unban_member(interaction.user, interaction)

    @discord.ui.button(label="Очистить", style=discord.ButtonStyle.red, emoji=EMOJIS["clear"])
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        await clear_chat(interaction.user, interaction)

class CurrencyView(discord.ui.View):
    @discord.ui.select(
        placeholder="Выберите валюту",
        options=[
            discord.SelectOption(label="Золото", emoji=EMOJIS["gold"], value="gold"),
            discord.SelectOption(label="Кристаллы", emoji=EMOJIS["crystals"], value="crystals")
        ]
    )
    async def currency_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await give_currency(interaction.user, interaction, select.values[0])

class CaseView(discord.ui.View):
    @discord.ui.select(
        placeholder="Выберите кейс",
        options=[
            discord.SelectOption(label="Обычный", emoji="🎰", value="common_case", description="50 🪙"),
            discord.SelectOption(label="Редкий", emoji="🌟", value="rare_case", description="100 🪙"),
            discord.SelectOption(label="Легендарный", emoji="🔥", value="legendary_case", description="200 🪙")
        ]
    )
    async def case_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await open_case(interaction.user, interaction, select.values[0])

# Функции бота
async def show_profile(user, ctx_or_interaction):
    xp, gold, _, _, crystals, daily_streak, _, _, _, muted_until = get_user_data(user.id)
    level = xp // 100
    mute_status = "🔇 (Замучен до " + muted_until.isoformat() + ")" if muted_until and datetime.utcnow() < datetime.fromisoformat(muted_until) else "🔊 (Не замучен)"
    embed = discord.Embed(
        title=f"{EMOJIS['profile']} Профиль {user.name}",
        description=f"Информация о {user.mention}",
        color=COLORS["default"]
    )
    embed.add_field(name="Уровень", value=f"{level} (XP: {xp})", inline=True)
    embed.add_field(name="Золото", value=f"{gold} {EMOJIS['gold']}", inline=True)
    embed.add_field(name="Кристаллы", value=f"{crystals} {EMOJIS['crystals']}", inline=True)
    embed.add_field(name="Стрик", value=f"{daily_streak} дней", inline=True)
    embed.add_field(name="Статус мута", value=mute_status, inline=True)
    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
    embed.set_image(url="https://i.imgur.com/8pZqL7G.gif")  # Анимированное аниме-изображение
    if isinstance(ctx_or_interaction, discord.Interaction):
        await ctx_or_interaction.response.send_message(embed=embed, view=ProfileView(), ephemeral=True)
    else:
        await ctx_or_interaction.send(embed=embed, view=ProfileView())

async def mine(user, interaction):
    _, _, _, _, _, _, last_mine, _, _, _ = get_user_data(user.id)
    can_mine, error = check_cooldown(last_mine, 300, "добычи")
    if not can_mine:
        await interaction.response.send_message(embed=discord.Embed(title=f"{EMOJIS['cooldowns']} Кулдаун", description=error, color=COLORS["error"]), ephemeral=True)
        return
    pickaxe_level, _, _, _ = get_gear(user.id)
    crystals_gain = int(random.randint(5, 15) * (1 + pickaxe_level * 0.05))
    update_user_data(user.id, crystals=crystals_gain, last_mine=datetime.utcnow().isoformat())
    await interaction.response.send_message(embed=discord.Embed(title=f"{EMOJIS['mine']} Добыча", description=f"Вы добыли {crystals_gain} {EMOJIS['crystals']}!", color=COLORS["success"]), ephemeral=True)

async def work(user, interaction):
    _, _, _, _, _, _, _, last_work, _, _ = get_user_data(user.id)
    can_work, error = check_cooldown(last_work, 3600, "работы")
    if not can_work:
        await interaction.response.send_message(embed=discord.Embed(title=f"{EMOJIS['cooldowns']} Кулдаун", description=error, color=COLORS["error"]), ephemeral=True)
        return
    gold_gain = random.randint(5, 10)
    update_user_data(user.id, gold=gold_gain, last_work=datetime.utcnow().isoformat())
    await interaction.response.send_message(embed=discord.Embed(title=f"{EMOJIS['work']} Работа", description=f"Вы заработали {gold_gain} {EMOJIS['gold']}!", color=COLORS["success"]), ephemeral=True)

async def profit(user, interaction):
    _, _, _, _, _, _, _, _, last_profit, _ = get_user_data(user.id)
    can_profit, error = check_cooldown(last_profit, 14400, "прибыли")
    if not can_profit:
        await interaction.response.send_message(embed=discord.Embed(title=f"{EMOJIS['cooldowns']} Кулдаун", description=error, color=COLORS["error"]), ephemeral=True)
        return
    profit = random.randint(50, 100) if random.random() < 0.2 else 0
    update_user_data(user.id, gold=profit, last_profit=datetime.utcnow().isoformat())
    if profit:
        await interaction.response.send_message(embed=discord.Embed(title=f"{EMOJIS['profit']} Прибыль", description=f"Вы получили {profit} {EMOJIS['gold']}!", color=COLORS["success"]), ephemeral=True)
    else:
        await interaction.response.send_message(embed=discord.Embed(title="😔 Неудача", description="Удача не на вашей стороне!", color=COLORS["error"]), ephemeral=True)

async def sell_crystals(user, interaction, amount):
    _, _, _, _, crystals, _, _, _, _, _ = get_user_data(user.id)
    if amount <= 0 or amount > crystals:
        await interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description=f"У вас {crystals} {EMOJIS['crystals']}!", color=COLORS["error"]), ephemeral=True)
        return
    gold_gain = amount // 2
    update_user_data(user.id, crystals=-amount, gold=gold_gain)
    await interaction.response.send_message(embed=discord.Embed(title="💰 Продажа", description=f"Вы продали {amount} {EMOJIS['crystals']} за {gold_gain} {EMOJIS['gold']}!", color=COLORS["gold"]), ephemeral=True)

async def daily(user, interaction):
    _, _, last_daily, _, _, daily_streak, _, _, _, _ = get_user_data(user.id)
    can_daily, error = check_cooldown(last_daily, 86400, "ежедневки")
    if not can_daily:
        await interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description=error, color=COLORS["error"]), ephemeral=True)
        return
    multiplier = 1 + (daily_streak * 0.1)
    gold_reward = int(random.randint(10, 20) * multiplier)
    crystals_reward = int(random.randint(5, 10) * multiplier)
    new_streak = daily_streak + 1 if last_daily and (datetime.utcnow() - datetime.fromisoformat(last_daily)).days == 1 else 1
    update_user_data(user.id, gold=gold_reward, crystals=crystals_reward, last_daily=datetime.utcnow().isoformat(), daily_streak=new_streak)
    # Проверка заданий
    if user.id in daily_quests:
        quest = daily_quests[user.id]
        if quest["type"] == "messages" and quest["progress"] >= quest["target"]:
            extra_gold = 20
            update_user_data(user.id, gold=extra_gold)
            await interaction.followup.send(embed=discord.Embed(title="🎉 Завершено задание!", description=f"Вы выполнили задание и получили {extra_gold} {EMOJIS['gold']}!", color=COLORS["gold"]), ephemeral=True)
            del daily_quests[user.id]
    await interaction.response.send_message(embed=discord.Embed(title=f"{EMOJIS['daily']} Ежедневка", description=f"+{gold_reward} {EMOJIS['gold']}, +{crystals_reward} {EMOJIS['crystals']}!\nСтрик: {new_streak}", color=COLORS["gold"]), ephemeral=True)

async def mute_member(user, interaction):
    await interaction.response.send_modal(
        title="🔇 Замутить пользователя",
        custom_id="mute_modal",
        components=[
            discord.ui.TextInput(
                label="Укажите пользователя (ID или упоминание)",
                style=discord.TextInputStyle.short,
                custom_id="target_id",
                placeholder="123456789012345678 или @username",
                required=True
            ),
            discord.ui.TextInput(
                label="Время мута (в минутах, 0 для бесконечного)",
                style=discord.TextInputStyle.short,
                custom_id="duration",
                placeholder="30",
                required=True
            )
        ]
    )
    try:
        modal_interaction = await bot.wait_for("modal_submit", check=lambda i: i.custom_id == "mute_modal" and i.user == user, timeout=300)
        target_id = modal_interaction.components[0].value
        duration = int(modal_interaction.components[1].value)
        try:
            target = await bot.fetch_user(int(target_id)) if target_id.isdigit() else interaction.guild.get_member(int(target_id[2:-1])) or discord.utils.get(interaction.guild.members, name=target_id.split("#")[0])
            if not target:
                await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="Пользователь не найден!", color=COLORS["error"]), ephemeral=True)
                return
            member = interaction.guild.get_member(target.id)
            if member and not interaction.user.top_role > member.top_role:
                await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="У вас недостаточно прав!", color=COLORS["error"]), ephemeral=True)
                return
            muted_until = datetime.utcnow() + timedelta(minutes=duration) if duration > 0 else None
            update_user_data(target.id, muted_until=muted_until.isoformat() if muted_until else None)
            role = discord.utils.get(interaction.guild.roles, name="Muted")
            if not role:
                role = await interaction.guild.create_role(name="Muted", permissions=discord.Permissions(text=False))
                for channel in interaction.guild.channels:
                    await channel.set_permissions(role, send_messages=False)
            if member:
                await member.add_roles(role)
            await modal_interaction.response.send_message(embed=discord.Embed(title="🔇 Пользователь замучен", description=f"{target.mention} замучен на {duration} мин" if duration > 0 else "навсегда" + "!", color=COLORS["success"]), ephemeral=True)
        except (ValueError, discord.errors.HTTPException) as e:
            await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="Неверный формат ID или ошибка!", color=COLORS["error"]), ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send(embed=discord.Embed(title="⏳ Тайм-аут", description="Время на ввод истекло!", color=COLORS["error"]), ephemeral=True)

async def unmute_member(user, interaction):
    await interaction.response.send_modal(
        title="🔊 Размутить пользователя",
        custom_id="unmute_modal",
        components=[
            discord.ui.TextInput(
                label="Укажите пользователя (ID или упоминание)",
                style=discord.TextInputStyle.short,
                custom_id="target_id",
                placeholder="123456789012345678 или @username",
                required=True
            )
        ]
    )
    try:
        modal_interaction = await bot.wait_for("modal_submit", check=lambda i: i.custom_id == "unmute_modal" and i.user == user, timeout=300)
        target_id = modal_interaction.components[0].value
        try:
            target = await bot.fetch_user(int(target_id)) if target_id.isdigit() else interaction.guild.get_member(int(target_id[2:-1])) or discord.utils.get(interaction.guild.members, name=target_id.split("#")[0])
            if not target:
                await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="Пользователь не найден!", color=COLORS["error"]), ephemeral=True)
                return
            member = interaction.guild.get_member(target.id)
            if member and not interaction.user.top_role > member.top_role:
                await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="У вас недостаточно прав!", color=COLORS["error"]), ephemeral=True)
                return
            update_user_data(target.id, muted_until=None)
            role = discord.utils.get(interaction.guild.roles, name="Muted")
            if member and role:
                await member.remove_roles(role)
            await modal_interaction.response.send_message(embed=discord.Embed(title="🔊 Пользователь размучен", description=f"{target.mention} размучен!", color=COLORS["success"]), ephemeral=True)
        except (ValueError, discord.errors.HTTPException) as e:
            await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="Неверный формат ID или ошибка!", color=COLORS["error"]), ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send(embed=discord.Embed(title="⏳ Тайм-аут", description="Время на ввод истекло!", color=COLORS["error"]), ephemeral=True)

async def ban_member(user, interaction):
    await interaction.response.send_modal(
        title="🚫 Забанить пользователя",
        custom_id="ban_modal",
        components=[
            discord.ui.TextInput(
                label="Укажите пользователя (ID или упоминание)",
                style=discord.TextInputStyle.short,
                custom_id="target_id",
                placeholder="123456789012345678 или @username",
                required=True
            ),
            discord.ui.TextInput(
                label="Причина (опционально)",
                style=discord.TextInputStyle.short,
                custom_id="reason",
                placeholder="Напишите причину...",
                required=False
            )
        ]
    )
    try:
        modal_interaction = await bot.wait_for("modal_submit", check=lambda i: i.custom_id == "ban_modal" and i.user == user, timeout=300)
        target_id = modal_interaction.components[0].value
        reason = modal_interaction.components[1].value or "Без причины"
        try:
            target = await bot.fetch_user(int(target_id)) if target_id.isdigit() else interaction.guild.get_member(int(target_id[2:-1])) or discord.utils.get(interaction.guild.members, name=target_id.split("#")[0])
            if not target:
                await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="Пользователь не найден!", color=COLORS["error"]), ephemeral=True)
                return
            member = interaction.guild.get_member(target.id)
            if member and not interaction.user.top_role > member.top_role:
                await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="У вас недостаточно прав!", color=COLORS["error"]), ephemeral=True)
                return
            await interaction.guild.ban(target, reason=reason)
            await modal_interaction.response.send_message(embed=discord.Embed(title="🚫 Пользователь забанен", description=f"{target.mention} забанен по причине: {reason}", color=COLORS["success"]), ephemeral=True)
        except (ValueError, discord.errors.HTTPException) as e:
            await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="Неверный формат ID или ошибка!", color=COLORS["error"]), ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send(embed=discord.Embed(title="⏳ Тайм-аут", description="Время на ввод истекло!", color=COLORS["error"]), ephemeral=True)

async def unban_member(user, interaction):
    await interaction.response.send_modal(
        title="✅ Разбанить пользователя",
        custom_id="unban_modal",
        components=[
            discord.ui.TextInput(
                label="Укажите пользователя (ID)",
                style=discord.TextInputStyle.short,
                custom_id="target_id",
                placeholder="123456789012345678",
                required=True
            )
        ]
    )
    try:
        modal_interaction = await bot.wait_for("modal_submit", check=lambda i: i.custom_id == "unban_modal" and i.user == user, timeout=300)
        target_id = modal_interaction.components[0].value
        try:
            target = await bot.fetch_user(int(target_id))
            if not target:
                await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="Пользователь не найден!", color=COLORS["error"]), ephemeral=True)
                return
            await interaction.guild.unban(target)
            await modal_interaction.response.send_message(embed=discord.Embed(title="✅ Пользователь разбанен", description=f"{target.mention} разбанен!", color=COLORS["success"]), ephemeral=True)
        except (ValueError, discord.errors.HTTPException) as e:
            await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="Неверный формат ID или ошибка!", color=COLORS["error"]), ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send(embed=discord.Embed(title="⏳ Тайм-аут", description="Время на ввод истекло!", color=COLORS["error"]), ephemeral=True)

async def clear_chat(user, interaction):
    await interaction.response.send_modal(
        title="🧹 Очистка чата",
        custom_id="clear_modal",
        components=[
            discord.ui.TextInput(
                label="Количество сообщений для удаления",
                style=discord.TextInputStyle.short,
                custom_id="amount",
                placeholder="10",
                required=True
            )
        ]
    )
    try:
        modal_interaction = await bot.wait_for("modal_submit", check=lambda i: i.custom_id == "clear_modal" and i.user == user, timeout=300)
        amount = int(modal_interaction.components[0].value)
        if amount <= 0 or amount > 100:  # Лимит Discord — 100 сообщений
            await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="Введите число от 1 до 100!", color=COLORS["error"]), ephemeral=True)
            return
        async for message in interaction.channel.history(limit=amount + 1):
            await message.delete()
        await modal_interaction.response.send_message(embed=discord.Embed(title="🧹 Чат очищен", description=f"Удалено {amount} сообщений!", color=COLORS["success"]), ephemeral=True)
    except (ValueError, discord.errors.HTTPException) as e:
        await interaction.followup.send(embed=discord.Embed(title="❌ Ошибка", description="Неверный формат или ошибка!", color=COLORS["error"]), ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send(embed=discord.Embed(title="⏳ Тайм-аут", description="Время на ввод истекло!", color=COLORS["error"]), ephemeral=True)

async def leaderboards(ctx):
    cursor.execute('SELECT user_id, xp, gold, crystals FROM users ORDER BY xp DESC LIMIT 10')
    top_users = cursor.fetchall()
    embed = discord.Embed(
        title=f"{EMOJIS['leaderboards']} Топ-10 игроков",
        color=COLORS["rainbow"]
    )
    for i, (user_id, xp, gold, crystals) in enumerate(top_users, 1):
        user = bot.get_user(user_id)
        embed.add_field(
            name=f"#{i} {user.name if user else 'Неизвестный'}",
            value=f"XP: {xp} | Золото: {gold} {EMOJIS['gold']} | Кристаллы: {crystals} {EMOJIS['crystals']}",
            inline=False
        )
    embed.set_image(url="https://i.imgur.com/8pZqL7G.gif")
    await ctx.send(embed=embed)

async def help_cmd(ctx):
    embed = discord.Embed(
        title=f"{EMOJIS['help']} Список команд",
        color=COLORS["purple"]
    )
    commands_list = [
        f"{EMOJIS['profile']} `!profile` — Показать профиль",
        f"{EMOJIS['mine']} `!mine` — Добыть кристаллы",
        f"{EMOJIS['work']} `!work` — Заработать золото",
        f"{EMOJIS['profit']} `!profit` — Получить прибыль",
        f"{EMOJIS['daily']} `!daily` — Ежедневная награда",
        f"{EMOJIS['gear']} `!gear` — Посмотреть и улучшить снаряжение",
        f"{EMOJIS['buyrole']} `!buyrole` — Купить роль",
        f"{EMOJIS['cooldowns']} `!cooldowns` — Проверить кулдауны",
        f"{EMOJIS['rps']} `!rps <оппонент>` — Игра Камень, Ножницы, Бумага",
        f"{EMOJIS['blackjack']} `!blackjack <оппонент> <ставка>` — Игра Блэкджек",
        f"{EMOJIS['transfer']} `!transfer <пользователь> <валюта> <кол-во>` — Передать валюту",
        f"{EMOJIS['leaderboards']} `!leaderboards` — Топ-10 игроков",
        f"{EMOJIS['cases']} `!cases` — Открыть меню кейсов",
        f"{EMOJIS['mute']} `!mute` — Замутить пользователя (админ)",
        f"{EMOJIS['ban']} `!ban` — Забанить пользователя (админ)",
        f"{EMOJIS['clear']} `!clear` — Очистить чат (админ)",
        f"{EMOJIS['give']} `!give` — Выдать валюту пользователю (админ)"
    ]
    embed.description = "\n".join(commands_list)
    embed.set_image(url="https://i.imgur.com/8pZqL7G.gif")
    await ctx.send(embed=embed, view=HelpView())

class HelpView(discord.ui.View):
    @discord.ui.button(label="Подробнее", style=discord.ButtonStyle.blurple, emoji=EMOJIS["help"])
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=discord.Embed(
            title="ℹ️ Подробности",
            description="Используйте команды с префиксом `!`. Для модерации нужны права администратора.\nЕсли есть вопросы, обращайтесь к администрации!",
            color=COLORS["purple"]
        ), ephemeral=True)

async def give_currency(user, interaction, currency: str):
    await interaction.response.send_modal(
        title=f"{EMOJIS['give']} Выдать валюту",
        custom_id="give_currency_modal",
        components=[
            discord.ui.TextInput(
                label="Укажите пользователя (ID или упоминание)",
                style=discord.TextInputStyle.short,
                custom_id="target_id",
                placeholder="123456789012345678 или @username",
                required=True
            ),
            discord.ui.TextInput(
                label="Количество",
                style=discord.TextInputStyle.short,
                custom_id="amount",
                placeholder="50",
                required=True
            )
        ]
    )
    try:
        modal_interaction = await bot.wait_for("modal_submit", check=lambda i: i.custom_id == "give_currency_modal" and i.user == user, timeout=300)
        target_id = modal_interaction.components[0].value
        amount = int(modal_interaction.components[1].value)
        if amount <= 0:
            await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="Количество должно быть положительным!", color=COLORS["error"]), ephemeral=True)
            return
        try:
            target = await bot.fetch_user(int(target_id)) if target_id.isdigit() else interaction.guild.get_member(int(target_id[2:-1])) or discord.utils.get(interaction.guild.members, name=target_id.split("#")[0])
            if not target:
                await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="Пользователь не найден!", color=COLORS["error"]), ephemeral=True)
                return
            if currency == "gold":
                update_user_data(target.id, gold=amount)
                await modal_interaction.response.send_message(embed=discord.Embed(title=f"{EMOJIS['give']} Выдача золота", description=f"Выдали {amount} {EMOJIS['gold']} {target.mention}!", color=COLORS["success"]), ephemeral=True)
            else:  # crystals
                update_user_data(target.id, crystals=amount)
                await modal_interaction.response.send_message(embed=discord.Embed(title="💎 Выдача кристаллов", description=f"Выдали {amount} {EMOJIS['crystals']} {target.mention}!", color=COLORS["success"]), ephemeral=True)
        except (ValueError, discord.errors.HTTPException) as e:
            await modal_interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="Неверный формат ID или ошибка!", color=COLORS["error"]), ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send(embed=discord.Embed(title="⏳ Тайм-аут", description="Время на ввод истекло!", color=COLORS["error"]), ephemeral=True)

async def open_case(user, interaction, case_id):
    _, gold, _, _, _, _, _, _, _, _ = get_user_data(user.id)
    case = cursor.execute('SELECT cost, rewards FROM cases WHERE case_id = ?', (case_id,)).fetchone()
    if not case:
        await interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description="Кейс не найден!", color=COLORS["error"]), ephemeral=True)
        return
    cost, rewards = case
    if gold < cost:
        await interaction.response.send_message(embed=discord.Embed(title="❌ Недостаточно", description=f"Нужно {cost} {EMOJIS['gold']}!", color=COLORS["error"]), ephemeral=True)
        return
    rewards_list = get_case_rewards(case_id)
    total_weight = sum(weight for _, weight in rewards_list)
    rand = random.random() * total_weight
    cumulative = 0
    reward = 0
    for value, weight in rewards_list:
        cumulative += weight
        if rand <= cumulative:
            reward = value
            break
    update_user_data(user.id, gold=-cost, gold=reward)
    await interaction.response.send_message(embed=discord.Embed(
        title=f"{EMOJIS['cases']} Вы открыли {case_id.replace('_', ' ').title()}",
        description=f"Вы потратили {cost} {EMOJIS['gold']} и выиграли {reward} {EMOJIS['gold']}!",
        color=COLORS["rainbow"]
    ), ephemeral=True)

# События
@bot.event
async def on_ready():
    logger.info(f"Бот {bot.user} запущен!")
    print(f"✅ Бот {bot.user} запущен!")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="за тобой в шахте!"))

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    current_time = datetime.utcnow()
    last_time = last_message_time.get(message.author.id, current_time - timedelta(minutes=1))
    if current_time - last_time >= timedelta(minutes=1):
        xp, gold, _, _, crystals, _, _, _, _, _ = get_user_data(message.author.id)
        xp_gain = 2
        update_user_data(message.author.id, xp=xp_gain)
        last_message_time[message.author.id] = current_time
        if xp % 100 == 0:
            update_user_data(message.author.id, gold=10)
            await message.channel.send(embed=discord.Embed(title="🎉 Новый уровень!", description=f"{message.author.mention} получил 10 {EMOJIS['gold']}!", color=COLORS["gold"]))
        # Обновление прогресса ежедневных заданий
        if message.author.id not in daily_quests:
            daily_quests[message.author.id] = {"type": "messages", "target": random.randint(5, 15), "progress": 0}
        daily_quests[message.author.id]["progress"] += 1
    await bot.process_commands(message)

@bot.event
async def on_typing(channel, user, when):
    if user.bot or channel.type != discord.ChannelType.text or not channel.permissions_for(channel.guild.me).send_messages or channel.guild is None:
        return
    if user.typing and not user.typing_message:
        embed = discord.Embed(
            title="📋 Доступные команды",
            description=f"Используй `{PREFIX}` перед командой:\n\n"
                       f"{EMOJIS['profile']} `profile` — Посмотреть профиль\n"
                       f"{EMOJIS['mine']} `mine` — Добыть кристаллы\n"
                       f"{EMOJIS['work']} `work` — Заработать золото\n"
                       f"{EMOJIS['profit']} `profit` — Получить прибыль\n"
                       f"{EMOJIS['daily']} `daily` — Ежедневная награда\n"
                       f"{EMOJIS['gear']} `gear` — Снаряжение\n"
                       f"{EMOJIS['buyrole']} `buyrole` — Купить роль\n"
                       f"{EMOJIS['cooldowns']} `cooldowns` — Проверить кулдауны\n"
                       f"{EMOJIS['rps']} `rps` — Камень, Ножницы, Бумага\n"
                       f"{EMOJIS['blackjack']} `blackjack` — Блэкджек\n"
                       f"{EMOJIS['leaderboards']} `leaderboards` — Топ-10 игроков\n"
                       f"{EMOJIS['cases']} `cases` — Открыть кейсы\n"
                       f"{EMOJIS['help']} `help` — Список команд\n"
                       f"{EMOJIS['mute']} `mute` — Модерация (админ)\n"
                       f"{EMOJIS['ban']} `ban` — Модерация (админ)\n"
                       f"{EMOJIS['clear']} `clear` — Очистка чата (админ)\n"
                       f"{EMOJIS['give']} `give` — Выдать валюту (админ)",
            color=COLORS["purple"]
        )
        embed.set_thumbnail(url="https://i.imgur.com/8pZqL7G.gif")
        await channel.send(embed=embed, delete_after=10.0)

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and not before.channel:
        voice_activity[member.id] = datetime.utcnow()
    elif before.channel and not after.channel and member.id in voice_activity:
        duration = (datetime.utcnow() - voice_activity.pop(member.id)).seconds // 60
        if not before.self_mute and not before.self_deaf:
            earned_gold = duration
            _, helmet_level, _, _ = get_gear(member.id)
            crystals_gain = int(duration * (1 + helmet_level * 0.05))
            update_user_data(member.id, gold=earned_gold, crystals=crystals_gain)
            try:
                embed = discord.Embed(
                    title="🎙 Голосовой чат",
                    description=f"Вы провели {duration} мин: +{earned_gold} {EMOJIS['gold']}, +{crystals_gain} {EMOJIS['crystals']}!",
                    color=COLORS["blue"]
                )
                embed.set_image(url="https://i.imgur.com/8pZqL7G.gif")
                await member.send(embed=embed)
            except discord.Forbidden:
                logger.warning(f"Не удалось отправить сообщение {member.id}")

@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL.replace("🔔", "").replace("-", "").lower())
    if channel:
        embed = discord.Embed(
            title=f"🌟 Добро пожаловать, {member.name}!",
            description=f"Привет {member.mention}, теперь ты новый участник Forever Alone.\nПерейди к каналу #rules, чтобы узнать правила!",
            color=COLORS["rainbow"]
        )
        embed.set_thumbnail(url="https://i.imgur.com/8pZqL7G.gif")  # Аниме-аватар
        embed.set_image(url="https://i.imgur.com/8pZqL7G.gif")  # Анимированный фон приветствия
        await channel.send(embed=embed)

# Команды
@bot.command()
async def profile(ctx):
    await show_profile(ctx.author, ctx)

@bot.command()
async def mine(ctx):
    await mine(ctx.author, ctx)

@bot.command()
async def work(ctx):
    await work(ctx.author, ctx)

@bot.command()
async def profit(ctx):
    await profit(ctx.author, ctx)

@bot.command()
async def sell(ctx, amount: int):
    await sell_crystals(ctx.author, ctx, amount)

@bot.command()
async def daily(ctx):
    await daily(ctx.author, ctx)

@bot.command()
async def gear(ctx):
    pickaxe, helmet, gloves, boots = get_gear(ctx.author.id)
    embed = discord.Embed(
        title=f"{EMOJIS['gear']} Снаряжение шахтёра",
        description=f"Твоё оборудование, {ctx.author.mention}",
        color=COLORS["orange"]
    )
    embed.add_field(name="Кирка ⛏", value=f"Ур. {pickaxe}: +{pickaxe * 5}% к добыче", inline=True)
    embed.add_field(name="Шлем ⛑", value=f"Ур. {helmet}: +{helmet * 5}% к голосовым 💎", inline=True)
    embed.add_field(name="Перчатки 🧤", value=f"Ур. {gloves}: +{gloves * 5}% к текстовым 💎", inline=True)
    embed.add_field(name="Ботинки 👢", value=f"Ур. {boots}: +{boots * 5}% к ежедневке", inline=True)
    embed.set_thumbnail(url="https://i.imgur.com/8pZqL7G.gif")
    await ctx.send(embed=embed, view=GearView())

@bot.command()
async def actions(ctx):
    embed = discord.Embed(
        title="🎮 Действия",
        description="Выбери, что делать!",
        color=COLORS["default"]
    )
    embed.set_image(url="https://i.imgur.com/8pZqL7G.gif")
    await ctx.send(embed=embed, view=ActionView())

@bot.command()
async def buyrole(ctx):
    embed = discord.Embed(
        title=f"{EMOJIS['buyrole']} Магазин ролей",
        description=f"Выбери роль для покупки, {ctx.author.mention}",
        color=COLORS["gold"]
    )
    for role_id, price in ROLES_CONFIG.items():
        role = discord.utils.get(ctx.guild.roles, id=int(role_id))
        if role:
            embed.add_field(name=f"{role.name}", value=f"Цена: {price} {EMOJIS['gold']}", inline=True)
    embed.set_thumbnail(url="https://i.imgur.com/8pZqL7G.gif")
    await ctx.send(embed=embed, view=RoleShopView())

@bot.command()
@commands.has_permissions(administrator=True)
async def moderation(ctx):
    embed = discord.Embed(
        title="🔧 Меню модерации",
        description="Выберите действие для модерации!",
        color=COLORS["purple"]
    )
    embed.set_image(url="https://i.imgur.com/8pZqL7G.gif")
    await ctx.send(embed=embed, view=ModerationView())

@bot.command()
@commands.has_permissions(administrator=True)
async def give(ctx):
    embed = discord.Embed(
        title=f"{EMOJIS['give']} Выдать валюту",
        description="Выберите тип валюты для выдачи!",
        color=COLORS["gold"]
    )
    embed.set_image(url="https://i.imgur.com/8pZqL7G.gif")
    await ctx.send(embed=embed, view=CurrencyView())

@bot.command()
async def cases(ctx):
    embed = discord.Embed(
        title=f"{EMOJIS['cases']} Меню кейсов",
        description="Выберите кейс для открытия!",
        color=COLORS["rainbow"]
    )
    embed.set_image(url="https://i.imgur.com/8pZqL7G.gif")
    await ctx.send(embed=embed, view=CaseView())

@bot.command()
async def leaderboards(ctx):
    await leaderboards(ctx)

@bot.command()
async def help(ctx):
    await help_cmd(ctx)

@bot.command()
async def cooldowns(ctx):
    _, _, _, _, _, _, last_mine, last_work, last_profit, _ = get_user_data(ctx.author.id)
    now = datetime.utcnow()
    cooldowns = []
    
    if last_mine:
        can_mine, error = check_cooldown(last_mine, 300, "добычи")
        if not can_mine:
            cooldowns.append(error)
    
    if last_work:
        can_work, error = check_cooldown(last_work, 3600, "работы")
        if not can_work:
            cooldowns.append(error)
    
    if last_profit:
        can_profit, error = check_cooldown(last_profit, 14400, "прибыли")
        if not can_profit:
            cooldowns.append(error)
    
    if last_daily := get_user_data(ctx.author.id)[2]:
        can_daily, error = check_cooldown(last_daily, 86400, "ежедневки")
        if not can_daily:
            cooldowns.append(error)
    
    if cooldowns:
        embed = discord.Embed(
            title=f"{EMOJIS['cooldowns']} Кулдауны",
            description="\n".join(cooldowns),
            color=COLORS["error"]
        )
        embed.set_image(url="https://i.imgur.com/8pZqL7G.gif")
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="✅ Кулдауны",
            description=f"{ctx.author.mention}, все действия доступны!",
            color=COLORS["success"]
        )
        embed.set_image(url="https://i.imgur.com/8pZqL7G.gif")
        await ctx.send(embed=embed)

# Активность
@tasks.loop(minutes=1)
async def track_voice_activity():
    for member_id in list(voice_activity.keys()):
        update_user_data(member_id, gold=1)

@tasks.loop(hours=24)
async def reset_daily_quests():
    global daily_quests
    daily_quests = {}
    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=WELCOME_CHANNEL.replace("🔔", "").replace("-", "").lower())
        if channel:
            embed = discord.Embed(
                title="🌟 Новые ежедневные задания!",
                description="Выполняйте задания для бонусов! Сегодня: напишите 5-15 сообщений.",
                color=COLORS["rainbow"]
            )
            embed.set_image(url="https://i.imgur.com/8pZqL7G.gif")
            await channel.send(embed=embed)

# Запуск бота
if __name__ == "__main__":
    track_voice_activity.start()
    reset_daily_quests.start()
    bot.run(TOKEN)
