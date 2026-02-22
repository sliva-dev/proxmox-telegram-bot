import logging
import time
import subprocess

from proxmox.client import get_proxmox_api, retry_proxmox_call
from proxmox.utils import _human_gb, find_node_by_vmid
from config import PROXMOX

logger = logging.getLogger(__name__)


@retry_proxmox_call(max_retries=3)
def get_lxc_list():
    proxmox = get_proxmox_api(PROXMOX)
    lxcs = []
    try:
        for node in proxmox.nodes.get():
            node_name = node["node"]
            for ct in proxmox.nodes(node_name).lxc.get():
                vmid = int(ct["vmid"])
                try:
                    status = proxmox.nodes(node_name).lxc(vmid).status.current.get()

                    uptime = int(status.get("uptime", 0))
                    cpu = round(float(status.get("cpu", 0)) * 100, 1)
                    mem_used = int(status.get("mem", 0)) // 1024 // 1024
                    mem_total = int(status.get("maxmem", 1)) // 1024 // 1024
                    mem_pct = round(mem_used / mem_total * 100, 1) if mem_total else 0

                    used_gb = total_gb = 0.0

                    if "rootfs" in status:
                        used_gb += _human_gb(status["rootfs"].get("used", 0))
                        total_gb += _human_gb(
                            status["rootfs"].get("total", 0)
                        ) or _human_gb(status["rootfs"].get("max", 0))

                    for key, val in status.items():
                        if key.startswith("mp") or key.startswith("mountpoint"):
                            if isinstance(val, dict):
                                used_gb += _human_gb(val.get("used", 0))
                                total_gb += _human_gb(val.get("total", 0)) or _human_gb(
                                    val.get("max", 0)
                                )

                    lxcs.append(
                        {
                            "id": vmid,
                            "name": ct.get("name", f"LXC{vmid}"),
                            "status": ct.get("status", "unknown"),
                            "node": node_name,
                            "uptime": uptime,
                            "cpu_usage_percent": cpu,
                            "mem_used_mb": mem_used,
                            "mem_total_mb": mem_total,
                            "mem_usage_percent": mem_pct,
                            "disk_used_gb": round(used_gb, 1),
                            "disk_total_gb": (
                                round(total_gb, 1) if total_gb > 0 else 0.0
                            ),
                        }
                    )
                except Exception as e:
                    logger.error(f"[LXC {vmid}] ошибка получения данных: {e}")
    except Exception as e:
        logger.error(f"Ошибка получения списка LXC: {e}")
    return lxcs


def lxc_action(vmid, action, node=None):
    proxmox = get_proxmox_api(PROXMOX)

    if node is None:
        node = find_node_by_vmid(proxmox, vmid, "lxc")

    if not node:
        raise ValueError(f"Контейнер с ID {vmid} не найден ни на одной ноде.")

    try:
        if action == "start":
            proxmox.nodes(node).lxc(vmid).status.start.post()
            return "Запущен"

        elif action == "stop":
            try:
                proxmox.nodes(node).lxc(vmid).status.shutdown.post(timeout=20)
                return "Выключается..."
            except Exception as e:
                logger.warning(
                    f"Мягкое выключение {vmid} не удалось ({e}), принудительная остановка."
                )
                proxmox.nodes(node).lxc(vmid).status.stop.post()
                return "Принудительно остановлен"

        elif action == "reboot":
            try:
                proxmox.nodes(node).lxc(vmid).status.reboot.post(timeout=20)
                return "Перезагружается..."
            except Exception as e:
                logger.warning(
                    f"Мягкая перезагрузка {vmid} не удалась ({e}), принудительный рестарт."
                )
                proxmox.nodes(node).lxc(vmid).status.stop.post()

                for _ in range(10):
                    curr_status = (
                        proxmox.nodes(node).lxc(vmid).status.current.get().get("status")
                    )
                    if curr_status == "stopped":
                        break
                    time.sleep(1)

                proxmox.nodes(node).lxc(vmid).status.start.post()
                return "Принудительно перезапущен"

        else:
            raise ValueError(f"Неизвестное действие: {action}")

    except Exception as e:
        raise Exception(f"Ошибка {action} LXC {vmid}: {e}")


def execute_lxc_command(vmid, node, command):
    try:
        cmd = ["pct", "exec", str(vmid), "--", "bash", "-c", command]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        out = result.stdout.strip()
        err = result.stderr.strip()

        if not out and not err:
            return "✅ Команда выполнена (без вывода)"

        return out if out else err
    except subprocess.TimeoutExpired:
        return "⏳ Превышено время выполнения команды (таймаут 30 секунд)."
    except Exception as e:
        return f"❌ Ошибка выполнения pct exec: {e}"
