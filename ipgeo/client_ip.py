"""Which address the request actually came from — the part that is a
security decision, not a lookup.

``X-Forwarded-For`` is written by whoever is in front of you, and anyone
can send one. Reading the leftmost entry — the idiom every snippet on the
internet shows — means a caller picks their own IP by typing it, which for
an IP-throttled or IP-geolocated endpoint is the whole ballgame. So the
default here is ``REMOTE_ADDR`` and nothing else, and trusting a header at
all is an explicit statement of how many proxies are genuinely in front:

``STAPEL_GEO["IP_TRUSTED_PROXY_DEPTH"]`` = how many hops the deployment
owns. The chain considered is ``X-Forwarded-For ++ [REMOTE_ADDR]``, and
the client is the entry ``depth`` places from its right end. Behind one
nginx that is ``1``; direct-to-gunicorn it is ``0`` (the default);
behind nginx behind a CDN it is ``2``. Counting from the RIGHT is what
makes a forged prefix inert: a caller can prepend as many entries as they
like and none of them is ever the one that gets read.

A host with a different topology replaces the whole function through
``IP_CLIENT_IP_RESOLVER`` rather than adding another header setting.
"""
from __future__ import annotations

from typing import Optional

from ..conf import geo_settings


def _split_forwarded(raw: str) -> list[str]:
    return [piece.strip() for piece in raw.split(",") if piece.strip()]


def client_ip_from_request(request) -> Optional[str]:
    """The caller's address per ``IP_TRUSTED_PROXY_DEPTH`` (see module doc)."""
    meta = getattr(request, "META", None) or {}
    remote_addr = (meta.get("REMOTE_ADDR") or "").strip()

    try:
        depth = int(geo_settings.IP_TRUSTED_PROXY_DEPTH or 0)
    except (TypeError, ValueError):
        depth = 0
    if depth <= 0:
        return remote_addr or None

    chain = _split_forwarded(meta.get("HTTP_X_FORWARDED_FOR") or "")
    if remote_addr:
        chain.append(remote_addr)
    if not chain:
        return None
    index = len(chain) - 1 - depth
    # Fewer hops arrived than the deployment claims to own: the frontmost
    # entry is the closest thing to a client, and it is still one WE saw
    # rather than one the caller chose the position of.
    return chain[max(index, 0)]


__all__ = ["client_ip_from_request"]
