import psutil
import subprocess
import re
import logging
from config import ALERTS
from proxmox_utils import get_vm_list

logger = logging.getLogger(__name__)

def get_temp():
    try:
        result = subprocess.run(['sensors'], capture_output=True, text=True, check=True)
        lines = result.stdout.splitlines()
        temps = []

        # === СЮДА ПОДСТАВЬТЕ СВОИ ДАННЫЕ С sensors ===
        # Запустите в терминале команду 'sensors' и посмотрите какие у вас названия датчиков
        # Затем настройте правила ниже под вашу систему

        current_chip = None
        for line in lines:
            if line and not line.startswith(' '):
                current_chip = line.strip()
            match = re.search(r'([A-Za-z0-9\-_ ]+):\s*\+?([\d.]+)°C', line)
            if match:
                label = match.group(1).strip()
                val = float(match.group(2))

                # Настройте эти правила под ваши датчики:
                if label.lower().startswith('tctl'):
                    pretty = 'CPU (Tctl)' # Основной датчик CPU
                elif 'ccd' in label.lower():
                    pretty = 'CPU CCD' # Дополнительные ядра CPU
                elif 'temp1' in label.lower() and 'mt7921' in current_chip.lower():
                    pretty = 'Chipset / temp'  # Датчик WiFi
                else:
                    pretty = label

                temps.append({'chip': current_chip or '', 'sensor': pretty, 'temp': val})
        return temps
    except subprocess.CalledProcessError:
        return []
    except Exception as e:
        logger.error(f"❌ Ошибка получения температур: {e}")
        return []

def get_storage():
    try:
        result = subprocess.run(['df', '-h'], capture_output=True, text=True, check=True)
        lines = result.stdout.splitlines()[1:]
        storage_info = []
        for line in lines:
            if line.strip():
                parts = line.split()
                if len(parts) >= 6:
                    mount = parts[5]
                    size = parts[1]
                    used = parts[2]
                    perc = parts[4]
                    storage_info.append({'filesystem': parts[0], 'mount': mount, 'used': used, 'size': size, 'percent': perc})
        return storage_info
    except Exception as e:
        logger.error(f"Ошибка получения информации о дисках: {e}")
        return []

def check_cpu_temp():
    """Проверка температуры CPU на превышение порога"""
    try:
        temps = get_temp()
        if not temps:
            logger.info("📊 Нет данных о температуре")
            return False, 0

        cpu_temp = None
        for t in temps:
            if t['sensor'] == 'CPU (Tctl)':
                cpu_temp = t['temp']
                break

        # Если не нашли Tctl, берем максимальную температуру
        if cpu_temp is None:
            cpu_temp = max([t['temp'] for t in temps])

        threshold = ALERTS.get('CPU_TEMP_THRESHOLD', 80)

        logger.debug(f"🌡️ Температура CPU: {cpu_temp}°C, порог: {threshold}°C")
        return cpu_temp > threshold, round(cpu_temp, 1)
    except Exception as e:
        logger.error(f"❌ Ошибка проверки температуры: {e}")
        return False, 0

def check_cpu_usage():
    """Проверка загрузки CPU на превышение порога"""
    try:
        usage = psutil.cpu_percent(interval=1)
        threshold = ALERTS.get('CPU_USAGE_THRESHOLD', 90)
        return usage > threshold, round(usage, 1)
    except Exception as e:
        logger.error(f"Ошибка проверки загрузки CPU: {e}")
        return False, 0

def check_ram_usage():
    """Проверка использования RAM на превышение порога"""
    try:
        ram = psutil.virtual_memory()
        threshold = ALERTS.get('RAM_USAGE_THRESHOLD', 90)
        return ram.percent > threshold, round(ram.percent, 1)
    except Exception as e:
        logger.error(f"Ошибка проверки использования RAM: {e}")
        return False, 0

def check_vm_status(important_vms):
    """Проверка статуса важных VM"""
    try:
        vm_list = get_vm_list()
        if not vm_list:
            return False, "Не удалось получить список VM"

        stopped_vms = []
        for vm in vm_list:
            if vm['vmid'] in important_vms and vm['status'] != 'running':
                stopped_vms.append(f"VM {vm['vmid']} ({vm.get('name', '')})")

        if stopped_vms:
            return True, f"Остановлены важные VM: {', '.join(stopped_vms)}"

        return False, "Все VM работают"
    except Exception as e:
        return False, f"Ошибка проверки VM: {str(e)}"

def get_status():
    try:
        # Uptime
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.read().split()[0])
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            uptime = f"{days}д {hours}ч"

        # CPU Load
        load = psutil.getloadavg()
        cpus = psutil.cpu_count(logical=True) or 1
        def load_pct(l):
            pct = int((l / cpus) * 100)
            return f"{l:.2f} ({pct}%)"
        cpu_load = f"1м: {load_pct(load[0])}, 5м: {load_pct(load[1])}, 15м: {load_pct(load[2])}"

        # RAM
        ram = psutil.virtual_memory()
        ram_used_gb = ram.used // (1024**3)
        ram_total_gb = ram.total // (1024**3)
        ram_usage = f"{ram.percent:.1f}% ({ram_used_gb}ГБ / {ram_total_gb}ГБ)"

        # Диски
        storage = get_storage()
        # Ищем основные диски по mount point
        main_disks = {
            'root': '/',
        }

        disks_out = []
        for disk_name, mount_point in main_disks.items():
            for s in storage:
                if s['mount'] == mount_point:
                    emoji = "💾" if disk_name == 'root' else "🚀" if 'ssd' in disk_name else "📀"
                    disks_out.append(f"{emoji} {disk_name}: {s['percent']} ({s['used']} / {s['size']})")
                    break

        # Температуры с нормальными названиями
        temps = get_temp()
        temps_text = []

        for t in temps:
            sensor_name = t['sensor']
            # Переименовываем датчики
            if sensor_name == 'CPU (Tctl)':
                temps_text.append(f"🔥 CPU: {t['temp']:.1f}°C")
            elif sensor_name == 'CPU CCD':
                temps_text.append(f"❄️ CPU_2: {t['temp']:.1f}°C")
            elif sensor_name == 'Chipset / temp':
                temps_text.append(f"📡 WiFi: {t['temp']:.1f}°C")
            else:
                temps_text.append(f"🌡️ {sensor_name}: {t['temp']:.1f}°C")

        # Собираем всё в красивое сообщение
        status_text = (
            f"⏰ Время работы: {uptime}\n"
            f"⚡ Нагрузка CPU: {cpu_load}\n"
            f"💾 Оперативная память: {ram_usage}\n\n"
            f"💿 Диски:\n" + "\n".join(disks_out) + "\n\n"
            f"🌡️ Температуры:\n" + "\n".join(temps_text)
        )
        return status_text
    except Exception as e:
        logger.error(f"❌ Ошибка получения статуса: {str(e)}")
        raise Exception(f"❌ Ошибка получения статуса: {str(e)}")
