import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import random
import json
import os
from database import get_user_data, update_user_data, get_gear, update_gear
from economy import COOLDOWNS, GEAR_BONUS_PER_LEVEL, get_gear_cost, check_cooldown

# Логирование
logger = logging.getLogger(__name__)

# Загрузка конфигурации
with open("config.json", "r") as file:
    config = json.load(file)
    TOKEN = os.getenv("DISCORD_TOKEN", config["TOKEN"])
    PREFIX = config["PREFIX"]
    ROLES_CONFIG = config["roles"]
    WELCOME_CHANNEL = config["welcome_channel"]
    ROLES_CHANNEL = config["roles_channel"]
    ADMIN_CHANNEL = config["admin_channel"]

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# Глобальные переменные
last_message_time = {}
voice_activity = {}

# Цвета для эмбедов
COLORS = {
    "default": discord.Color.blue(),
    "success": discord.Color.green(),
    "error": discord.Color.red(),
    "gold": discord.Color.gold(),
    "purple": discord.Color.purple()
}

# Эмодзи
EMOJIS = {
    "gold": "🪙",
    "crystals": "💎",
    "mine": "⛏",
    "work": "👷",
    "profit": "💸",
    "daily": "🎁",
    "profile": "👤",
    "gear": "⚒",
    "rps": "🆚",
    "blackjack": "🃏",
    "transfer": "💸",
    "give": "🎁",
    "buyrole": "🏷",
    "cooldowns": "⏳"
}

class ProfileView(discord.ui.View):
    @discord.ui.button(label="Профиль", style=discord.ButtonStyle.green, emoji=EMOJIS["profile"])
    async def profile_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_profile(interaction.user, interaction)

class GearView(discord.ui.View):
    @discord.ui.button(label="Кирка", style=discord.ButtonStyle.blurple, emoji=EMOJIS["mine"])
    async def pickaxe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await upgrade_gear(interaction.user, "pickaxe", interaction)

    @discord.ui.button(label="Шлем", style=discord.ButtonStyle.blurple, emoji="⛑")
    async def helmet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await upgrade_gear(interaction.user, "helmet", interaction)

    @discord.ui.button(label="Перчатки", style=discord.ButtonStyle.blurple, emoji="🧤")
    async def gloves(self, interaction: discord.Interaction, button: discord.ui.Button):
        await upgrade_gear(interaction.user, "gloves", interaction)

    @discord.ui.button(label="Ботинки", style=discord.ButtonStyle.blurple, emoji="👢")
    async def boots(self, interaction: discord.Interaction, button: discord.ui.Button):
        await upgrade_gear(interaction.user, "boots", interaction)

class ActionView(discord.ui.View):
    @discord.ui.button(label="Добыть", style=discord.ButtonStyle.green, emoji=EMOJIS["mine"])
    async def mine(self, interaction: discord.Interaction, button: discord.ui.Button):
        await mine(interaction.user, interaction)

    @discord.ui.button(label="Работать", style=discord.ButtonStyle.green, emoji=EMOJIS["work"])
    async def work(self, interaction: discord.Interaction, button: discord.ui.Button):
        await work(interaction.user, interaction)

    @discord.ui.button(label="Получить прибыль", style=discord.ButtonStyle.green, emoji=EMOJIS["profit"])
    async def profit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await profit(interaction.user, interaction)

    @discord.ui.button(label="Продать кристаллы", style=discord.ButtonStyle.red, emoji="💰")
    async def sell(self, interaction: discord.Interaction, button: discord.ui.Button):
        await sell_crystals(interaction.user, interaction, 100)

    @discord.ui.button(label="Ежедневка", style=discord.ButtonStyle.grey, emoji=EMOJIS["daily"])
    async def daily(self, interaction: discord.Interaction, button: discord.ui.Button):
        await daily(interaction.user, interaction)

class AdminMessageView(discord.ui.View):
    @discord.ui.button(label="Отправить", style=discord.ButtonStyle.green, emoji="📩")
    async def send(self, interaction: discord.Interaction, button: discord.ui.Button):
        await admin_message(interaction.user, interaction)

class RoleShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_roles()

    def add_roles(self):
        for role_id, price in ROLES_CONFIG.items():
            role = discord.utils.get(bot.get_guild(0).roles, id=int(role_id))
            if role:
                self.add_item(discord.ui.Button(label=f"{role.name} ({price} {EMOJIS['gold']})", style=discord.ButtonStyle.green, custom_id=f"buy_role_{role_id}"))

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.data["custom_id"].startswith("buy_role_"):
            role_id = interaction.data["custom_id"].split("_")[-1]
            await buy_role(interaction.user, role_id, interaction)
        return True

async def show_profile(user, ctx_or_interaction):
    xp, gold, _, _, crystals, daily_streak, _, _, _ = get_user_data(user.id)
    level = xp // 100
    embed = discord.Embed(
        title=f"👤 Профиль {user.name}",
        description=f"Информация о {user.mention}",
        color=COLORS["default"]
    )
    embed.add_field(name=f"Уровень {EMOJIS['profile']}", value=f"{level} (XP: {xp})", inline=True)
    embed.add_field(name=f"Золотые монетки {EMOJIS['gold']}", value=f"{gold}", inline=True)
    embed.add_field(name=f"Кристаллы {EMOJIS['crystals']}", value=f"{crystals}", inline=True)
    embed.add_field(name=f"Стрик {EMOJIS['daily']}", value=f"{daily_streak} дней", inline=True)
    embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
    embed.set_image(url="https://i.imgur.com/8pZqL7G.jpeg")  # Пример аниме-изображения
    if isinstance(ctx_or_interaction, discord.Interaction):
        await ctx_or_interaction.response.send_message(embed=embed, view=ProfileView(), ephemeral=True)
    else:
        await ctx_or_interaction.send(embed=embed, view=ProfileView())

