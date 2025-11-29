import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
import nest_asyncio
from telegram import Update
from telegram.ext import Application
from bot_handlers import HANDLERS
from alerts import AlertManager
from config import TELEGRAM

nest_asyncio.apply()

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    file_handler = RotatingFileHandler(
        'bot.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

setup_logging()
logger = logging.getLogger(__name__)

async def main():
    logger.info("Запуск бота...")
    logger.debug(f"Python version: {sys.version}")

    if not TELEGRAM['BOT_TOKEN']:
        raise ValueError("BOT_TOKEN не настроен в .env")
    if not TELEGRAM['WHITELIST']:
        raise ValueError("WHITELIST пуст в .env")

    try:
        application = Application.builder().token(TELEGRAM['BOT_TOKEN']).build()

        for handler in HANDLERS:
            application.add_handler(handler)

        alert_manager = AlertManager(application)

        await alert_manager.start()

        logger.info("Бот запущен!")

        try:
            await application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
        except Exception as e:
            logger.error(f"Ошибка при запуске polling: {e}")
        finally:
            # Graceful shutdown
            await alert_manager.stop()

    except Exception as e:
        logger.error(f"Критическая ошибка при запуске: {e}")
        raise

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)
