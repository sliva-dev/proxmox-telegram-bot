from telegram import Update
from telegram.ext import ContextTypes
import logging
import html
from functools import wraps
from config import TELEGRAM

logger = logging.getLogger(__name__)


def require_auth(func):
    """Декоратор для проверки прав доступа. Если прав нет — пишет лог и админу."""

    @wraps(func)
    async def wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ) -> None:
        user = update.effective_user

        if not user:
            return None

        whitelist = TELEGRAM.whitelist

        if user.id in whitelist:
            return await func(update, context, *args, **kwargs)

        first_name = html.escape(user.first_name) if user.first_name else "Без имени"
        user_info = f"ID: {user.id}, Имя: {first_name}"
        if user.username:
            user_info += f", @{html.escape(user.username)}"

        command = update.message.text if update.message else "callback"

        logger.warning(
            f"Неавторизованный доступ заблокирован! {user_info} | Запрос: {command}"
        )

        for admin_id in whitelist:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📋 Лог — неавторизованный доступ\n"
                    f"Пользователь: {user_info}\n"
                    f"Запрос: {command}",
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")

        return None

    return wrapper