@bot.command(name="profile")
async def profile_cmd(ctx):
    await show_profile(ctx.author, ctx)

@bot.event
async def on_typing(channel, user, when):
    if user.bot:
        return
    if channel.type != discord.ChannelType.text:
        return
    if not channel.permissions_for(channel.guild.me).send_messages:
        return
    if channel.guild is None:
        return
    prefix = PREFIX
    if not user.typing:
        return
    content = user.typing_message.content if user.typing_message else ""
    if content.startswith(prefix):
        embed = discord.Embed(
            title=f"📋 Доступные команды для {user.name}",
            description=f"Используй `{prefix}` перед командой:\n\n"
                       f"{EMOJIS['profile']} `profile` — Посмотреть свой профиль\n"
                       f"{EMOJIS['mine']} `mine` — Добыть кристаллы\n"
                       f"{EMOJIS['work']} `work` — Заработать золото\n"
                       f"{EMOJIS['profit']} `profit` — Получить прибыль\n"
                       f"{EMOJIS['daily']} `daily` — Ежедневная награда\n"
                       f"{EMOJIS['gear']} `gear` — Просмотреть снаряжение\n"
                       f"{EMOJIS['buyrole']} `buyrole` — Купить роль\n"
                       f"{EMOJIS['cooldowns']} `cooldowns` — Проверить кулдауны\n"
                       f"{EMOJIS['rps']} `rps` — Игра Камень, Ножницы, Бумага\n"
                       f"{EMOJIS['blackjack']} `blackjack` — Игра Блэкджек",
            color=COLORS["purple"]
        )
        embed.set_thumbnail(url="https://i.imgur.com/8pZqL7G.jpeg")
        await channel.send(embed=embed, delete_after=10.0)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    current_time = datetime.utcnow()
    last_time = last_message_time.get(message.author.id, current_time - timedelta(minutes=1))
    if current_time - last_time >= timedelta(minutes=1):
        xp, gold, _, _, crystals, _, _, _, _ = get_user_data(message.author.id)
        xp_gain = 2
        update_user_data(message.author.id, xp=xp_gain)
        last_message_time[message.author.id] = current_time
        if xp % 100 == 0:
            update_user_data(message.author.id, gold=10)
            embed = discord.Embed(
                title="🎉 Новый уровень!",
                description=f"{message.author.mention}, вы достигли нового уровня и получили 10 {EMOJIS['gold']}!",
                color=COLORS["gold"]
            )
            await message.channel.send(embed=embed)
    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and not before.channel:
        voice_activity[member.id] = datetime.utcnow()
    elif before.channel and not after.channel and member.id in voice_activity:
        duration = (datetime.utcnow() - voice_activity.pop(member.id)).seconds // 60
        if not before.self_mute and not before.self_deaf:
            earned_gold = duration
            _, helmet_level, _, _ = get_gear(member.id)
            crystals_gain = int(duration * (1 + helmet_level * GEAR_BONUS_PER_LEVEL))
            update_user_data(member.id, gold=earned_gold, crystals=crystals_gain)
            try:
                embed = discord.Embed(
                    title="🎙 Голосовой чат",
                    description=f"Вы провели {duration} минут в голосовом чате: +{earned_gold} {EMOJIS['gold']}, +{crystals_gain} {EMOJIS['crystals']}!",
                    color=COLORS["blue"]
                )
                await member.send(embed=embed)
            except discord.Forbidden:
                logger.warning(f"Не удалось отправить сообщение {member.id}")

@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name=WELCOME_CHANNEL.replace("🔔", "").replace("-", "").lower())
    if channel:
        embed = discord.Embed(
            title=f"🌟 Добро пожаловать, {member.name}!",
            description=f"Привет {member.mention}, теперь ты новый участник Forever Alone. Перейди к каналу #rules, чтобы узнать правила!",
            color=COLORS["purple"]
        )
        embed.set_thumbnail(url="https://i.imgur.com/8pZqL7G.jpeg")  # Аниме-аватар
        embed.set_image(url="https://i.imgur.com/8pZqL7G.jpeg")  # Фон приветствия, как на скриншоте
        await channel.send(embed=embed)

@bot.command(name="mine")
async def mine_cmd(ctx):
    _, _, _, _, _, _, last_mine, _, _ = get_user_data(ctx.author.id)
    can_mine, error = check_cooldown(last_mine, COOLDOWNS["mine"], "добычи")
    if not can_mine:
        embed = discord.Embed(title="⏳ Кулдаун", description=f"{ctx.author.mention}, {error}", color=COLORS["error"])
        await ctx.send(embed=embed)
        return
    pickaxe_level, _, _, _ = get_gear(ctx.author.id)
    crystals_gain = int(random.randint(5, 15) * (1 + pickaxe_level * GEAR_BONUS_PER_LEVEL))
    update_user_data(ctx.author.id, crystals=crystals_gain, last_mine=datetime.utcnow().isoformat())
    embed = discord.Embed(
        title=f"{EMOJIS['mine']} Добыча",
        description=f"{ctx.author.mention}, вы добыли {crystals_gain} {EMOJIS['crystals']} в шахте!",
        color=COLORS["success"]
    )
    await ctx.send(embed=embed, view=ActionView())

