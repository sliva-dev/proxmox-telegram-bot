import re
import logging
import time

from proxmox.client import get_proxmox_api, retry_proxmox_call
from proxmox.utils import _human_gb, find_node_by_vmid
from config import PROXMOX

logger = logging.getLogger(__name__)


@retry_proxmox_call(max_retries=3)
def get_vm_list():
    proxmox = get_proxmox_api(PROXMOX)
    vms = []
    try:
        for node in proxmox.nodes.get():
            node_name = node["node"]
            for vm in proxmox.nodes(node_name).qemu.get():

                if vm.get("template") == 1:
                    continue

                vmid = int(vm["vmid"])
                try:
                    status = proxmox.nodes(node_name).qemu(vmid).status.current.get()

                    uptime = int(status.get("uptime", 0))
                    cpu = round(float(status.get("cpu", 0)) * 100, 1)
                    mem_used = int(status.get("mem", 0)) // 1024 // 1024
                    mem_total = int(status.get("maxmem", 1)) // 1024 // 1024
                    mem_pct = round(mem_used / mem_total * 100, 1) if mem_total else 0

                    used_gb = _human_gb(status.get("disk", 0))
                    total_gb = _human_gb(status.get("maxdisk", 0))

                    if total_gb == 0:
                        config = proxmox.nodes(node_name).qemu(vmid).config.get()
                        for val in config.values():
                            if isinstance(val, str):
                                m = re.search(r"size=(\d+)([GM]?)B?", val, re.I)
                                if m:
                                    size = int(m.group(1))
                                    unit = m.group(2).upper()
                                    if not unit or unit == "G":
                                        total_gb += size
                                    elif unit == "M":
                                        total_gb += size / 1024

                    vms.append(
                        {
                            "id": vmid,
                            "name": vm.get("name", f"VM{vmid}"),
                            "status": vm.get("status", "unknown"),
                            "node": node_name,
                            "uptime": uptime,
                            "cpu_usage_percent": cpu,
                            "mem_used_mb": mem_used,
                            "mem_total_mb": mem_total,
                            "mem_usage_percent": mem_pct,
                            "disk_used_gb": used_gb if used_gb > 0 else 0.0,
                            "disk_total_gb": round(total_gb, 1),
                        }
                    )
                except Exception as e:
                    logger.error(f"[VM {vmid}] ошибка получения данных: {e}")
                    vms.append(
                        {
                            "id": vmid,
                            "name": "Ошибка",
                            "status": "error",
                            "node": node_name,
                            "uptime": 0,
                            "cpu_usage_percent": 0,
                            "mem_used_mb": 0,
                            "mem_total_mb": 0,
                            "mem_usage_percent": 0,
                            "disk_used_gb": 0.0,
                            "disk_total_gb": 0.0,
                        }
                    )
    except Exception as e:
        logger.error(f"Ошибка получения списка VM: {e}")
    return vms


def vm_action(vmid, action, node=None):
    proxmox = get_proxmox_api(PROXMOX)

    if node is None:
        node = find_node_by_vmid(proxmox, vmid, "qemu")

    if not node:
        raise ValueError(f"Виртуальная машина с ID {vmid} не найдена.")

    try:
        if action == "start":
            proxmox.nodes(node).qemu(vmid).status.start.post()
            return "Запущена"

        elif action == "stop":
            try:
                proxmox.nodes(node).qemu(vmid).status.shutdown.post(timeout=30)
                return "Выключается..."
            except Exception as e:
                logger.warning(
                    f"Мягкое выключение VM {vmid} не удалось ({e}), принудительная остановка."
                )
                proxmox.nodes(node).qemu(vmid).status.stop.post()
                return "Принудительно остановлена"

        elif action == "reboot":
            try:
                proxmox.nodes(node).qemu(vmid).status.reboot.post(timeout=30)
                return "Перезагружается..."
            except Exception as e:
                logger.warning(
                    f"Мягкая перезагрузка VM {vmid} не удалась ({e}), принудительный сброс."
                )
                proxmox.nodes(node).qemu(vmid).status.reset.post()
                return "Принудительно перезагружена"

        else:
            raise ValueError(f"Неизвестное действие: {action}")

    except Exception as e:
        raise Exception(f"Ошибка {action} VM {vmid}: {e}")


def execute_vm_command(vmid, node, command):
    proxmox = get_proxmox_api(PROXMOX)
    try:
        res = (
            proxmox.nodes(node)
            .qemu(vmid)
            .agent.exec.post(command=["bash", "-c", command])
        )
        pid = res.get("pid")

        for _ in range(15):
            status = proxmox.nodes(node).qemu(vmid).agent("exec-status").get(pid=pid)
            if status.get("exited") == 1:
                out = status.get("out-data", "")
                err = status.get("err-data", "")
                return (
                    out
                    if out
                    else (err if err else "✅ Команда выполнена (без вывода)")
                )
            time.sleep(1)

        return "⏳ Превышено время ожидания ответа от команды."

    except Exception as e:
        error_msg = str(e).lower()
        if "agent" in error_msg or "qemu-guest-agent is not running" in error_msg:
            return "❌ Ошибка: QEMU Guest Agent не установлен или не запущен в этой VM."
        return f"❌ Ошибка выполнения команды: {e}"
