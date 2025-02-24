import sqlite3
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

conn = sqlite3.connect('bot_data.db')
cursor = conn.cursor()

# Создание таблиц
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
        inventory TEXT DEFAULT '[]'
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
conn.commit()

def get_user_data(user_id):
    try:
        cursor.execute('SELECT xp, gold, last_daily, inventory, crystals, daily_streak, last_mine, last_work, last_profit FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone() or (0, 0, None, '[]', 0, 0, None, None, None)
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных в get_user_data: {e}")
        return (0, 0, None, '[]', 0, 0, None, None, None)

def update_user_data(user_id, xp=None, gold=None, last_daily=None, inventory=None, crystals=None, daily_streak=None, last_mine=None, last_work=None, last_profit=None):
    try:
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
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных в update_user_data: {e}")

def get_gear(user_id):
    try:
        cursor.execute('SELECT pickaxe_level, helmet_level, gloves_level, boots_level FROM gear WHERE user_id = ?', (user_id,))
        return cursor.fetchone() or (0, 0, 0, 0)
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных в get_gear: {e}")
        return (0, 0, 0, 0)

def update_gear(user_id, pickaxe_level=None, helmet_level=None, gloves_level=None, boots_level=None):
    try:
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
    except sqlite3.Error as e:
        logger.error(f"Ошибка базы данных в update_gear: {e}")