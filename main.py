import logging
import sys

from telegram import Update
from telegram.ext import Application
from core.logger import setup_logging
from config import TELEGRAM
from handlers.routers import HANDLERS
from services.alerts import AlertManager

setup_logging()
logger = logging.getLogger(__name__)


async def post_init(application: Application):
    """Хук, который выполняется ДО начала поллинга."""
    logger.info("Запуск фоновых сервисов...")

    alert_manager = AlertManager(application)
    application.bot_data["alert_manager"] = alert_manager

    await alert_manager.start()


async def post_shutdown(application: Application):
    """Хук, который выполняется ПЕРЕД полной остановкой бота."""
    logger.info("Остановка фоновых сервисов...")
    alert_manager = application.bot_data.get("alert_manager")
    if alert_manager:
        await alert_manager.stop()


def main():
    logger.info("Сборка приложения...")
    logger.debug(f"Python version: {sys.version}")

    try:
        application = (
            Application.builder()
            .token(TELEGRAM.bot_token)
            .post_init(post_init)
            .post_shutdown(post_shutdown)
            .build()
        )

        application.bot_data["whitelist"] = TELEGRAM.whitelist

        for handler in HANDLERS:
            application.add_handler(handler)

        logger.info("Бот запущен! Ожидание обновлений...")

        application.run_polling(
            allowed_updates=Update.ALL_TYPES, drop_pending_updates=True
        )

    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Процесс остановлен пользователем.")
