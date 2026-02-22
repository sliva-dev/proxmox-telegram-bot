from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, filters

from handlers.common import start, status
from handlers.console import console
from handlers.resources import vm_list_cmd, lxc_list_cmd, vm_callback, lxc_callback
from handlers.terminal import handle_terminal_input

HANDLERS = [
    CommandHandler(["start", "help"], start),
    CommandHandler("status", status),
    CommandHandler("vm", vm_list_cmd),
    CommandHandler("lxc", lxc_list_cmd),
    CommandHandler("console", console),
    CallbackQueryHandler(vm_callback, pattern=r"^vm_"),
    CallbackQueryHandler(lxc_callback, pattern=r"^lxc_"),
    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_terminal_input),
]
