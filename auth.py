from telegram import Update
from telegram.ext import ContextTypes
from config import TELEGRAM
import logging

logger = logging.getLogger(__name__)

def is_authorized(update: Update) -> bool:
    user_id = update.effective_user.id
    return user_id in TELEGRAM['WHITELIST']

async def notify_unauthorized_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Уведомляет админов о попытке доступа неавторизованного пользователя"""
    user = update.effective_user
    user_info = f"ID: {user.id}, Имя: {user.first_name}"
    if user.username:
        user_info += f", @{user.username}"

    command = update.message.text if update.message else "callback"

    # Отправляем уведомление всем в whitelist
    for admin_id in TELEGRAM['WHITELIST']:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"📋 Лог — неавторизованный доступ\n"
                     f"Пользователь: {user_info}\n"
                     f"Запрос: {command}"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")
