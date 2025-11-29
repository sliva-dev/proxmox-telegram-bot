import re
import time
import logging
from functools import wraps
from proxmoxer import ProxmoxAPI
from config import PROXMOX

logger = logging.getLogger(__name__)

# Singleton для Proxmox API
_proxmox_instance = None

def get_proxmox_api():
    """Получить экземпляр Proxmox API (singleton)"""
    global _proxmox_instance

    if _proxmox_instance is not None:
        return _proxmox_instance

    try:
        logger.info(f"Создаем соединение с Proxmox: {PROXMOX['HOST']}")
        if not PROXMOX['USER'] or '@' not in PROXMOX['USER']:
            raise ValueError("USER должен быть в формате user@realm")

        _proxmox_instance = ProxmoxAPI(
            host=PROXMOX['HOST'],
            user=PROXMOX['USER'],
            token_name=PROXMOX['TOKEN_NAME'],
            token_value=PROXMOX['TOKEN_VALUE'],
            verify_ssl=False,
            port=PROXMOX.get('PORT', 8006),
            timeout=30
        )
        _proxmox_instance.nodes.get()
        logger.info("Соединение с Proxmox установлено")
        return _proxmox_instance
    except Exception as e:
        logger.error(f"Ошибка подключения к Proxmox: {e}")
        _proxmox_instance = None
        raise