async def mine(user, interaction):
    _, _, _, _, _, _, last_mine, _, _ = get_user_data(user.id)
    can_mine, error = check_cooldown(last_mine, COOLDOWNS["mine"], "добычи")
    if not can_mine:
        await interaction.response.send_message(embed=discord.Embed(title="⏳ Кулдаун", description=error, color=COLORS["error"]), ephemeral=True)
        return
    pickaxe_level, _, _, _ = get_gear(user.id)
    crystals_gain = int(random.randint(5, 15) * (1 + pickaxe_level * GEAR_BONUS_PER_LEVEL))
    update_user_data(user.id, crystals=crystals_gain, last_mine=datetime.utcnow().isoformat())
    await interaction.response.send_message(embed=discord.Embed(
        title=f"{EMOJIS['mine']} Добыча",
        description=f"Вы добыли {crystals_gain} {EMOJIS['crystals']} в шахте!",
        color=COLORS["success"]
    ), ephemeral=True)

@bot.command(name="sell")
async def sell_cmd(ctx, amount: int):
    _, _, _, _, crystals, _, _ = get_user_data(ctx.author.id)
    if amount <= 0 or amount > crystals:
        embed = discord.Embed(
            title="❌ Ошибка",
            description=f"{ctx.author.mention}, укажите корректное количество кристаллов (у вас {crystals} {EMOJIS['crystals']})!",
            color=COLORS["error"]
        )
        await ctx.send(embed=embed)
        return
    gold_gain = amount // 2
    update_user_data(ctx.author.id, crystals=-amount, gold=gold_gain)
    embed = discord.Embed(
        title="💰 Продажа",
        description=f"{ctx.author.mention}, вы продали {amount} {EMOJIS['crystals']} за {gold_gain} {EMOJIS['gold']}!",
        color=COLORS["gold"]
    )
    await ctx.send(embed=embed, view=ActionView())

async def sell_crystals(user, interaction, amount):
    _, _, _, _, crystals, _, _ = get_user_data(user.id)
    if amount <= 0 or amount > crystals:
        await interaction.response.send_message(embed=discord.Embed(
            title="❌ Ошибка",
            description=f"Укажите корректное количество кристаллов (у вас {crystals} {EMOJIS['crystals']})!",
            color=COLORS["error"]
        ), ephemeral=True)
        return
    gold_gain = amount // 2
    update_user_data(user.id, crystals=-amount, gold=gold_gain)
    await interaction.response.send_message(embed=discord.Embed(
        title="💰 Продажа",
        description=f"Вы продали {amount} {EMOJIS['crystals']} за {gold_gain} {EMOJIS['gold']}!",
        color=COLORS["gold"]
    ), ephemeral=True)

@bot.command(name="work")
async def work_cmd(ctx):
    _, gold, _, _, _, _, _, last_work, _ = get_user_data(ctx.author.id)
    can_work, error = check_cooldown(last_work, COOLDOWNS["work"], "работы")
    if not can_work:
        embed = discord.Embed(title="⏳ Кулдаун", description=f"{ctx.author.mention}, {error}", color=COLORS["error"])
        await ctx.send(embed=embed)
        return
    gold_gain = int(random.randint(5, 10))
    update_user_data(ctx.author.id, gold=gold_gain, last_work=datetime.utcnow().isoformat())
    embed = discord.Embed(
        title=f"{EMOJIS['work']} Работа",
        description=f"{ctx.author.mention}, вы поработали и получили {gold_gain} {EMOJIS['gold']}!",
        color=COLORS["success"]
    )
    await ctx.send(embed=embed, view=ActionView())

async def work(user, interaction):
    _, gold, _, _, _, _, _, last_work, _ = get_user_data(user.id)
    can_work, error = check_cooldown(last_work, COOLDOWNS["work"], "работы")
    if not can_work:
        await interaction.response.send_message(embed=discord.Embed(title="⏳ Кулдаун", description=error, color=COLORS["error"]), ephemeral=True)
        return
    gold_gain = int(random.randint(5, 10))
    update_user_data(user.id, gold=gold_gain, last_work=datetime.utcnow().isoformat())
    await interaction.response.send_message(embed=discord.Embed(
        title=f"{EMOJIS['work']} Работа",
        description=f"Вы поработали и получили {gold_gain} {EMOJIS['gold']}!",
        color=COLORS["success"]
    ), ephemeral=True)

@bot.command(name="daily")
async def daily_cmd(ctx):
    _, gold, last_daily, _, crystals, daily_streak, _, _, _ = get_user_data(ctx.author.id)
    can_daily, error = check_cooldown(last_daily, COOLDOWNS["daily"], "ежедневной награды")
    if not can_daily:
        embed = discord.Embed(title="❌ Ошибка", description=f"{ctx.author.mention}, {error}", color=COLORS["error"])
        await ctx.send(embed=embed)
        return
    daily_multiplier = 1 + (daily_streak * 0.1)
    gold_reward = int(random.randint(10, 20) * daily_multiplier)
    crystals_reward = int(random.randint(5, 10) * daily_multiplier)
    new_streak = daily_streak + 1 if last_daily and (datetime.utcnow() - datetime.fromisoformat(last_daily)).days == 1 else 1
    update_user_data(ctx.author.id, gold=gold_reward, crystals=crystals_reward, last_daily=datetime.utcnow().isoformat(), daily_streak=new_streak)
    embed = discord.Embed(
        title=f"{EMOJIS['daily']} Ежедневная награда",
        description=f"{ctx.author.mention}, вы получили: {gold_reward} {EMOJIS['gold']}, {crystals_reward} {EMOJIS['crystals']}! Стрик: {new_streak} дней.",
        color=COLORS["gold"]
    )
    await ctx.send(embed=embed, view=ActionView())

