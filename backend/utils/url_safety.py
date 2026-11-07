import ipaddress
import re
import socket
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse
import httpx

# [NEW] Phase 5.4: Domain Whitelist (Bypass blocking DNS checks for known safe hosts)
SAFE_WIKI_DOMAINS: List[str] = [
    "wikipedia.org",
    "wikidata.org",
    "wikivoyage.org",
    "wikimedia.org",
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "0",
    "::1",
    "metadata.google.internal",
    "instance-data",
    "host.docker.internal",
}

BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class SSRFSecurityError(ValueError):
    """Raised when an outbound HTTP request targets a disallowed or private destination."""
    pass


def is_ip_safe(ip: Union[str, ipaddress.IPv4Address, ipaddress.IPv6Address]) -> bool:
    """
    Checks if an IP address is safe for outbound communication.
    Blocks loopback, private, link-local, multicast, metadata, CGNAT, etc.
    """
    try:
        if isinstance(ip, str):
            clean_ip = ip.strip("[] \t\r\n")
            ip_obj = ipaddress.ip_address(clean_ip)
        else:
            ip_obj = ip

        if getattr(ip_obj, "ipv4_mapped", None):
            ip_obj = ip_obj.ipv4_mapped

        if (
            ip_obj.is_loopback
            or ip_obj.is_private
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        ):
            return False

        for net in BLOCKED_NETWORKS:
            if ip_obj in net:
                return False

        return True
    except Exception:
        return False


def get_safe_ip(url: str) -> Optional[str]:
    """
    [SAFETY] Anti-DNS-Rebinding IP Resolver.
    Resolves the hostname and checks if the IP is safe (public).
    Returns the IP string if safe, otherwise returns None.
    """
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ["http", "https"]:
            return None

        hostname = parsed.hostname
        if not hostname:
            return None

        clean_host = hostname.lower().rstrip(".")
        if not clean_host or clean_host in BLOCKED_HOSTNAMES:
            return None

        # Check if hostname itself is directly an IP literal or integer IP
        try:
            if clean_host.isdigit():
                direct_ip = ipaddress.ip_address(int(clean_host))
            else:
                direct_ip = ipaddress.ip_address(clean_host.strip("[]"))
            if not is_ip_safe(direct_ip):
                return None
            return str(direct_ip)
        except (ValueError, OverflowError):
            pass

        # Resolve hostname to check real IP
        try:
            addr_infos = socket.getaddrinfo(hostname, None)
            if not addr_infos:
                return None
            for info in addr_infos:
                resolved_ip = info[4][0]
                if not is_ip_safe(resolved_ip):
                    return None
            return addr_infos[0][4][0]
        except socket.gaierror:
            return None
    except Exception:
        return None


def is_safe_url(url: str) -> bool:
    """
    [SAFETY] Centralized SSRF Prevention Utility.
    Checks if a URL is safe to fetch by the server.
    """
    if not url or not isinstance(url, str):
        return False

    url_str = url.strip()
    try:
        parsed = urlparse(url_str.lower())
    except Exception:
        return False

    if parsed.scheme not in ["http", "https"]:
        return False

    hostname = parsed.hostname or ""
    clean_host = hostname.lower().rstrip(".")
    if not clean_host or clean_host in BLOCKED_HOSTNAMES:
        return False

    if any(clean_host == domain or clean_host.endswith("." + domain) for domain in SAFE_WIKI_DOMAINS):
        return True

    return get_safe_ip(url_str) is not None


async def _enforce_request_ssrf_safety(request: httpx.Request) -> None:
    """
    Request hook to intercept outbound HTTP requests before sending,
    preventing SSRF and intranet redirects.
    """
    url_str = str(request.url)
    if not is_safe_url(url_str):
        raise SSRFSecurityError(f"[SSRF Blocked] Outbound connection to {url_str} targets a disallowed or private destination.")


def create_safe_client(**kwargs: Any) -> httpx.AsyncClient:
    """
    Factory function creating an httpx.AsyncClient equipped with SSRF enforcement.
    Uses request event hooks to intercept and validate target URLs before sending,
    preventing intranet redirects and unauthorized destinations.
    """
    event_hooks = kwargs.pop("event_hooks", None)
    event_hooks = dict(event_hooks) if event_hooks else {}
    req_hooks = list(event_hooks.get("request", []))
    if _enforce_request_ssrf_safety not in req_hooks:
        req_hooks.insert(0, _enforce_request_ssrf_safety)
    event_hooks["request"] = req_hooks
    return httpx.AsyncClient(event_hooks=event_hooks, **kwargs)
