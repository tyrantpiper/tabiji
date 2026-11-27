import asyncio
from concurrent.futures import ThreadPoolExecutor
import ipaddress
import re
import socket
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse
import httpx

# Dedicated 4-thread DNS bulkhead isolating blocking socket.getaddrinfo() from both the
# asyncio event loop and the default ThreadPoolExecutor used by synchronous SDKs (e.g. Supabase).
_DNS_SAFETY_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ssrf-dns")

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


_SAFE_DNS_HOSTNAME_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$"
)


def _validate_and_parse_host(url: str) -> Optional[tuple[str, str, Optional[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]]]:
    """
    Validate URL syntax, authority, port, and hostname before any allowlist or DNS decision.
    Rejects backslashes, C0/C1 control chars, whitespace in authority, userinfo (@),
    empty/non-canonical/out-of-range ports, blocked hostnames, and malformed DNS labels.
    Returns (raw_hostname, clean_host, parsed_ip_or_none) or None if invalid.
    """
    if not url or not isinstance(url, str):
        return None
    if "\\" in url or any(ord(ch) < 32 or 127 <= ord(ch) <= 159 for ch in url):
        return None
    url_str = url.strip()
    if not url_str:
        return None
    try:
        parsed = urlparse(url_str)
        port = parsed.port
    except Exception:
        return None

    if port is not None and (port < 1 or port > 65535):
        return None
    if parsed.scheme.lower() not in ("http", "https"):
        return None

    netloc = parsed.netloc or ""
    if parsed.username is not None or parsed.password is not None or "@" in netloc:
        return None
    if any(ch.isspace() for ch in netloc):
        return None

    raw_host = (parsed.hostname or "").lower()
    if not raw_host:
        return None

    is_bracketed_ipv6 = netloc.startswith("[")
    expected_host_part = f"[{raw_host}]" if is_bracketed_ipv6 else raw_host
    expected_netloc = expected_host_part if port is None else f"{expected_host_part}:{port}"
    if netloc.lower() != expected_netloc:
        return None

    clean_host = raw_host[:-1] if raw_host.endswith(".") else raw_host
    if not clean_host or clean_host in BLOCKED_HOSTNAMES:
        return None

    # Direct IPv4 / integer IP / IPv6 literal check
    try:
        if clean_host.isdigit():
            direct_ip = ipaddress.ip_address(int(clean_host))
        else:
            direct_ip = ipaddress.ip_address(clean_host)
        return raw_host, clean_host, direct_ip
    except (ValueError, OverflowError):
        if is_bracketed_ipv6 or ":" in clean_host:
            return None

    # DNS hostname validation (ASCII RFC 1123 or valid IDNA punycode)
    if clean_host.startswith(".") or clean_host.endswith(".") or ".." in clean_host:
        return None
    try:
        ascii_host = clean_host if clean_host.isascii() else clean_host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    if len(ascii_host) > 253 or not _SAFE_DNS_HOSTNAME_RE.fullmatch(ascii_host):
        return None

    return raw_host, ascii_host, None


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
        parsed_host = _validate_and_parse_host(url)
        if parsed_host is None:
            return None
        hostname, _clean_host, direct_ip = parsed_host

        if direct_ip is not None:
            if not is_ip_safe(direct_ip):
                return None
            return str(direct_ip)

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


def _classify_url_without_dns(url: str) -> Optional[bool]:
    """
    Pure-CPU SSRF pre-classification (no network/DNS I/O).
    Returns:
      - False for invalid/disallowed schemes, malformed ports/hostnames, BLOCKED_HOSTNAMES, or unsafe IP literals
      - True for whitelisted SAFE_WIKI_DOMAINS or public direct IP literals
      - None when blocking OS DNS resolution (socket.getaddrinfo) is required
    """
    parsed_host = _validate_and_parse_host(url)
    if parsed_host is None:
        return False

    _raw_host, clean_host, direct_ip = parsed_host
    if direct_ip is not None:
        return is_ip_safe(direct_ip)

    if any(clean_host == domain or clean_host.endswith("." + domain) for domain in SAFE_WIKI_DOMAINS):
        return True

    return None


def is_safe_url(url: str) -> bool:
    """
    [SAFETY] Centralized SSRF Prevention Utility.
    Checks if a URL is safe to fetch by the server.
    """
    fast_verdict = _classify_url_without_dns(url)
    if fast_verdict is not None:
        return fast_verdict
    return get_safe_ip(url.strip()) is not None


_DEFAULT_IS_SAFE_URL = is_safe_url


async def is_safe_url_async(url: str, timeout: float = 3.0) -> bool:
    """
    Non-blocking SSRF URL safety check executed on the dedicated 4-thread DNS bulkhead.
    Pure-CPU verdicts (SAFE_WIKI_DOMAINS, BLOCKED_HOSTNAMES, invalid schemes, direct IP literals)
    resolve inline on the event loop so saturated DNS workers cannot starve whitelisted traffic.
    Fails closed (returns False) on timeout or unexpected errors.
    """
    if not url or not isinstance(url, str):
        return False
    if is_safe_url is _DEFAULT_IS_SAFE_URL:
        fast_verdict = _classify_url_without_dns(url)
        if fast_verdict is not None:
            return fast_verdict
    loop = asyncio.get_running_loop()
    try:
        return bool(
            await asyncio.wait_for(
                loop.run_in_executor(_DNS_SAFETY_EXECUTOR, is_safe_url, url),
                timeout=timeout,
            )
        )
    except (asyncio.TimeoutError, Exception):
        return False


async def _enforce_request_ssrf_safety(request: httpx.Request) -> None:
    """
    Request hook to intercept outbound HTTP requests before sending,
    preventing SSRF and intranet redirects.
    """
    url_str = str(request.url)
    if not await is_safe_url_async(url_str):
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