async def daily(user, interaction):
    _, gold, last_daily, _, crystals, daily_streak, _, _, _ = get_user_data(user.id)
    can_daily, error = check_cooldown(last_daily, COOLDOWNS["daily"], "ежедневной награды")
    if not can_daily:
        await interaction.response.send_message(embed=discord.Embed(title="❌ Ошибка", description=error, color=COLORS["error"]), ephemeral=True)
        return
    daily_multiplier = 1 + (daily_streak * 0.1)
    gold_reward = int(random.randint(10, 20) * daily_multiplier)
    crystals_reward = int(random.randint(5, 10) * daily_multiplier)
    new_streak = daily_streak + 1 if last_daily and (datetime.utcnow() - datetime.fromisoformat(last_daily)).days == 1 else 1
    update_user_data(user.id, gold=gold_reward, crystals=crystals_reward, last_daily=datetime.utcnow().isoformat(), daily_streak=new_streak)
    await interaction.response.send_message(embed=discord.Embed(
        title=f"{EMOJIS['daily']} Ежедневная награда",
        description=f"Вы получили: {gold_reward} {EMOJIS['gold']}, {crystals_reward} {EMOJIS['crystals']}! Стрик: {new_streak} дней.",
        color=COLORS["gold"]
    ), ephemeral=True)

@bot.command(name="profit")
async def profit_cmd(ctx):
    _, gold, _, _, _, _, _, _, last_profit = get_user_data(ctx.author.id)
    can_profit, error = check_cooldown(last_profit, COOLDOWNS["profit"], "получения прибыли")
    if not can_profit:
        embed = discord.Embed(title="⏳ Кулдаун", description=f"{ctx.author.mention}, {error}", color=COLORS["error"])
        await ctx.send(embed=embed)
        return
    base_chance = 0.2
    profit = int(random.randint(50, 100)) if random.random() < base_chance else 0
    update_user_data(ctx.author.id, gold=profit, last_profit=datetime.utcnow().isoformat())
    if profit:
        embed = discord.Embed(
            title=f"{EMOJIS['profit']} Прибыль",
            description=f"{ctx.author.mention}, вы получили прибыль {profit} {EMOJIS['gold']}!",
            color=COLORS["success"]
        )
    else:
        embed = discord.Embed(
            title="😔 Неудача",
            description=f"{ctx.author.mention}, удача не на вашей стороне. Попробуйте снова через 4 часа!",
            color=COLORS["error"]
        )
    await ctx.send(embed=embed, view=ActionView())

async def profit(user, interaction):
    _, gold, _, _, _, _, _, _, last_profit = get_user_data(user.id)
    can_profit, error = check_cooldown(last_profit, COOLDOWNS["profit"], "получения прибыли")
    if not can_profit:
        await interaction.response.send_message(embed=discord.Embed(title="⏳ Кулдаун", description=error, color=COLORS["error"]), ephemeral=True)
        return
    base_chance = 0.2
    profit = int(random.randint(50, 100)) if random.random() < base_chance else 0
    update_user_data(user.id, gold=profit, last_profit=datetime.utcnow().isoformat())
    if profit:
        await interaction.response.send_message(embed=discord.Embed(
            title=f"{EMOJIS['profit']} Прибыль",
            description=f"Вы получили прибыль {profit} {EMOJIS['gold']}!",
            color=COLORS["success"]
        ), ephemeral=True)
    else:
        await interaction.response.send_message(embed=discord.Embed(
            title="😔 Неудача",
            description="Удача не на вашей стороне. Попробуйте снова через 4 часа!",
            color=COLORS["error"]
        ), ephemeral=True)

@bot.command(name="gear")
async def gear_cmd(ctx):
    pickaxe_level, helmet_level, gloves_level, boots_level = get_gear(ctx.author.id)
    embed = discord.Embed(
        title=f"{EMOJIS['gear']} Снаряжение шахтёра",
        description=f"Ваше оборудование, {ctx.author.mention}",
        color=COLORS["orange"]
    )
    embed.add_field(name=f"Кирка {EMOJIS['mine']}", value=f"Уровень {pickaxe_level}: +{pickaxe_level * 5}% к добыче {EMOJIS['crystals']}", inline=True)
    embed.add_field(name=f"Шлем ⛑", value=f"Уровень {helmet_level}: +{helmet_level * 5}% к {EMOJIS['crystals']} от голосового чата", inline=True)
    embed.add_field(name=f"Перчатки 🧤", value=f"Уровень {gloves_level}: +{gloves_level * 5}% к {EMOJIS['crystals']} от текстового чата", inline=True)
    embed.add_field(name=f"Ботинки 👢", value=f"Уровень {boots_level}: +{boots_level * 5}% к ежедневным {EMOJIS['crystals']}", inline=True)
    embed.set_thumbnail(url="https://i.imgur.com/8pZqL7G.jpeg")  # Изображение шахтёра
    await ctx.send(embed=embed, view=GearView())

