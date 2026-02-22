import asyncio
import logging
from textwrap import dedent

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.auth import require_auth
from system.sensors import get_status

logger = logging.getLogger(__name__)


@require_auth
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = dedent(
        """\
        Привет! Это бот для управления <b>Proxmox VE</b>.

        <b>Команды:</b>
        /status - Состояние хоста
        /vm - Список VM
        /lxc - Список LXC
        /console &lt;cmd&gt; - Выполнить команду
    """
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


@require_auth
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, get_status)

        await update.message.reply_text(
            f"📊 <b>Статус хоста:</b>\n{info}", parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.exception("Ошибка при получении статуса хоста:")
        await update.message.reply_text(
            "❌ Произошла ошибка при получении статуса хоста. Подробности в логах сервера."
        )