def retry_proxmox_call(max_retries=3, delay=1):
    """Декоратор для повторных вызовов Proxmox API"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        sleep_time = delay * (2 ** attempt)  # exponential backoff
                        logger.warning(f"Попытка {attempt + 1}/{max_retries} не удалась: {e}. Повтор через {sleep_time}с")
                        time.sleep(sleep_time)
            logger.error(f"Все {max_retries} попыток не удались: {last_exception}")
            raise last_exception
        return wrapper
    return decorator

def find_node_by_vmid(proxmox, vmid, resource_type='qemu'):
    """Ищет узел, на котором находится VM/LXC с заданным vmid"""
    try:
        for node in proxmox.nodes.get():
            node_name = node['node']
            resources = proxmox.nodes(node_name).qemu.get() if resource_type == 'qemu' else proxmox.nodes(node_name).lxc.get()
            for res in resources:
                if int(res['vmid']) == int(vmid):
                    return node_name
        raise ValueError(f"Ресурс {vmid} не найден")
    except Exception as e:
        raise Exception(f"Ошибка поиска узла: {e}")

def _human_gb(bytes_val):
    return round(bytes_val / (1024 ** 3), 1) if bytes_val else 0.0

@retry_proxmox_call(max_retries=3)
def get_vm_list():
    proxmox = get_proxmox_api()
    vms = []
    try:
        for node in proxmox.nodes.get():
            node_name = node['node']
            for vm in proxmox.nodes(node_name).qemu.get():
                vmid = int(vm['vmid'])
                try:
                    status = proxmox.nodes(node_name).qemu(vmid).status.current.get()
                    config = proxmox.nodes(node_name).qemu(vmid).config.get()

                    uptime = int(status.get('uptime', 0))
                    cpu = round(float(status.get('cpu', 0)) * 100, 1)
                    mem_used = int(status.get('mem', 0)) // 1024 // 1024
                    mem_total = int(status.get('maxmem', 1)) // 1024 // 1024
                    mem_pct = round(mem_used / mem_total * 100, 1) if mem_total else 0

                    used_gb = _human_gb(status.get('disk', 0))
                    total_gb = _human_gb(status.get('maxdisk', 0))

                    if total_gb == 0:  # guest-agent не установлен
                        total_gb = 0
                        for val in config.values():
                            if isinstance(val, str):
                                m = re.search(r'size=(\d+)([GM]?)B?', val, re.I)
                                if m:
                                    size = int(m.group(1))
                                    unit = m.group(2).upper()
                                    if not unit or unit == 'G':
                                        total_gb += size
                                    elif unit == 'M':
                                        total_gb += size / 1024

                    vms.append({
                        'id': vmid,
                        'name': vm.get('name', f"VM{vmid}"),
                        'status': vm.get('status', 'unknown'),
                        'node': node_name,
                        'uptime': uptime,
                        'cpu_usage_percent': cpu,
                        'mem_used_mb': mem_used,
                        'mem_total_mb': mem_total,
                        'mem_usage_percent': mem_pct,
                        'disk_used_gb': used_gb if used_gb > 0 else 0.0,
                        'disk_total_gb': round(total_gb, 1),
                    })
                except Exception as e:
                    logger.error(f"[VM {vmid}] ошибка: {e}")
                    vms.append({'id': vmid, 'name': 'Ошибка', 'status': 'error', 'node': node_name,
                                'uptime': 0, 'cpu_usage_percent': 0, 'mem_used_mb': 0, 'mem_total_mb': 0,
                                'mem_usage_percent': 0, 'disk_used_gb': 0.0, 'disk_total_gb': 0.0})
    except Exception as e:
        logger.error(f"Ошибка получения VM: {e}")
    return vms

@retry_proxmox_call(max_retries=3)
def get_lxc_list():
    proxmox = get_proxmox_api()
    lxcs = []
    try:
        for node in proxmox.nodes.get():
            node_name = node['node']
            for ct in proxmox.nodes(node_name).lxc.get():
                vmid = int(ct['vmid'])
                try:
                    status = proxmox.nodes(node_name).lxc(vmid).status.current.get()
                    config = proxmox.nodes(node_name).lxc(vmid).config.get()

                    uptime = int(status.get('uptime', 0))
                    cpu = round(float(status.get('cpu', 0)) * 100, 1)
                    mem_used = int(status.get('mem', 0)) // 1024 // 1024
                    mem_total = int(status.get('maxmem', 1)) // 1024 // 1024
                    mem_pct = round(mem_used / mem_total * 100, 1) if mem_total else 0

                    used_gb = total_gb = 0.0

                    if 'rootfs' in status:
                        used_gb += _human_gb(status['rootfs'].get('used', 0))
                        total_gb += _human_gb(status['rootfs'].get('total', 0)) or _human_gb(status['rootfs'].get('max', 0))

                    for key, val in status.items():
                        if key.startswith('mp') or key.startswith('mountpoint'):
                            if isinstance(val, dict):
                                used_gb += _human_gb(val.get('used', 0))
                                total_gb += _human_gb(val.get('total', 0)) or _human_gb(val.get('max', 0))

                    lxcs.append({
                        'id': vmid,
                        'name': ct.get('name', f"LXC{vmid}"),
                        'status': ct.get('status', 'unknown'),
                        'node': node_name,
                        'uptime': uptime,
                        'cpu_usage_percent': cpu,
                        'mem_used_mb': mem_used,
                        'mem_total_mb': mem_total,
                        'mem_usage_percent': mem_pct,
                        'disk_used_gb': round(used_gb, 1),
                        'disk_total_gb': round(total_gb, 1) if total_gb > 0 else 0.0,
                    })
                except Exception as e:
                    logger.error(f"[LXC {vmid}] ошибка: {e}")
    except Exception as e:
        logger.error(f"Ошибка получения LXC: {e}")
    return lxcs

def vm_action(vmid, action, node=None):
    proxmox = get_proxmox_api()
    if node is None:
        node = find_node_by_vmid(proxmox, vmid, 'qemu')
    try:
        if action == 'start':
            proxmox.nodes(node).qemu(vmid).status.start.post()
            return "Запущена"
        if action == 'stop':
            try:
                proxmox.nodes(node).qemu(vmid).status.shutdown.post(timeout=30)
                return "Выключается..."
            except:
                proxmox.nodes(node).qemu(vmid).status.stop.post()
                return "Принудительно остановлена"
        if action == 'reboot':
            try:
                proxmox.nodes(node).qemu(vmid).status.reboot.post(timeout=30)
                return "Перезагружается..."
            except:
                proxmox.nodes(node).qemu(vmid).status.reset.post()
                return "Принудительно перезагружена"
    except Exception as e:
        raise Exception(f"Ошибка {action} VM {vmid}: {e}")

def lxc_action(vmid, action, node=None):
    proxmox = get_proxmox_api()
    if node is None:
        node = find_node_by_vmid(proxmox, vmid, 'lxc')
    try:
        if action == 'start':
            proxmox.nodes(node).lxc(vmid).status.start.post()
            return "Запущен"
        if action == 'stop':
            try:
                proxmox.nodes(node).lxc(vmid).status.shutdown.post(timeout=20)
                return "Выключается..."
            except:
                proxmox.nodes(node).lxc(vmid).status.stop.post()
                return "Принудительно остановлен"
        if action == 'reboot':
            try:
                proxmox.nodes(node).lxc(vmid).status.reboot.post(timeout=20)
                return "Перезагружается..."
            except:
                proxmox.nodes(node).lxc(vmid).status.stop.post()
                time.sleep(2)
                proxmox.nodes(node).lxc(vmid).status.start.post()
                return "Принудительно перезапущен"
    except Exception as e:
        raise Exception(f"Ошибка {action} LXC {vmid}: {e}")

def format_uptime(seconds: int) -> str:
    if not seconds:
        return "—"
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    m = (seconds % 3600) // 60
    if d: return f"{d}д {h}ч {m}м"
    if h: return f"{h}ч {m}м"
    return f"{m}м"
