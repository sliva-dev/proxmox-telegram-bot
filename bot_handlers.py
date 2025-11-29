from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from config import TELEGRAM
from system_utils import get_status
from unified_handlers import vm_list_cmd, lxc_list_cmd, vm_callback, lxc_callback
from auth import is_authorized, notify_unauthorized_access
import re
import subprocess
import logging

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await notify_unauthorized_access(update, context)
        return
    help_text = """
Привет! Это бот для управления Proxmox VE.

Команды:
/status - Состояние хоста (темп и 4 основных диска)
/vm - Список VM (кнопки)
/lxc - Список LXC (кнопки)
/console <cmd> - Выполнить команду
    """
    await update.message.reply_text(help_text)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await notify_unauthorized_access(update, context)
        return
    try:
        info = get_status()
        await update.message.reply_text(f"📊 Статус хоста:\n{info}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# -------- console --------
DANGEROUS_PATTERNS = [
    r'\brm\s+-rf\s+/\b',      # rm -rf /
    r'\bmkfs\b',              # mkfs
    r'\bdd\s+if=.*\s+of=/dev/', # dd с дисками
    r'\bunmount\b',           # unmount
    r'\bmount\s+.*\s+/dev/',  # mount устройств
    r'\bfdisk\b',             # fdisk
    r'\bparted\b',            # parted
    r'\bwipefs\b',            # wipefs
    r'\bshutdown\b',          # shutdown
    r'\bhalt\b',              # halt
    r'\bpoweroff\b',          # poweroff
    r'\breboot\b',            # reboot
    r'^\s*:\s*\(\s*\)\s*{\s*:.*}\s*;\s*$', # fork bomb
]

def validate_command(cmd: str) -> bool:
    """Проверить команду на безопасность"""
    cmd_lower = cmd.lower().strip()

    # Проверяем черный список
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_lower):
            return False

    return True

async def console(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await notify_unauthorized_access(update, context)
        return
    if not context.args:
        await update.message.reply_text("Укажите команду: /console <cmd>")
        return

    cmd = ' '.join(context.args)
    if not validate_command(cmd):
        await update.message.reply_text("❌ Команда содержит недопустимые символы или запрещена.")
        return

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            executable='/bin/bash'
        )

        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR: {result.stderr}"

        if not output.strip():
            output = "Команда выполнена без вывода."

        if len(output) > 4000:
            output = output[:4000] + "\n... (вывод обрезан)"

        await update.message.reply_text(f"```\n{output}\n```", parse_mode='Markdown')

    except subprocess.TimeoutExpired:
        await update.message.reply_text("❌ Таймаут: команда выполняется слишком долго.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка выполнения: {str(e)}")

# Хендлеры
HANDLERS = [
    CommandHandler("start", start),
    CommandHandler("help", start),
    CommandHandler("status", status),
    CommandHandler("vm", vm_list_cmd),
    CommandHandler("lxc", lxc_list_cmd),
    CommandHandler("console", console),
    CallbackQueryHandler(vm_callback, pattern=r'^(vm_).*'),
    CallbackQueryHandler(lxc_callback, pattern=r'^(lxc_).*'),
]
