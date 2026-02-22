import logging
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from proxmox.vms import get_vm_list, vm_action
from proxmox.lxcs import get_lxc_list, lxc_action
from proxmox.utils import format_uptime
from core.auth import require_auth

logger = logging.getLogger(__name__)


class ResourceHandler:
    def __init__(self, resource_type: str):
        self.resource_type = resource_type
        self.get_list_func = get_vm_list if resource_type == "vm" else get_lxc_list
        self.action_func = vm_action if resource_type == "vm" else lxc_action
        self.resource_name_ru = "VM" if resource_type == "vm" else "LXC"

    def _get_status_display(self, status: str):
        status_emoji = "🟢" if status == "running" else "🔴"
        if self.resource_type == "vm":
            status_text = "Запущена" if status == "running" else "Остановлена"
        else:
            status_text = "Запущен" if status == "running" else "Остановлен"
        return status_emoji, status_text

    def _get_resource_by_id(self, resources: list, resource_id: str):
        return next((r for r in resources if r["id"] == int(resource_id)), None)

    async def _fetch_resources_async(self):
        return await asyncio.to_thread(self.get_list_func)

    async def _run_action_async(self, resource_id, action, node):
        return await asyncio.to_thread(self.action_func, resource_id, action, node=node)

    async def handle_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            resources = await self._fetch_resources_async()
            if not resources:
                await update.message.reply_text(f"{self.resource_name_ru} не найдены.")
                return

            keyboard = self._build_list_keyboard(resources)
            await update.message.reply_text(
                f"Выбери {self.resource_name_ru}:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as e:
            logger.error(f"Ошибка получения списка {self.resource_type}: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def _enable_console_mode(self, update, context, resource_id, node):
        context.user_data["active_console"] = {
            "type": self.resource_type,
            "id": resource_id,
            "node": node,
        }
        await update.callback_query.message.reply_text(
            f"💻 **Вход в терминал {self.resource_name_ru} {resource_id}**\n\n"
            "Все твои следующие сообщения будут отправляться как команды.\n"
            "Для выхода напиши `exit`.",
            parse_mode="Markdown",
        )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data

        try:
            if data == f"{self.resource_type}_refresh":
                await self._refresh_list(query)
                return

            parts = data.split(":")
            action_type = parts[0]

            if action_type == f"{self.resource_type}_select" and len(parts) == 3:
                await self._show_resource_details(query, parts[1], parts[2])
            elif action_type == f"{self.resource_type}_action" and len(parts) == 4:
                await self._handle_resource_action(query, parts[1], parts[2], parts[3])
            elif action_type == f"{self.resource_type}_confirm" and len(parts) == 4:
                await self._handle_confirmed_action(query, parts[1], parts[2], parts[3])
            elif action_type == f"{self.resource_type}_console" and len(parts) == 3:
                await self._enable_console_mode(update, context, parts[1], parts[2])

        except Exception as e:
            logger.error(f"Ошибка обработки callback {data}: {e}")
            await query.edit_message_text(f"❌ Ошибка обработки: {str(e)}")

    def _build_list_keyboard(self, resources):
        keyboard = []
        sorted_resources = sorted(resources, key=lambda x: x["id"])

        for resource in sorted_resources:
            status_emoji, status_text = self._get_status_display(resource["status"])
            btn_text = (
                f"{resource['id']} {resource['name']} {status_emoji}{status_text}"
            )
            callback_data = (
                f"{self.resource_type}_select:{resource['id']}:{resource['node']}"
            )

            keyboard.append(
                [InlineKeyboardButton(btn_text, callback_data=callback_data)]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "Обновить", callback_data=f"{self.resource_type}_refresh"
                )
            ]
        )
        return keyboard

    async def _refresh_list(self, query):
        resources = await self._fetch_resources_async()
        if not resources:
            await query.edit_message_text(f"{self.resource_name_ru} не найдены.")
            return

        keyboard = self._build_list_keyboard(resources)
        await query.edit_message_text(
            f"Выбери {self.resource_name_ru}:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _show_resource_details(self, query, resource_id, node):
        resources = await self._fetch_resources_async()
        resource_info = self._get_resource_by_id(resources, resource_id)

        if not resource_info:
            await query.edit_message_text(
                f"{self.resource_name_ru} {resource_id} не найдена."
            )
            return

        details_text = self._format_resource_details(resource_info)
        keyboard = self._build_details_keyboard(resource_id, node)
        await query.edit_message_text(
            details_text, reply_markup=InlineKeyboardMarkup(keyboard)
        )

    def _format_resource_details(self, resource):
        status_emoji, status_text = self._get_status_display(resource["status"])
        uptime_str = format_uptime(resource["uptime"])

        disk_info = ""
        if resource.get("disk_total_gb", 0) > 0 and resource.get("disk_used_gb", 0) > 0:
            disk_info = f"💾 Диск: {resource['disk_used_gb']:.1f} / {resource['disk_total_gb']:.1f} ГБ\n"
        elif resource.get("disk_total_gb", 0) > 0:
            disk_info = f"💾 Диск: {resource['disk_total_gb']:.1f} ГБ\n"

        details = f"""📋 Детали {self.resource_name_ru} {resource['id']} ({resource['name']})
🖥️ Узел: {resource['node']}
{status_emoji} Статус: {status_text}
⏳ Аптайм: {uptime_str}

📈 Метрики:
💻 CPU: {resource['cpu_usage_percent']:.1f}%
🧠 RAM: {resource['mem_used_mb']:.0f} / {resource['mem_total_mb']:.0f} MB ({resource['mem_usage_percent']:.1f}%)
{disk_info}"""

        return details.strip()

    def _build_details_keyboard(self, resource_id, node):
        return [
            [
                InlineKeyboardButton(
                    "▶️ Запустить",
                    callback_data=f"{self.resource_type}_confirm:start:{resource_id}:{node}",
                )
            ],
            [
                InlineKeyboardButton(
                    "⏹️ Остановить",
                    callback_data=f"{self.resource_type}_confirm:stop:{resource_id}:{node}",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Перезагрузить",
                    callback_data=f"{self.resource_type}_confirm:reboot:{resource_id}:{node}",
                )
            ],
            [
                InlineKeyboardButton(
                    "💻 Консоль",
                    callback_data=f"{self.resource_type}_console:{resource_id}:{node}",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Обновить детали",
                    callback_data=f"{self.resource_type}_select:{resource_id}:{node}",
                )
            ],
            [
                InlineKeyboardButton(
                    "Назад к списку", callback_data=f"{self.resource_type}_refresh"
                )
            ],
        ]

    async def _handle_confirmed_action(self, query, action, resource_id, node):
        action_text = {
            "start": "запуск",
            "stop": "остановку",
            "reboot": "перезагрузку",
        }.get(action, action)

        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Да",
                    callback_data=f"{self.resource_type}_action:{action}:{resource_id}:{node}",
                ),
                InlineKeyboardButton(
                    "❌ Отмена",
                    callback_data=f"{self.resource_type}_select:{resource_id}:{node}",
                ),
            ]
        ]

        await query.edit_message_text(
            f"⚠️ Точно выполнить {action_text} {self.resource_name_ru} {resource_id}?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _handle_resource_action(self, query, action, resource_id, node):
        await query.edit_message_text(
            f"⏳ Выполняю {action} для {self.resource_name_ru} {resource_id}..."
        )

        try:
            result = await self._run_action_async(resource_id, action, node)

            target_status = "running" if action in ["start", "reboot"] else "stopped"
            max_attempts = 5

            for _ in range(max_attempts):
                await asyncio.sleep(2)
                resources = await self._fetch_resources_async()
                res = self._get_resource_by_id(resources, resource_id)
                if res and res["status"] == target_status:
                    break

            await self._refresh_after_action(query, resource_id, node, result)
        except Exception as e:
            await self._handle_action_error(query, str(e))

    async def _refresh_after_action(self, query, resource_id, node, result_message):
        resources = await self._fetch_resources_async()
        resource_info = self._get_resource_by_id(resources, resource_id)

        if resource_info:
            details_text = self._format_resource_details(resource_info)
            keyboard = self._build_details_keyboard(resource_id, node)
            await query.edit_message_text(
                details_text, reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(f"✅ Действие выполнено. {result_message}")

    async def _handle_action_error(self, query, error_msg):
        error_lower = error_msg.lower()

        if any(
            phrase in error_lower
            for phrase in ["already running", "ct already running"]
        ):
            await query.edit_message_text(f"❌ {self.resource_name_ru} уже запущен")
        elif any(phrase in error_lower for phrase in ["is not running", "not running"]):
            await query.edit_message_text(f"❌ {self.resource_name_ru} уже остановлен")
        elif "500 internal server error" in error_lower:
            await query.edit_message_text(
                "❌ Ошибка сервера Proxmox (500 Internal Server Error)"
            )
        else:
            await query.edit_message_text(f"❌ Ошибка: {error_msg}")


vm_handler = ResourceHandler("vm")
lxc_handler = ResourceHandler("lxc")


@require_auth
async def vm_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await vm_handler.handle_list(update, context)


@require_auth
async def lxc_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await lxc_handler.handle_list(update, context)


@require_auth
async def vm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await vm_handler.handle_callback(update, context)


@require_auth
async def lxc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await lxc_handler.handle_callback(update, context)
