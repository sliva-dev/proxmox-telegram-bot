import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM = {
    'BOT_TOKEN': os.getenv('BOT_TOKEN'),
    'WHITELIST': [int(uid.strip()) for uid in os.getenv('WHITELIST', '').split(',') if uid.strip()]
}

# Исправьте эту часть - убедитесь что realm сохраняется
_host = os.getenv('HOST') or os.getenv('PROXMOX_HOST') or 'localhost'
_user = os.getenv('USER') or os.getenv('PROXMOX_USER')
if _user and '@' not in _user:
    _user = f"{_user}@pam"

_token_name = os.getenv('PROXMOX_TOKEN_NAME')
_token_value = os.getenv('PROXMOX_TOKEN_VALUE')

PROXMOX = {
    'HOST': _host,
    'USER': _user,  # Должно быть 'root@pam'
    'TOKEN_NAME': _token_name,
    'TOKEN_VALUE': _token_value,
    'PORT': int(os.getenv('PROXMOX_PORT', 8006))
}

ALERTS = {
    'CPU_TEMP_THRESHOLD': int(os.getenv('CPU_TEMP_THRESHOLD', 75)),
    'CPU_USAGE_THRESHOLD': int(os.getenv('CPU_USAGE_THRESHOLD', 80)),
    'RAM_USAGE_THRESHOLD': int(os.getenv('RAM_USAGE_THRESHOLD', 80)),
    'CHECK_INTERVAL': int(os.getenv('CHECK_INTERVAL', 300))
}
