import psutil
import time
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

IGNORE_FSTYPES = {"", "squashfs", "tmpfs", "devtmpfs", "overlay", "iso9660", "vfat"}


def get_temp():
    """Собирает температуры и возвращает список словарей (для алертов и статуса)."""
    temps_list = []
    if not hasattr(psutil, "sensors_temperatures"):
        return temps_list

    try:
        temps = psutil.sensors_temperatures()
        for chip_name, entries in temps.items():
            for entry in entries:
                label = entry.label or chip_name
                val = entry.current

                label_lower = label.lower()
                chip_lower = chip_name.lower()

                if "tctl" in label_lower or "tctl" in chip_lower:
                    pretty = "CPU"
                elif "ccd" in label_lower or "ccd" in chip_lower:
                    pretty = "CPU (Кристалл)"
                elif "mt7921" in label_lower or "mt7921" in chip_lower:
                    pretty = "Wi-Fi адаптер"
                else:
                    pretty = label

                temps_list.append({"chip": chip_name, "sensor": pretty, "temp": val})

        return temps_list
    except Exception as e:
        logger.error(f"❌ Ошибка получения температур: {e}")
        return []


def get_uptime_str():
    """Возвращает время работы системы в удобном формате."""
    uptime_seconds = time.time() - psutil.boot_time()
    td = timedelta(seconds=int(uptime_seconds))
    hours = td.seconds // 3600
    return f"{td.days}д {hours}ч"


def get_cpu_load():
    """Получает нагрузку на CPU (кроссплатформенно)."""
    try:
        load = psutil.getloadavg()
        cpus = psutil.cpu_count(logical=True) or 1

        def load_pct(l):
            pct = int((l / cpus) * 100)
            return f"{l:.2f} ({pct}%)"

        return f"1м: {load_pct(load[0])}, 5м: {load_pct(load[1])}, 15м: {load_pct(load[2])}"
    except AttributeError:
        return f"{psutil.cpu_percent(interval=1)}%"


def get_status():
    """Собирает всю информацию о системе и формирует итоговый текст."""
    try:
        uptime = get_uptime_str()
        cpu_load = get_cpu_load()

        ram = psutil.virtual_memory()
        ram_used_gb = int(ram.used / (1024**3))
        ram_total_gb = int(ram.total / (1024**3))
        ram_usage = f"{int(ram.percent)}% ({ram_used_gb}ГБ / {ram_total_gb}ГБ)"

        disks_out = []
        for part in psutil.disk_partitions(all=False):
            if part.fstype in IGNORE_FSTYPES or part.mountpoint.startswith("/boot"):
                continue

            try:
                usage = psutil.disk_usage(part.mountpoint)
                used_gb = round(usage.used / (1024**3), 1)
                size_gb = round(usage.total / (1024**3), 1)

                emoji = "🖥️" if part.mountpoint in ("/", "C:\\") else "🗄️"
                disks_out.append(
                    f"{emoji} {part.mountpoint}: {usage.percent}% ({used_gb}ГБ / {size_gb}ГБ)"
                )
            except PermissionError:
                continue

        temps = get_temp()
        temps_text = []
        if not temps:
            if not hasattr(psutil, "sensors_temperatures"):
                temps_text.append("🌡️ Чтение температур не поддерживается вашей ОС.")
            else:
                temps_text.append("🌡️ Датчики не обнаружены или нет прав доступа.")
        else:
            for t in temps:
                sensor = t["sensor"]
                val = t["temp"]

                if "CPU" in sensor:
                    temps_text.append(f"🔥 {sensor}: {val:.1f}°C")
                elif "Wi-Fi" in sensor or "Chipset" in sensor:
                    temps_text.append(f"📡 {sensor}: {val:.1f}°C")
                else:
                    temps_text.append(f"🌡️ {sensor}: {val:.1f}°C")

        status_text = (
            f"⏰ Время работы: {uptime}\n"
            f"⚡ Нагрузка CPU: {cpu_load}\n"
            f"💻 Оперативная память: {ram_usage}\n\n"
            f"💽 Диски:\n"
            + ("\n".join(disks_out) if disks_out else "Нет данных")
            + "\n\n"
            f"🌡️ Температуры:\n"
            + ("\n".join(temps_text) if temps_text else "Нет данных")
        )
        return status_text

    except Exception as e:
        logger.error(f"❌ Ошибка получения статуса: {e}", exc_info=True)
        return f"❌ Произошла ошибка при сборе данных: {e}"


if __name__ == "__main__":
    print(get_status())
