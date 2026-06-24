"""Network Awareness Layer (Roadmap Feature #2) — read-only connectivity state for Nexi.

Tool cards
----------
am_i_online        role: net awareness | risk: LOW | confirm: never | verifier: reachability probed   | memory: never store
get_network_status role: net awareness | risk: LOW | confirm: never | verifier: interface resolved     | memory: never store
get_ip_address     role: net awareness | risk: LOW | confirm: never | verifier: local address resolved  | memory: never store

All functions are READ-ONLY (never change adapters, connect, or disconnect). The
reachability probe opens a short-lived outbound socket but sends no data. Every
function returns the engine's standard tool-result dict so the verifier passes on
observed values, regardless of whether the machine is online or offline.
"""

from __future__ import annotations

import socket
from typing import Any


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "net_awareness"), "message": message, **extra}


def _probe_online(timeout: float = 1.5) -> bool:
    """Return True if the internet is reachable. Read-only: connects to a DNS
    port and immediately closes; no data is sent. Tries a couple of well-known
    resolvers so a single blocked host doesn't produce a false negative."""
    for host in ("1.1.1.1", "8.8.8.8"):
        sock = None
        try:
            sock = socket.create_connection((host, 53), timeout=timeout)
            return True
        except OSError:
            continue
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
    return False


def _local_ip() -> str:
    """Best-effort primary local IPv4. Uses an unconnected UDP socket trick that
    asks the OS which interface would route outbound traffic; no packets are sent."""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return ""
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def _all_ipv4() -> list[str]:
    addrs: list[str] = []
    try:
        import psutil
        for iface, snics in psutil.net_if_addrs().items():
            for snic in snics:
                if snic.family == socket.AF_INET and snic.address and not snic.address.startswith("127."):
                    addrs.append(snic.address)
    except Exception:
        pass
    return addrs


def _active_interface() -> str:
    """Name of an up, non-loopback interface, or '' if none can be determined."""
    try:
        import psutil
        stats = psutil.net_if_stats()
        candidates = [name for name, st in stats.items()
                      if getattr(st, "isup", False) and name.lower() not in {"loopback pseudo-interface 1", "lo"}]
        candidates.sort(key=lambda n: (0 if any(k in n.lower() for k in ("wi-fi", "wifi", "wlan", "ethernet")) else 1, n))
        return candidates[0] if candidates else ""
    except Exception:
        return ""


def _wifi_ssid() -> str:
    """Current Wi-Fi SSID on Windows via a read-only `netsh` query, or '' if not on Wi-Fi."""
    try:
        import subprocess
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                             capture_output=True, text=True, timeout=4)
        for line in (out.stdout or "").splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("ssid") and ":" in stripped and not stripped.lower().startswith("bssid"):
                return stripped.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


def am_i_online(slots: dict | None = None) -> dict[str, Any]:
    online = _probe_online()
    msg = "Yes, you're online." if online else "No, I can't reach the internet right now."
    return _ok(msg, tool="am_i_online", online=online)


def get_network_status(slots: dict | None = None) -> dict[str, Any]:
    online = _probe_online()
    iface = _active_interface()
    ssid = _wifi_ssid()
    bits = ["online" if online else "offline"]
    if ssid:
        bits.append(f'on Wi-Fi "{ssid}"')
    elif iface:
        bits.append(f"via {iface}")
    msg = "Network status: " + ", ".join(bits) + "."
    return _ok(msg, tool="get_network_status", online=online, interface=iface, ssid=ssid)


def get_ip_address(slots: dict | None = None) -> dict[str, Any]:
    ip = _local_ip()
    others = [a for a in _all_ipv4() if a != ip]
    if ip:
        msg = f"Your local IP address is {ip}."
        if others:
            msg += f" Other addresses: {', '.join(others[:3])}."
    else:
        msg = "I couldn't determine a local IP address."
    return _ok(msg, tool="get_ip_address", ip=ip, addresses=([ip] if ip else []) + others)
