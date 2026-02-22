import re
import asyncio
import html

from telegram import Update
from telegram.ext import ContextTypes
from core.auth import require_auth

DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\s+/\b",
    r"\bmkfs\b",
    r"\bdd\s+if=.*\s+of=/dev/",
    r"\bunmount\b",
    r"\bmount\s+.*\s+/dev/",
    r"\bfdisk\b",
    r"\bparted\b",
    r"\bwipefs\b",
    r"\bhalt\b",
    r"\bpoweroff\b",
    r"^\s*:\s*\(\s*\)\s*{\s*:.*}\s*;\s*$",
]


def validate_command(cmd: str) -> bool:
    cmd_lower = cmd.lower().strip()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_lower):
            return False
    return True


@require_auth
async def console(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Укажите команду: /console <cmd>")
        return

    cmd = " ".join(context.args)
    if not validate_command(cmd):
        await update.message.reply_text(
            "❌ Команда содержит недопустимые символы или запрещена."
        )
        return

    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            executable="/bin/bash",
        )

        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)

        output = stdout.decode("utf-8", errors="replace")
        err_output = stderr.decode("utf-8", errors="replace")

        if err_output:
            output += f"\nSTDERR: {err_output}"

        if not output.strip():
            output = "Команда выполнена без вывода."

        if len(output) > 4000:
            output = output[:4000] + "\n... (вывод обрезан)"

        safe_output = html.escape(output)

        await update.message.reply_text(
            f"<pre><code>{safe_output}</code></pre>", parse_mode="HTML"
        )

    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass

        await update.message.reply_text(
            "❌ Таймаут: команда выполняется слишком долго и была принудительно завершена."
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка выполнения: {html.escape(str(e))}", parse_mode="HTML"
        )
