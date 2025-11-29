import re
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import TELEGRAM
from proxmox_utils import get_vm_list, get_lxc_list, vm_action, lxc_action, format_uptime
from auth import is_authorized, notify_unauthorized_access

logger = logging.getLogger(__name__)

class ResourceHandler:
    def __init__(self, resource_type: str):
        self.resource_type = resource_type  # 'vm' или 'lxc'
        self.get_list_func = get_vm_list if resource_type == 'vm' else get_lxc_list
        self.action_func = vm_action if resource_type == 'vm' else lxc_action
        self.resource_name_ru = "VM" if resource_type == 'vm' else "LXC"

    async def handle_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список ресурсов"""
        if not is_authorized(update):
            await notify_unauthorized_access(update, context)
            return

        try:
            resources = self.get_list_func()
            if not resources:
                await update.message.reply_text(f"{self.resource_name_ru} не найдены.")
                return

            keyboard = self._build_list_keyboard(resources)
            await update.message.reply_text(f"Выбери {self.resource_name_ru}:",
                                         reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.error(f"Ошибка получения списка {self.resource_type}: {e}")
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback-запросов"""
        query = update.callback_query
        await query.answer()

        if not is_authorized(update):
            await notify_unauthorized_access(update, context)
            return

        data = query.data
        try:
            if data == f"{self.resource_type}_refresh":
                await self._refresh_list(query)
            elif data.startswith(f"{self.resource_type}_select:"):
                await self._show_resource_details(query, data)
            elif data.startswith(f"{self.resource_type}_action:"):
                await self._handle_resource_action(query, data)
            elif data.startswith(f"{self.resource_type}_confirm:"):
                await self._handle_confirmed_action(query, data)
        except Exception as e:
            logger.error(f"Ошибка обработки callback {data}: {e}")
            await query.edit_message_text(f"❌ Ошибка обработки: {str(e)}")

    def _build_list_keyboard(self, resources):
        """Построить клавиатуру списка ресурсов"""
        keyboard = []
        sorted_resources = sorted(resources, key=lambda x: x['id'])

        for resource in sorted_resources:
            status_emoji = "🟢" if resource['status'] == 'running' else "🔴"
            status_text = "Запущен" if resource['status'] == 'running' else "Остановлен"
            if self.resource_type == 'vm':
                status_text = "Запущена" if resource['status'] == 'running' else "Остановлена"

            btn_text = f"{resource['id']} {resource['name']} {status_emoji}{status_text}"
            callback_data = f"{self.resource_type}_select:{resource['id']}:{resource['node']}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])

        keyboard.append([InlineKeyboardButton("Обновить", callback_data=f"{self.resource_type}_refresh")])
        return keyboard

    async def _refresh_list(self, query):
        """Обновить список ресурсов"""
        resources = self.get_list_func()
        if not resources:
            await query.edit_message_text(f"{self.resource_name_ru} не найдены.")
            return

        keyboard = self._build_list_keyboard(resources)
        await query.edit_message_text(f"Выбери {self.resource_name_ru}:",
                                    reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_resource_details(self, query, data):
        """Показать детали ресурса"""
        match = re.match(rf'^{self.resource_type}_select:(\d+):(.+)$', data)
        if not match:
            await query.edit_message_text("❌ Неверный формат данных")
            return

        resource_id = match.group(1)
        node = match.group(2)

        resources = self.get_list_func()
        resource_info = next((r for r in resources if r['id'] == int(resource_id)), None)

        if not resource_info:
            await query.edit_message_text(f"{self.resource_name_ru} {resource_id} не найдена.")
            return

        details_text = self._format_resource_details(resource_info)
        keyboard = self._build_details_keyboard(resource_id, node)
        await query.edit_message_text(details_text, reply_markup=InlineKeyboardMarkup(keyboard))

    def _format_resource_details(self, resource):
        """Форматировать детали ресурса"""
        status_emoji = "🟢" if resource['status'] == 'running' else "🔴"
        status_text = "Запущен" if resource['status'] == 'running' else "Остановлен"
        if self.resource_type == 'vm':
            status_text = "Запущена" if resource['status'] == 'running' else "Остановлена"

        uptime_str = format_uptime(resource['uptime'])

        # Форматируем информацию о диске (убираем 0.0)
        disk_info = ""
        if resource['disk_total_gb'] > 0 and resource['disk_used_gb'] > 0:
            disk_info = f"💾 Диск: {resource['disk_used_gb']:.1f} / {resource['disk_total_gb']:.1f} ГБ\n"
        elif resource['disk_total_gb'] > 0:
            disk_info = f"💾 Диск: {resource['disk_total_gb']:.1f} ГБ\n"
        # Если disk_total_gb == 0, то строка с диском не добавляется

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
        """Построить клавиатуру действий"""
        keyboard = [
            [InlineKeyboardButton("▶️ Запустить",
                               callback_data=f"{self.resource_type}_confirm:start:{resource_id}:{node}")],
            [InlineKeyboardButton("⏹️ Остановить",
                               callback_data=f"{self.resource_type}_confirm:stop:{resource_id}:{node}")],
            [InlineKeyboardButton("🔄 Перезагрузить",
                               callback_data=f"{self.resource_type}_confirm:reboot:{resource_id}:{node}")],
            [InlineKeyboardButton("🔄 Обновить детали",
                               callback_data=f"{self.resource_type}_select:{resource_id}:{node}")],
            [InlineKeyboardButton("Назад к списку",
                               callback_data=f"{self.resource_type}_refresh")]
        ]
        return keyboard

    async def _handle_resource_action(self, query, data):
        """Обработать действие с ресурсом (старая версия - для обратной совместимости)"""
        match = re.match(rf'^{self.resource_type}_action:(start|stop|reboot):(\d+):(.+)$', data)
        if not match:
            await query.edit_message_text("❌ Неверный формат действия")
            return

        action = match.group(1)
        resource_id = match.group(2)
        node = match.group(3)

        await query.edit_message_text(f"⏳ Выполняю {action} для {self.resource_name_ru} {resource_id}...")

        try:
            result = self.action_func(resource_id, action, node=node)

            # Ждем немного перед обновлением, чтобы Proxmox успел обновить статус
            await asyncio.sleep(2)

            # После действия автоматически обновляем детали
            await self._refresh_after_action(query, resource_id, node, result)
        except Exception as e:
            await self._handle_action_error(query, str(e))

    async def _handle_confirmed_action(self, query, data):
        """Обработать подтвержденное действие"""
        match = re.match(rf'^{self.resource_type}_confirm:(start|stop|reboot):(\d+):(.+)$', data)
        if not match:
            await query.edit_message_text("❌ Неверный формат действия")
            return

        action = match.group(1)
        resource_id = match.group(2)
        node = match.group(3)

        # Показать подтверждение
        action_text = {"start": "запуск", "stop": "остановку", "reboot": "перезагрузку"}[action]
        keyboard = [
            [
                InlineKeyboardButton("✅ Да",
                                   callback_data=f"{self.resource_type}_action:{action}:{resource_id}:{node}"),
                InlineKeyboardButton("❌ Отмена",
                                   callback_data=f"{self.resource_type}_select:{resource_id}:{node}")
            ]
        ]

        await query.edit_message_text(
            f"⚠️ Точно выполнить {action_text} {self.resource_name_ru} {resource_id}?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _refresh_after_action(self, query, resource_id, node, result_message):
        """Обновить детали после действия"""
        resources = self.get_list_func()
        resource_info = next((r for r in resources if r['id'] == int(resource_id)), None)

        if resource_info:
            details_text = self._format_resource_details(resource_info)
            keyboard = self._build_details_keyboard(resource_id, node)
            await query.edit_message_text(details_text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text(f"✅ {result_message}")

    def _handle_action_error(self, query, error_msg):
        """Обработать ошибку действия"""
        error_lower = error_msg.lower()

        if any(phrase in error_lower for phrase in ["already running", "ct already running"]):
            return query.edit_message_text(f"❌ {self.resource_name_ru} уже запущен")
        elif any(phrase in error_lower for phrase in ["is not running", "not running"]):
            return query.edit_message_text(f"❌ {self.resource_name_ru} уже остановлен")
        elif "500 Internal Server Error" in error_msg:
            return query.edit_message_text("❌ Ошибка сервера Proxmox")
        else:
            return query.edit_message_text(f"❌ Ошибка: {error_msg}")

# Создаем экземпляры обработчиков
vm_handler = ResourceHandler('vm')
lxc_handler = ResourceHandler('lxc')

# Функции для импорта
async def vm_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await vm_handler.handle_list(update, context)

async def lxc_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await lxc_handler.handle_list(update, context)

async def vm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await vm_handler.handle_callback(update, context)

async def lxc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await lxc_handler.handle_callback(update, context)