async def upgrade_gear(user, gear_name, interaction):
    gear_map = {"pickaxe": "pickaxe_level", "helmet": "helmet_level", "gloves": "gloves_level", "boots": "boots_level"}
    if gear_name not in gear_map:
        await interaction.response.send_message(embed=discord.Embed(
            title="❌ Ошибка",
            description="Доступные предметы: pickaxe, helmet, gloves, boots",
            color=COLORS["error"]
        ), ephemeral=True)
        return
    _, _, _, _, crystals, _, _ = get_user_data(user.id)
    pickaxe_level, helmet_level, gloves_level, boots_level = get_gear(user.id)
    current_level = {"pickaxe_level": pickaxe_level, "helmet_level": helmet_level, "gloves_level": gloves_level, "boots_level": boots_level}[gear_map[gear_name]]
    cost = get_gear_cost(current_level)
    if crystals < cost:
        await interaction.response.send_message(embed=discord.Embed(
            title="❌ Ошибка",
            description=f"Недостаточно кристаллов! Нужно: {cost} {EMOJIS['crystals']}",
            color=COLORS["error"]
        ), ephemeral=True)
        return
    update_user_data(user.id, crystals=-cost)
    if gear_name == "pickaxe":
        update_gear(user.id, pickaxe_level=current_level + 1)
    elif gear_name == "helmet":
        update_gear(user.id, helmet_level=current_level + 1)
    elif gear_name == "gloves":
        update_gear(user.id, gloves_level=current_level + 1)
    elif gear_name == "boots":
        update_gear(user.id, boots_level=current_level + 1)
    embed = discord.Embed(
        title="✅ Улучшение",
        description=f"Вы улучшили {gear_name} до уровня {current_level + 1} за {cost} {EMOJIS['crystals']}!",
        color=COLORS["success"]
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command(name="upgrade_gear")
async def upgrade_gear_cmd(ctx):
    pickaxe_level, helmet_level, gloves_level, boots_level = get_gear(ctx.author.id)
    embed = discord.Embed(
        title=f"{EMOJIS['gear']} Меню улучшений снаряжения",
        description=f"Выберите предмет для прокачки, {ctx.author.mention}",
        color=COLORS["orange"]
    )
    embed.add_field(name=f"Кирка {EMOJIS['mine']}", value=f"Уровень {pickaxe_level}: +{pickaxe_level * 5}% к добыче {EMOJIS['crystals']}\nЦена: {get_gear_cost(pickaxe_level)} {EMOJIS['crystals']}", inline=True)
    embed.add_field(name=f"Шлем ⛑", value=f"Уровень {helmet_level}: +{helmet_level * 5}% к {EMOJIS['crystals']} от голосового чата\nЦена: {get_gear_cost(helmet_level)} {EMOJIS['crystals']}", inline=True)
    embed.add_field(name=f"Перчатки 🧤", value=f"Уровень {gloves_level}: +{gloves_level * 5}% к {EMOJIS['crystals']} от текстового чата\nЦена: {get_gear_cost(gloves_level)} {EMOJIS['crystals']}", inline=True)
    embed.add_field(name=f"Ботинки 👢", value=f"Уровень {boots_level}: +{boots_level * 5}% к ежедневным {EMOJIS['crystals']}\nЦена: {get_gear_cost(boots_level)} {EMOJIS['crystals']}", inline=True)
    embed.set_thumbnail(url="https://i.imgur.com/8pZqL7G.jpeg")
    await ctx.send(embed=embed, view=GearView())

@bot.command(name="rps")
async def rps_cmd(ctx, opponent: discord.Member):
    options = ["камень", "ножницы", "бумага"]
    embed = discord.Embed(
        title=f"{EMOJIS['rps']} Камень, Ножницы, Бумага",
        description=f"{ctx.author.mention} против {opponent.mention}! Выберите: 'камень', 'ножницы' или 'бумага'.",
        color=COLORS["purple"]
    )
    await ctx.send(embed=embed)
    def check(m):
        return m.author in [ctx.author, opponent] and m.content.lower() in options

    try:
        player_msg = await bot.wait_for("message", check=check, timeout=30)
        opp_msg = await bot.wait_for("message", check=check, timeout=30)
        player_choice = player_msg.content.lower()
        opp_choice = opp_msg.content.lower()

        if player_choice == opp_choice:
            result = "🤝 Ничья!"
        elif (player_choice == "камень" and opp_choice == "ножницы") or \
             (player_choice == "ножницы" and opp_choice == "бумага") or \
             (player_choice == "бумага" and opp_choice == "камень"):
            result = f"🎉 {ctx.author.mention} победил!"
        else:
            result = f"🎉 {opponent.mention} победил!"
        embed = discord.Embed(
            title=f"{EMOJIS['rps']} Результат",
            description=f"{ctx.author.mention} выбрал {player_choice}, {opponent.mention} выбрал {opp_choice}. {result}",
            color=COLORS["purple"]
        )
        await ctx.send(embed=embed)
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="⏳ Тайм-аут",
            description="Время истекло! Игра отменена.",
            color=COLORS["error"]
        )
        await ctx.send(embed=embed)

