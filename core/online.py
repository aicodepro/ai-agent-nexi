"""Connectivity check."""

import requests


def is_online(url: str = "https://www.google.com", timeout: int = 5) -> bool:
    try:
        r = requests.get(url, timeout=timeout)
        return 200 <= r.status_code < 300
    except (requests.ConnectionError, requests.Timeout, Exception):
        return False
