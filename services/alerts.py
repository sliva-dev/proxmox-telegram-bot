import asyncio
import logging
from telegram.ext import Application
from system.checks import check_cpu_temp, check_cpu_usage, check_ram_usage
from config import TELEGRAM, ALERTS

logger = logging.getLogger(__name__)


class AlertManager:
    def __init__(self, application: Application):
        self.app = application
        self.running = False
        self.task = None

    async def start(self):
        self.running = True
        self.task = asyncio.create_task(self._monitor_loop())
        logger.info("🚨 Система мониторинга запущена!")

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Система мониторинга остановлена")

    async def _monitor_loop(self):
        error_sleep = 60

        while self.running:
            try:
                await self._check_alerts()
                await asyncio.sleep(ALERTS.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в мониторинге: {e}")
                await asyncio.sleep(error_sleep)

    async def _run_check(self, check_func):
        """Запускает синхронную проверку в потоке, чтобы не блокировать бота"""
        return await asyncio.to_thread(check_func)

    async def _check_alerts(self):
        try:
            alert, value = await self._run_check(check_cpu_temp)
            if alert:
                await self._send_alert(
                    f"🔥 <b>ПЕРЕГРЕВ!</b> Температура CPU: {value}°C (порог: {ALERTS.cpu_temp_threshold}°C)"
                )
            else:
                logger.debug(f"✅ Температура в норме: {value}°C")
        except Exception as e:
            logger.error(f"❌ Ошибка проверки температуры: {e}")

        try:
            alert, value = await self._run_check(check_cpu_usage)
            if alert:
                await self._send_alert(
                    f"⚡ <b>ВЫСОКАЯ НАГРУЗКА!</b> CPU: {value}% (порог: {ALERTS.cpu_usage_threshold}%)"
                )
        except Exception as e:
            logger.error(f"❌ Ошибка проверки CPU: {e}")

        try:
            alert, value = await self._run_check(check_ram_usage)
            if alert:
                await self._send_alert(
                    f"💾 <b>МНОГО ПАМЯТИ!</b> RAM: {value}% (порог: {ALERTS.ram_usage_threshold}%)"
                )
        except Exception as e:
            logger.error(f"❌ Ошибка проверки RAM: {e}")

    async def _send_alert(self, text: str):
        try:
            for chat_id in TELEGRAM.whitelist:
                await self.app.bot.send_message(
                    chat_id=chat_id, text=text, parse_mode="HTML"
                )
            logger.info(f"📢 Отправлен алерт: {text}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки алерта: {e}")
