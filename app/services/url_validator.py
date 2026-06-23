import ipaddress
import socket
from urllib.parse import urlparse


BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "[::]",
    "[::1]",
    "metadata.google.internal",
    "169.254.169.254",
}

BLOCKED_EXTENSIONS = {
    ".pdf", ".zip", ".exe", ".dmg", ".mp4",
    ".mp3", ".avi", ".mov", ".png", ".jpg",
    ".jpeg", ".gif", ".svg", ".ico",
}


def validate_public_url(url: str) -> None:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https URLs are allowed.")

    if not parsed.hostname:
        raise ValueError("Invalid URL: missing hostname.")

    hostname = parsed.hostname.lower()

    if hostname in BLOCKED_HOSTS:
        raise ValueError("Local/internal URLs are not allowed.")

    path_lower = parsed.path.lower()
    for ext in BLOCKED_EXTENSIONS:
        if path_lower.endswith(ext):
            raise ValueError(f"File URLs ({ext}) are not supported. Only web pages.")

    try:
        ip = ipaddress.ip_address(socket.gethostbyname(hostname))
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            raise ValueError("Private/internal IP addresses are not allowed.")
    except ValueError:
        raise
    except Exception:
        pass