@bot.command(name="blackjack")
async def blackjack_cmd(ctx, opponent: discord.Member, bet: int):
    if bet <= 0:
        embed = discord.Embed(
            title="❌ Ошибка",
            description="Ставка должна быть положительной!",
            color=COLORS["error"]
        )
        await ctx.send(embed=embed)
        return
    _, gold, _, _, _, _, _, _, _ = get_user_data(ctx.author.id)
    _, opp_gold, _, _, _, _, _, _, _ = get_user_data(opponent.id)
    if gold < bet or opp_gold < bet:
        embed = discord.Embed(
            title="❌ Ошибка",
            description="У одного из игроков недостаточно золотых монет!",
            color=COLORS["error"]
        )
        await ctx.send(embed=embed)
        return

    def draw_card():
        return random.choice([2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11])

    def hand_value(hand):
        value = sum(hand)
        ace_count = hand.count(11)
        while value > 21 and ace_count:
            value -= 10
            ace_count -= 1
        return value

    player_hand = [draw_card(), draw_card()]
    opp_hand = [draw_card(), draw_card()]
    player_value = hand_value(player_hand)
    opp_value = hand_value(opp_hand)

    if player_value == 21 and opp_value != 21:
        update_user_data(ctx.author.id, gold=bet)
        update_user_data(opponent.id, gold=-bet)
        embed = discord.Embed(
            title=f"{EMOJIS['blackjack']} Блэкджек",
            description=f"{ctx.author.mention} выиграл с Blackjack! ({player_hand} = {player_value}) против {opp_hand} = {opp_value}. +{bet} {EMOJIS['gold']}!",
            color=COLORS["success"]
        )
        await ctx.send(embed=embed)
        return
    elif opp_value == 21 and player_value != 21:
        update_user_data(ctx.author.id, gold=-bet)
        update_user_data(opponent.id, gold=bet)
        embed = discord.Embed(
            title=f"{EMOJIS['blackjack']} Блэкджек",
            description=f"{opponent.mention} выиграл с Blackjack! ({opp_hand} = {opp_value}) против {player_hand} = {player_value}. +{bet} {EMOJIS['gold']}!",
            color=COLORS["success"]
        )
        await ctx.send(embed=embed)
        return
    elif player_value == 21 and opp_value == 21:
        embed = discord.Embed(
            title=f"{EMOJIS['blackjack']} Блэкджек",
            description=f"Ничья с Blackjack! ({player_hand} = {player_value}) против ({opp_hand} = {opp_value}).",
            color=COLORS["grey"]
        )
        await ctx.send(embed=embed)
        return

    embed = discord.Embed(
        title=f"{EMOJIS['blackjack']} Блэкджек",
        description=f"{ctx.author.mention}, ваша рука: {player_hand} (сумма: {player_value}). Напишите 'hit' или 'stand'.\n{opponent.mention}, ваша рука: {opp_hand} (сумма: {opp_value}). Напишите 'hit' или 'stand'.",
        color=COLORS["purple"]
    )
    await ctx.send(embed=embed)

    def check(m):
        return m.author in [ctx.author, opponent] and m.content.lower() in ["hit", "stand"]

    player_done = False
    opp_done = False
    while not (player_done and opp_done):
        try:
            msg = await bot.wait_for("message", check=check, timeout=30)
            if msg.author == ctx.author and not player_done:
                if msg.content.lower() == "hit":
                    player_hand.append(draw_card())
                    player_value = hand_value(player_hand)
                    embed = discord.Embed(
                        title=f"{EMOJIS['blackjack']} Блэкджек",
                        description=f"{ctx.author.mention}, ваша рука: {player_hand} (сумма: {player_value}).",
                        color=COLORS["purple"]
                    )
                    await ctx.send(embed=embed)
                else:
                    player_done = True
                if player_value > 21:
                    update_user_data(ctx.author.id, gold=-bet)
                    update_user_data(opponent.id, gold=bet)
                    embed = discord.Embed(
                        title="💥 Перебор",
                        description=f"{ctx.author.mention} перебор ({player_value})! {opponent.mention} выиграл {bet} {EMOJIS['gold']}!",
                        color=COLORS["error"]
                    )
                    await ctx.send(embed=embed)
                    return
            elif msg.author == opponent and not opp_done:
                if msg.content.lower() == "hit":
                    opp_hand.append(draw_card())
                    opp_value = hand_value(opp_hand)
                    embed = discord.Embed(
                        title=f"{EMOJIS['blackjack']} Блэкджек",
                        description=f"{opponent.mention}, ваша рука: {opp_hand} (сумма: {opp_value}).",
                        color=COLORS["purple"]
                    )
                    await ctx.send(embed=embed)
                else:
                    opp_done = True
                if opp_value > 21:
                    update_user_data(ctx.author.id, gold=bet)
                    update_user_data(opponent.id, gold=-bet)
                    embed = discord.Embed(
                        title="💥 Перебор",
                        description=f"{opponent.mention} перебор ({opp_value})! {ctx.author.mention} выиграл {bet} {EMOJIS['gold']}!",
                        color=COLORS["error"]
                    )
                    await ctx.send(embed=embed)
                    return
        except asyncio.TimeoutError:
            embed = discord.Embed(
                title="⏳ Тайм-аут",
                description="Время истекло! Ничья.",
                color=COLORS["error"]
            )
            await ctx.send(embed=embed)
            return

    if player_value > opp_value:
        update_user_data(ctx.author.id, gold=bet)
        update_user_data(opponent.id, gold=-bet)
        embed = discord.Embed(
            title="🏆 Победа",
            description=f"{ctx.author.mention} выиграл ({player_value}) против ({opp_value})! +{bet} {EMOJIS['gold']}!",
            color=COLORS["success"]
        )
        await ctx.send(embed=embed)
    elif opp_value > player_value:
        update_user_data(ctx.author.id, gold=-bet)
        update_user_data(opponent.id, gold=bet)
        embed = discord.Embed(
            title="🏆 Победа",
            description=f"{opponent.mention} выиграл ({opp_value}) против ({player_value})! +{bet} {EMOJIS['gold']}!",
            color=COLORS["success"]
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="⚖️ Ничья",
            description=f"Ничья ({player_value}) против ({opp_value}).",
            color=COLORS["grey"]
        )
        await ctx.send(embed=embed)

