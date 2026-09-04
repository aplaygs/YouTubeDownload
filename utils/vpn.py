"""
Модуль обнаружения активных VPN-соединений на macOS.

Отвечает за:
1. Проверку системных сетевых служб через scutil --nc list.
2. Проверку шлюза по умолчанию (default gateway interface: utun, tun, ppp, wg).
3. Информирование пользователя и предотвращение нежелательной загрузки через VPN.
"""

import re
import subprocess
from typing import List, Tuple


def get_active_vpn_services() -> List[str]:
    """
    Возвращает список названий активных (подключенных) VPN-сервисов на macOS.
    Например: ['vlad.wg', 'WireGuard', 'Amnezia']
    """
    connected_vpns: List[str] = []

    # 1. Проверка через системную утилиту конфигурации сети macOS (scutil)
    try:
        proc = subprocess.run(
            ["scutil", "--nc", "list"],
            capture_output=True,
            text=True,
            timeout=2
        )
        for line in proc.stdout.splitlines():
            # Ищем подключенные VPN/PPP/IPSec интерфейсы
            if "(Connected)" in line and any(kw in line for kw in ("VPN", "IPSec", "PPP", "wireguard", "tun")):
                match = re.search(r'\"([^\"]+)\"', line)
                name = match.group(1) if match else line.strip()
                if name not in connected_vpns:
                    connected_vpns.append(name)
    except Exception:
        pass

    # 2. Проверка активного сетевого шлюза по умолчанию
    try:
        route = subprocess.run(
            ["route", "-n", "get", "default"],
            capture_output=True,
            text=True,
            timeout=2
        )
        for line in route.stdout.splitlines():
            if "interface:" in line:
                iface = line.split(":", 1)[1].strip()
                # Если дефолтный трафик идет через туннельный интерфейс
                if iface.startswith(("utun", "ppp", "tun", "tap", "wg")):
                    desc = f"Туннель ({iface})"
                    if not connected_vpns and desc not in connected_vpns:
                        connected_vpns.append(desc)
    except Exception:
        pass

    return connected_vpns


def is_vpn_active() -> Tuple[bool, str]:
    """
    Проверяет, включен ли VPN в текущий момент.

    :return: Кортеж (is_active: bool, vpn_description: str)
    """
    vpns = get_active_vpn_services()
    if vpns:
        return True, ", ".join(vpns)
    return False, ""
