import asyncio
import logging
from telegram.ext import Application
from system_utils import check_cpu_temp, check_cpu_usage, check_ram_usage
from config import TELEGRAM, ALERTS

logger = logging.getLogger(__name__)

class AlertManager:
    def __init__(self, application: Application):
        self.app = application
        self.running = False
        self.last_alerts = {}
        self.task = None

    async def start(self):
        """Запустить мониторинг"""
        self.running = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info("🚨 Система мониторинга запущена!")

    async def stop(self):
        """Остановить мониторинг"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Система мониторинга остановлена")

    async def _monitor_loop(self):
        """Основной цикл мониторинга"""
        while self.running:
            try:
                await self._check_alerts()
                await asyncio.sleep(ALERTS['CHECK_INTERVAL'])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в мониторинге: {e}")
                await asyncio.sleep(60)

    async def _check_alerts(self):
        """Проверить все алерты"""
        try:
            alert, value = check_cpu_temp()
            if alert:
                await self._send_alert(f"🔥 *ПЕРЕГРЕВ!* Температура CPU: {value}°C (порог: {ALERTS['CPU_TEMP_THRESHOLD']}°C)")
            else:
                logger.debug(f"✅ Температура в норме: {value}°C")
        except Exception as e:
            logger.error(f"❌ Ошибка проверки температуры: {e}")

        alert, value = check_cpu_usage()
        if alert:
            await self._send_alert(f"⚡ *ВЫСОКАЯ НАГРУЗКА!* CPU: {value}% (порог: {ALERTS['CPU_USAGE_THRESHOLD']}%)")

        alert, value = check_ram_usage()
        if alert:
            await self._send_alert(f"💾 *МНОГО ПАМЯТИ!* RAM: {value}% (порог: {ALERTS['RAM_USAGE_THRESHOLD']}%)")

    async def _send_alert(self, text: str):
        """Отправить алерт"""
        try:
            for chat_id in TELEGRAM['WHITELIST']:
                await self.app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode='Markdown'
                )
            logger.info(f"📢 Отправлен алерт: {text}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки алерта: {e}")