@bot.command(name="cooldowns")
async def cooldowns_cmd(ctx):
    _, _, _, _, _, _, last_mine, last_work, last_profit = get_user_data(ctx.author.id)
    now = datetime.utcnow()
    cooldowns = []
    
    if last_mine:
        remaining = int(COOLDOWNS["mine"] - (now - datetime.fromisoformat(last_mine)).total_seconds())
        if remaining > 0:
            minutes = remaining // 60
            seconds = remaining % 60
            cooldowns.append(f"{EMOJIS['mine']} Добыча: {minutes} мин {seconds} сек")

    if last_work:
        remaining = int(COOLDOWNS["work"] - (now - datetime.fromisoformat(last_work)).total_seconds())
        if remaining > 0:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            cooldowns.append(f"{EMOJIS['work']} Работа: {hours} ч {minutes} мин")

    if last_profit:
        remaining = int(COOLDOWNS["profit"] - (now - datetime.fromisoformat(last_profit)).total_seconds())
        if remaining > 0:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            cooldowns.append(f"{EMOJIS['profit']} Прибыль: {hours} ч {minutes} мин")

    if last_daily and (now - datetime.fromisoformat(last_daily)).days < 1:
        remaining = int(COOLDOWNS["daily"] - (now - datetime.fromisoformat(last_daily)).total_seconds())
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        cooldowns.append(f"{EMOJIS['daily']} Ежедневка: {hours} ч {minutes} мин")

    if cooldowns:
        embed = discord.Embed(
            title=f"{EMOJIS['cooldowns']} Кулдауны",
            description="\n".join(cooldowns),
            color=COLORS["error"]
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="✅ Кулдауны",
            description=f"{ctx.author.mention}, все действия доступны!",
            color=COLORS["success"]
        )
        await ctx.send(embed=embed)

@bot.command(name="transfer")
async def transfer_cmd(ctx, member: discord.Member, currency: str, amount: int):
    if amount <= 0:
        embed = discord.Embed(
            title="❌ Ошибка",
            description="Укажите положительное количество!",
            color=COLORS["error"]
        )
        await ctx.send(embed=embed)
        return
    _, gold, _, _, crystals, _, _, _, _ = get_user_data(ctx.author.id)
    if currency.lower() == "gold" and gold >= amount:
        update_user_data(ctx.author.id, gold=-amount)
        update_user_data(member.id, gold=amount)
        embed = discord.Embed(
            title=f"{EMOJIS['transfer']} Передача",
            description=f"{ctx.author.mention} передал {amount} {EMOJIS['gold']} {member.mention}!",
            color=COLORS["gold"]
        )
        await ctx.send(embed=embed)
    elif currency.lower() == "crystals" and crystals >= amount:
        update_user_data(ctx.author.id, crystals=-amount)
        update_user_data(member.id, crystals=amount)
        embed = discord.Embed(
            title="💎 Передача",
            description=f"{ctx.author.mention} передал {amount} {EMOJIS['crystals']} {member.mention}!",
            color=COLORS["blue"]
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Ошибка",
            description=f"Недостаточно {currency} или неверная валюта! Используйте 'gold' или 'crystals'.",
            color=COLORS["error"]
        )
        await ctx.send(embed=embed)

@bot.command(name="give")
@commands.has_permissions(administrator=True)
async def give_cmd(ctx, member: discord.Member, currency: str, amount: int):
    if amount <= 0:
        embed = discord.Embed(
            title="❌ Ошибка",
            description="Укажите положительное количество!",
            color=COLORS["error"]
        )
        await ctx.send(embed=embed)
        return
    if currency.lower() == "gold":
        update_user_data(member.id, gold=amount)
        embed = discord.Embed(
            title=f"{EMOJIS['give']} Выдача",
            description=f"Админ {ctx.author.mention} выдал {amount} {EMOJIS['gold']} {member.mention}!",
            color=COLORS["gold"]
        )
        await ctx.send(embed=embed)
    elif currency.lower() == "crystals":
        update_user_data(member.id, crystals=amount)
        embed = discord.Embed(
            title="💎 Выдача",
            description=f"Админ {ctx.author.mention} выдал {amount} {EMOJIS['crystals']} {member.mention}!",
            color=COLORS["blue"]
        )
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Ошибка",
            description="Неверная валюта! Используйте 'gold' или 'crystals'.",
            color=COLORS["error"]
        )
        await ctx.send(embed=embed)

@bot.command(name="buyrole")
async def buyrole_cmd(ctx):
    embed = discord.Embed(
        title=f"{EMOJIS['buyrole']} Магазин ролей",
        description=f"Выберите роль для покупки, {ctx.author.mention}",
        color=COLORS["gold"]
    )
    for role_id, price in ROLES_CONFIG.items():
        role = discord.utils.get(ctx.guild.roles, id=int(role_id))
        if role:
            embed.add_field(name=f"{role.name}", value=f"Цена: {price} {EMOJIS['gold']}", inline=True)
    embed.set_thumbnail(url="https://i.imgur.com/8pZqL7G.jpeg")  # Изображение монетки
    await ctx.send(embed=embed, view=RoleShopView())

