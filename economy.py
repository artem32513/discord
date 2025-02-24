from datetime import datetime
import random

COOLDOWNS = {
    "mine": 300,  # 5 минут
    "work": 3600,  # 1 час
    "profit": 14400,  # 4 часа
    "daily": 86400  # 24 часа
}
GEAR_BONUS_PER_LEVEL = 0.05  # +5% за уровень

def get_gear_cost(level):
    return int(50 * (1.5 ** level))  # Экспоненциальный рост

def check_cooldown(last_time, cooldown_seconds, action_name):
    now = datetime.utcnow()
    if last_time and (now - datetime.fromisoformat(last_time)).total_seconds() < cooldown_seconds:
        remaining = int(cooldown_seconds - (now - datetime.fromisoformat(last_time)).total_seconds())
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        seconds = remaining % 60
        return False, f"Подождите {hours} ч {minutes} мин {seconds} сек перед следующей попыткой {action_name}!"
    return True, None