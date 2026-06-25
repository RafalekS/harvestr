# streamonitor/utils/proxy_pool.py
# Optional rotating proxy pool.
#
# Spreads status-polling + capture traffic across many exit IPs to dodge the
# per-IP rate-limits / bans / geo-blocks that bite when 1000+ bots poll cam
# sites from a single IP (e.g. one Mullvad exit). Each bot gets a STICKY proxy
# (same bot -> same exit IP for the life of its recordings, which matters
# because stream tokens/sessions are IP-bound), distributed round-robin across
# the pool.
#
# Proxies are read once, from (merged, de-duped):
#   1. a `proxies.txt` file at the project root  (one URL per line, '#' = comment)
#   2. the STRMNTR_PROXIES env var               (comma- or newline-separated)
# Each entry is a full proxy URL, e.g.
#   http://user:pass@host:port      https://host:port      socks5://host:port
#
# IMPORTANT: when the pool is EMPTY, get_proxy() returns None and every caller
# falls back to its original direct-connection behaviour. The whole feature is
# a no-op until you actually add proxies, so it carries no regression risk.

import os
import re
import threading
import itertools
from pathlib import Path
from typing import Optional, List, Dict

_lock = threading.Lock()
_proxies: Optional[List[str]] = None
_rr = None
_sticky: Dict[str, str] = {}


def _project_root() -> Path:
    # proxy_pool.py -> utils -> streamonitor -> live_backend -> <project root>
    return Path(__file__).resolve().parents[3]


def _load() -> List[str]:
    """Load + cache the proxy list once (thread-safe, idempotent)."""
    global _proxies, _rr
    if _proxies is not None:
        return _proxies
    with _lock:
        if _proxies is not None:
            return _proxies
        found: List[str] = []
        try:
            f = _project_root() / "proxies.txt"
            if f.exists():
                for line in f.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        found.append(line)
        except Exception:
            pass
        env = os.environ.get("STRMNTR_PROXIES", "") or ""
        found += [p.strip() for p in re.split(r"[,\n]", env) if p.strip()]
        seen = set()
        uniq: List[str] = []
        for p in found:
            if p not in seen:
                seen.add(p)
                uniq.append(p)
        _proxies = uniq
        _rr = itertools.cycle(uniq) if uniq else None
        return _proxies


def has_proxies() -> bool:
    return bool(_load())


def count() -> int:
    return len(_load())


def get_proxy(key: Optional[str] = None) -> Optional[str]:
    """Return a proxy URL for ``key`` or ``None`` if no pool is configured.

    Sticky: the same ``key`` always maps to the same proxy. New keys are
    handed out round-robin so the fleet spreads evenly across exit IPs.
    """
    pool = _load()
    if not pool:
        return None
    with _lock:
        if key is not None:
            existing = _sticky.get(key)
            if existing is not None:
                return existing
        proxy = next(_rr)
        if key is not None:
            _sticky[key] = proxy
        return proxy


def proxies_dict(key: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Convenience for requests/curl_cffi: {'http': p, 'https': p} or None."""
    p = get_proxy(key)
    if not p:
        return None
    return {"http": p, "https": p}
