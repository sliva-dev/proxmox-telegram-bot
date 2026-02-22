import logging

logger = logging.getLogger(__name__)


def _human_gb(bytes_val):
    return round(bytes_val / (1024**3), 1) if bytes_val else 0.0


def format_uptime(seconds: int) -> str:
    if not seconds:
        return "—"
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    m = (seconds % 3600) // 60
    if d:
        return f"{d}д {h}ч {m}м"
    if h:
        return f"{h}ч {m}м"
    return f"{m}м"


def find_node_by_vmid(proxmox, vmid, resource_type="qemu"):
    try:
        for node in proxmox.nodes.get():
            node_name = node["node"]
            resources = (
                proxmox.nodes(node_name).qemu.get()
                if resource_type == "qemu"
                else proxmox.nodes(node_name).lxc.get()
            )
            for res in resources:
                if int(res["vmid"]) == int(vmid):
                    return node_name
        raise ValueError(f"Ресурс {vmid} не найден")
    except Exception as e:
        logger.error(f"Ошибка поиска узла: {e}")
        raise Exception(f"Ошибка поиска узла: {e}")
