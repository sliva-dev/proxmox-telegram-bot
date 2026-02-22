import time
import logging
import threading
import urllib3
from functools import wraps
from proxmoxer import ProxmoxAPI

logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_proxmox_instance = None
_lock = threading.Lock()


def get_proxmox_api(config):
    """
    Возвращает синглтон-подключение к Proxmox API.
    Ожидает объект ProxmoxConfig.
    """
    global _proxmox_instance

    if _proxmox_instance is not None:
        return _proxmox_instance

    with _lock:
        if _proxmox_instance is not None:
            return _proxmox_instance

        try:
            logger.info(f"Создаем соединение с Proxmox: {config.host}")

            _proxmox_instance = ProxmoxAPI(
                host=config.host,
                user=config.user,
                token_name=config.token_name,
                token_value=config.token_value,
                verify_ssl=False,
                port=config.port,
                timeout=30,
            )
            _proxmox_instance.nodes.get()

            logger.info("Соединение с Proxmox установлено")
            return _proxmox_instance

        except Exception as e:
            logger.error(f"Ошибка подключения к Proxmox: {e}")
            _proxmox_instance = None
            raise


def retry_proxmox_call(max_retries=3, delay=1, catch_exceptions=(Exception,)):
    """
    Декоратор для повторных попыток.
    catch_exceptions: кортеж исключений, при которых нужно повторять вызов.
    Остальные ошибки будут пробрасываться сразу.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except catch_exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        sleep_time = delay * (2**attempt)
                        logger.warning(
                            f"Попытка {attempt + 1}/{max_retries} не удалась: {e}. Повтор через {sleep_time}с"
                        )
                        time.sleep(sleep_time)

            logger.error(f"Все {max_retries} попыток не удались: {last_exception}")
            raise last_exception

        return wrapper

    return decorator