async def buy_role(user, role_id, interaction):
    role = discord.utils.get(interaction.guild.roles, id=int(role_id))
    if not role or "staff" in role.name.lower():
        await interaction.response.send_message(embed=discord.Embed(
            title="❌ Ошибка",
            description="Эта роль недоступна для покупки!",
            color=COLORS["error"]
        ), ephemeral=True)
        return
    price = ROLES_CONFIG.get(role_id, 0)
    _, gold, _, _, _, _, _, _, _ = get_user_data(user.id)
    if gold < price:
        await interaction.response.send_message(embed=discord.Embed(
            title="❌ Ошибка",
            description=f"Недостаточно золотых монет! Нужно: {price} {EMOJIS['gold']}",
            color=COLORS["error"]
        ), ephemeral=True)
        return
    update_user_data(user.id, gold=-price)
    await user.add_roles(role)
    embed = discord.Embed(
        title="✅ Покупка роли",
        description=f"Вы купили роль {role.name} за {price} {EMOJIS['gold']}!",
        color=COLORS["success"]
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.command(name="set_role_price")
@commands.has_permissions(administrator=True)
async def set_role_price_cmd(ctx, role: discord.Role, price: int):
    if price < 0:
        embed = discord.Embed(
            title="❌ Ошибка",
            description="Цена не может быть отрицательной!",
            color=COLORS["error"]
        )
        await ctx.send(embed=embed)
        return
    ROLES_CONFIG[str(role.id)] = price
    with open("config.json", "w") as file:
        json.dump({"TOKEN": TOKEN, "PREFIX": PREFIX, "roles": ROLES_CONFIG, "welcome_channel": WELCOME_CHANNEL, "roles_channel": ROLES_CHANNEL, "admin_channel": ADMIN_CHANNEL}, file, indent=4)
    embed = discord.Embed(
        title="⚙ Настройка",
        description=f"Цена роли {role.name} установлена в {price} {EMOJIS['gold']}!",
        color=COLORS["success"]
    )
    await ctx.send(embed=embed)

@bot.command(name="toggle_role_sale")
@commands.has_permissions(administrator=True)
async def toggle_role_sale_cmd(ctx, role: discord.Role):
    role_id = str(role.id)
    if "staff" in role.name.lower():
        embed = discord.Embed(
            title="❌ Ошибка",
            description="Роли Staff нельзя продавать!",
            color=COLORS["error"]
        )
        await ctx.send(embed=embed)
        return
    if role_id in ROLES_CONFIG:
        del ROLES_CONFIG[role_id]
        status = "удалена из продажи"
    else:
        ROLES_CONFIG[role_id] = 50  # Значение по умолчанию
        status = "добавлена в продажу с ценой 50 🪙"
    with open("config.json", "w") as file:
        json.dump({"TOKEN": TOKEN, "PREFIX": PREFIX, "roles": ROLES_CONFIG, "welcome_channel": WELCOME_CHANNEL, "roles_channel": ROLES_CHANNEL, "admin_channel": ADMIN_CHANNEL}, file, indent=4)
    embed = discord.Embed(
        title="⚙ Настройка",
        description=f"Роль {role.name} {status}!",
        color=COLORS["success"]
    )
    await ctx.send(embed=embed)

@bot.command(name="admin_message")
@commands.has_permissions(administrator=True)
async def admin_message_cmd(ctx):
    embed = discord.Embed(
        title="📩 Отправка сообщения от лица бота",
        description="Введите текст сообщения для отправки в канал #admin-chat:",
        color=COLORS["purple"]
    )
    await ctx.send(embed=embed, view=AdminMessageView())

async def admin_message(user, interaction):
    await interaction.response.send_modal(
        title="📩 Введите сообщение",
        custom_id="admin_message_modal",
        components=[
            discord.ui.TextInput(
                label="Текст сообщения",
                style=discord.TextInputStyle.paragraph,
                custom_id="message_content",
                placeholder="Напишите текст для отправки...",
                required=True
            )
        ]
    )
    try:
        modal_interaction = await bot.wait_for("modal_submit", check=lambda i: i.custom_id == "admin_message_modal" and i.user == user, timeout=300)
        message_content = modal_interaction.components[0].value
        channel = discord.utils.get(interaction.guild.text_channels, name=ADMIN_CHANNEL.replace("#", "").replace("-", "").lower())
        if channel:
            embed = discord.Embed(
                title="📢 Сообщение от администрации",
                description=message_content,
                color=COLORS["purple"]
            )
            embed.set_footer(text=f"Отправлено от {user.name}", icon_url=user.avatar.url if user.avatar else None)
            await channel.send(embed=embed)
            await modal_interaction.response.send_message(embed=discord.Embed(
                title="✅ Сообщение отправлено",
                description="Ваше сообщение успешно отправлено в канал #admin-chat!",
                color=COLORS["success"]
            ), ephemeral=True)
        else:
            await modal_interaction.response.send_message(embed=discord.Embed(
                title="❌ Ошибка",
                description="Канал #admin-chat не найден!",
                color=COLORS["error"]
            ), ephemeral=True)
    except asyncio.TimeoutError:
        await interaction.followup.send(embed=discord.Embed(
            title="⏳ Тайм-аут",
            description="Время на ввод истекло!",
            color=COLORS["error"]
        ), ephemeral=True)

@bot.event
async def on_ready():
    logger.info(f"Бот {bot.user} запущен!")
    print(f"✅ Бот {bot.user} запущен!")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="за тобой в шахте!"))

    # Создание меню ролей в канале #roles
    roles_channel = discord.utils.get(bot.get_all_channels(), name=ROLES_CHANNEL.replace("#", "").replace("-", "").lower())
    if roles_channel:
        embed = discord.Embed(
            title="🏷 Магазин ролей",
            description="Реагируйте на эмодзи, чтобы купить роли (цена указана в 🪙):",
            color=COLORS["gold"]
        )
        for role_id, price in ROLES_CONFIG.items():
            role = discord.utils.get(bot.get_guild(0).roles, id=int(role_id))
            if role:
                embed.add_field(name=f"{role.name}", value=f"Цена: {price} {EMOJIS['gold']}", inline=True)
        embed.set_image(url="https://i.imgur.com/8pZqL7G.jpeg")  # Красивая картинка
        message = await roles_channel.send(embed=embed, view=RoleShopView())
        await message.pin()

@tasks.loop(minutes=1)
async def track_voice_activity():
    for member_id in list(voice_activity.keys()):
        update_user_data(member_id, gold=1)