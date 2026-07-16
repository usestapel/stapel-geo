"""Geocode cache policy seam + the ledger-backed default.

``STAPEL_GEO["GEOCODE_CACHE_POLICY"]`` is a dotted path to a
:class:`GeocodeCachePolicy` subclass (resolved via ``import_strings``,
instantiated per call) — the same seam shape as ``stapel-agent``'s
``CACHE_POLICY``. The default, :class:`LedgerCachePolicy`, answers
lookups from the ``GeocodeCache`` ledger table (the row the service
writes for accounting anyway) within ``GEOCODE_CACHE_TTL_DAYS`` (default
30 — addresses barely move).

The ledger row is **always** written regardless of the policy — caching
is a read seam, accounting is not optional. ``store()`` exists for
policies with their own storage (Redis, ...); the default is a no-op
because the ledger row IS the default policy's storage.
"""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import timedelta

from .dto import GeocodeFeature, GeocodeGeometry, GeocodeProperties, GeocodeResponse


def query_hash(verb: str, params: dict) -> str:
    """Stable SHA-256 over the verb + canonicalized call parameters."""
    canonical = json.dumps(
        {"verb": verb, "params": params}, sort_keys=True, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def response_to_json(response: GeocodeResponse) -> dict:
    """Serialize the normalized DTO for the ledger's JSON column."""
    return asdict(response)


def response_from_json(data: dict) -> GeocodeResponse:
    """Rebuild the normalized DTO from a ledger row's JSON column."""
    features = [
        GeocodeFeature(
            type=raw.get("type", "Feature"),
            geometry=GeocodeGeometry(**(raw.get("geometry") or {"type": "Point", "coordinates": []})),
            properties=GeocodeProperties(**(raw.get("properties") or {})),
        )
        for raw in data.get("features", [])
    ]
    return GeocodeResponse(type=data.get("type", "FeatureCollection"), features=features)


class GeocodeCachePolicy(ABC):
    """Decides when to consult the geocode cache and answers lookups."""

    @abstractmethod
    def should_cache(self, verb: str) -> bool:
        """Whether *verb* ("search"/"reverse"/"structured") uses the cache."""

    @abstractmethod
    def lookup(
        self, provider: str, verb: str, query_hash: str, lang: str
    ) -> GeocodeResponse | None:
        """Return the cached response, or ``None`` on a miss.

        *provider* is part of the key — providers rank and enrich
        differently, one provider's answer must not satisfy another's
        request. *lang* likewise (localized place names).
        """

    def store(
        self,
        provider: str,
        verb: str,
        query_hash: str,
        lang: str,
        response: GeocodeResponse,
    ) -> None:
        """Persist a successful response for future lookups.

        No-op by default: the default policy reads the GeocodeCache ledger
        row the service writes anyway. Policies with external storage
        (Redis, ...) override this.
        """


class LedgerCachePolicy(GeocodeCachePolicy):
    """Stock policy: the GeocodeCache ledger + GEOCODE_CACHE_TTL_DAYS."""

    def should_cache(self, verb: str) -> bool:
        return True

    def lookup(
        self, provider: str, verb: str, query_hash: str, lang: str
    ) -> GeocodeResponse | None:
        from django.utils import timezone

        from ..conf import geo_settings
        from ..models import GeocodeCache

        ttl_days = int(geo_settings.GEOCODE_CACHE_TTL_DAYS)
        row = (
            GeocodeCache.objects.filter(
                provider=provider,
                verb=verb,
                query_hash=query_hash,
                lang=lang or "",
                status=GeocodeCache.Status.OK,
                response__isnull=False,
                created_at__gte=timezone.now() - timedelta(days=ttl_days),
            )
            .order_by("-created_at")
            .first()
        )
        if row is None:
            return None
        return response_from_json(row.response)


def write_ledger(
    *,
    provider: str,
    verb: str,
    query_hash: str,
    lang: str,
    status: str,
    duration_ms: int,
    response: GeocodeResponse | None = None,
) -> None:
    """Append one accounting row (spend visibility per provider/verb).

    Called on every proxied geocoding call — ok, error and cache_hit
    alike — mirroring how PromptLog gives per-provider LLM spend. Never
    raises: a ledger failure must not break the user-facing response.
    """
    from ..models import GeocodeCache

    try:
        GeocodeCache.objects.create(
            provider=provider,
            verb=verb,
            query_hash=query_hash,
            lang=lang or "",
            status=status,
            duration_ms=duration_ms,
            response=response_to_json(response) if response is not None else None,
        )
    except Exception:  # noqa: BLE001 — accounting must not mask the answer
        import logging

        logging.getLogger(__name__).warning(
            "GeocodeCache ledger write failed", exc_info=True
        )


__all__ = [
    "GeocodeCachePolicy",
    "LedgerCachePolicy",
    "query_hash",
    "response_to_json",
    "response_from_json",
    "write_ledger",
]
