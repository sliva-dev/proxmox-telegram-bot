import psutil
import logging
from config import ALERTS
from system.sensors import get_temp

logger = logging.getLogger(__name__)


def check_cpu_temp():
    try:
        temps = get_temp()
        if not temps:
            return False, 0

        cpu_temp = next((t["temp"] for t in temps if t["sensor"] == "CPU"), None)

        if cpu_temp is None and temps:
            cpu_temp = max([t["temp"] for t in temps])

        if cpu_temp is None:
            return False, 0

        return cpu_temp > ALERTS.cpu_temp_threshold, round(cpu_temp, 1)
    except Exception as e:
        logger.error(f"❌ Ошибка проверки температуры: {e}")
        return False, 0


def check_cpu_usage():
    try:
        usage = psutil.cpu_percent(interval=None)
        return usage > ALERTS.cpu_usage_threshold, round(usage, 1)
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки CPU: {e}")
        return False, 0


def check_ram_usage():
    try:
        ram = psutil.virtual_memory()
        return ram.percent > ALERTS.ram_usage_threshold, round(ram.percent, 1)
    except Exception as e:
        logger.error(f"❌ Ошибка RAM: {e}")
        return False, 0
