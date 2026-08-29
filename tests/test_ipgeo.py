"""The IP-location verb: the seam, the proxy-trust decision, the floor.

Three things are worth a test here and the rest is plumbing:

1. **A refusal is never a 5xx and rarely a 4xx.** Every way the locator
   can fail to place somebody — a private address, an unknown range, a
   provider that raises — has to come back 200 with the fallback centre,
   because a frontend that has to branch on an error here hardcodes a
   centre instead and the setting stops mattering.
2. **X-Forwarded-For is counted from the right.** The default trusts
   nothing; a forged prefix stays inert at any depth. This is the only
   part of the feature where getting it wrong is a security bug rather
   than a wrong city.
3. **The map's opening centre is the fallback.** Not a second setting
   nobody remembers to set.
"""
from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import override_settings

from stapel_geo.ipgeo.base import IpLocator, IpLocatorError
from stapel_geo.ipgeo.client_ip import client_ip_from_request
from stapel_geo.ipgeo.dto import IpLocation, build_label
from stapel_geo.ipgeo.providers import (
    is_public_ip,
    register_ip_locator,
    registered_ip_locators,
)
from stapel_geo.ipgeo.service import locate_ip

IP_URL = "/geo/api/v1/ip"

MOSCOW = [55.7558, 37.6173]


class _FakeLocator(IpLocator):
    """Places 8.8.8.8 in Berlin and knows nothing else."""

    name = "fake"

    def locate(self, ip):
        if ip != "8.8.8.8":
            return None
        return IpLocation(
            lat=52.52,
            lon=13.405,
            source="fake",
            precision="city",
            ip_resolved=True,
            label="Berlin, Germany",
            city="Berlin",
            country="Germany",
            country_code="DE",
        )


class _BrokenLocator(IpLocator):
    name = "broken"

    def locate(self, ip):
        raise IpLocatorError("the database burned down")


class _CountingLocator(IpLocator):
    """Knows nobody, and records every address it was asked about."""

    name = "counting"
    calls: list[str] = []

    def locate(self, ip):
        self.calls.append(ip)
        return None


class _ExplodingLocator(IpLocator):
    name = "exploding"

    def locate(self, ip):
        raise RuntimeError("a provider bug, not a configuration one")


@pytest.fixture(autouse=True)
def _registered_fakes():
    register_ip_locator("fake", f"{__name__}._FakeLocator")
    register_ip_locator("broken", f"{__name__}._BrokenLocator")
    register_ip_locator("exploding", f"{__name__}._ExplodingLocator")
    register_ip_locator("counting", f"{__name__}._CountingLocator")
    cache.clear()
    yield
    register_ip_locator("fake", None)
    register_ip_locator("broken", None)
    register_ip_locator("exploding", None)
    register_ip_locator("counting", None)
    cache.clear()


def _settings(**overrides):
    base = {
        "IP_LOCATOR": "fake",
        "IP_TRUSTED_PROXY_DEPTH": 0,
        "IP_CACHE_TTL_S": 0,
        "MAP_DEFAULT_CENTER": MOSCOW,
        "GEOCODER_THROTTLE": "10000/min",
        "IP_THROTTLE": "10000/min",
        "IP_ANON_THROTTLE": "10000/min",
    }
    base.update(overrides)
    return override_settings(STAPEL_GEO=base)


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_known_address_is_placed_and_says_so(api_client):
    with _settings():
        response = api_client.get(IP_URL, REMOTE_ADDR="8.8.8.8")
    assert response.status_code == 200
    body = response.json()
    assert (body["lat"], body["lon"]) == (52.52, 13.405)
    assert body["ip_resolved"] is True
    assert body["source"] == "fake"
    assert body["precision"] == "city"
    assert body["label"] == "Berlin, Germany"


@pytest.mark.django_db
def test_unknown_address_falls_back_to_the_maps_own_centre(api_client):
    """The endpoint that cannot place you still has to open the map."""
    with _settings():
        response = api_client.get(IP_URL, REMOTE_ADDR="203.0.113.7")
    assert response.status_code == 200
    body = response.json()
    assert [body["lat"], body["lon"]] == MOSCOW
    assert body["ip_resolved"] is False
    assert body["source"] == "fallback"
    assert body["precision"] == "default"


@pytest.mark.django_db
def test_private_address_falls_back(api_client):
    with _settings():
        response = api_client.get(IP_URL, REMOTE_ADDR="127.0.0.1")
    assert response.status_code == 200
    assert response.json()["source"] == "fallback"


@pytest.mark.django_db
@pytest.mark.parametrize("locator", ["broken", "exploding"])
def test_a_broken_locator_is_a_fallback_not_a_500(api_client, locator):
    with _settings(IP_LOCATOR=locator):
        response = api_client.get(IP_URL, REMOTE_ADDR="8.8.8.8")
    assert response.status_code == 200
    assert response.json()["source"] == "fallback"


@pytest.mark.django_db
def test_no_answer_and_no_fallback_is_204_not_a_lie(api_client):
    """A deployment with no opinion says so, rather than inventing a point."""
    with _settings(MAP_DEFAULT_CENTER=None, IP_FALLBACK_CENTER=None):
        response = api_client.get(IP_URL, REMOTE_ADDR="203.0.113.7")
    assert response.status_code == 204


@pytest.mark.django_db
def test_explicit_fallback_centre_beats_the_map_default(api_client):
    with _settings(IP_FALLBACK_CENTER=[41.0, 29.0], IP_FALLBACK_LABEL="Istanbul"):
        response = api_client.get(IP_URL, REMOTE_ADDR="203.0.113.7")
    body = response.json()
    assert [body["lat"], body["lon"]] == [41.0, 29.0]
    assert body["label"] == "Istanbul"


@pytest.mark.django_db
def test_the_endpoint_answers_a_visitor_with_no_account(api_client):
    """The whole point: this is asked before anyone has signed up."""
    with _settings():
        response = api_client.get(IP_URL, REMOTE_ADDR="8.8.8.8")
    assert response.status_code == 200


@pytest.mark.django_db
def test_permissions_are_a_setting(api_client):
    with _settings(
        IP_PERMISSIONS=["stapel_core.django.api.permissions.IsNotAnonymousUser"]
    ):
        response = api_client.get(IP_URL, REMOTE_ADDR="8.8.8.8")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_map_config_publishes_the_endpoint(api_client):
    """The frontend learns the path from the server, not from a constant."""
    response = api_client.get("/geo/api/v1/map/config")
    assert response.status_code == 200
    assert response.json()["endpoints"]["ip"] == "api/v1/ip"


@pytest.mark.django_db
def test_no_coordinate_is_invented_for_a_static_locator_without_a_point(api_client):
    with _settings(IP_LOCATOR="static", IP_STATIC_POINT=None):
        response = api_client.get(IP_URL, REMOTE_ADDR="8.8.8.8")
    assert response.json()["source"] == "fallback"


@pytest.mark.django_db
def test_static_locator_answers_its_configured_point(api_client):
    with _settings(
        IP_LOCATOR="static", IP_STATIC_POINT=[43.2, 76.9], IP_STATIC_LABEL="Almaty"
    ):
        response = api_client.get(IP_URL, REMOTE_ADDR="8.8.8.8")
    body = response.json()
    assert [body["lat"], body["lon"]] == [43.2, 76.9]
    assert body["source"] == "static"
    assert body["label"] == "Almaty"
    # A configured constant is not a measurement of THIS visitor.
    assert body["ip_resolved"] is False


# ---------------------------------------------------------------------------
# Which address the request came from — the security-shaped half
# ---------------------------------------------------------------------------


class _Req:
    def __init__(self, **meta):
        self.META = meta


def test_depth_zero_ignores_x_forwarded_for_entirely():
    with _settings():
        ip = client_ip_from_request(
            _Req(REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="8.8.8.8")
        )
    assert ip == "10.0.0.1"


def test_depth_one_reads_the_entry_nginx_appended():
    with _settings(IP_TRUSTED_PROXY_DEPTH=1):
        ip = client_ip_from_request(
            _Req(REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="8.8.8.8")
        )
    assert ip == "8.8.8.8"


def test_a_forged_prefix_is_inert():
    """A caller prepending entries cannot move the one that gets read."""
    with _settings(IP_TRUSTED_PROXY_DEPTH=1):
        ip = client_ip_from_request(
            _Req(
                REMOTE_ADDR="10.0.0.1",
                HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8, 8.8.8.8",
            )
        )
    assert ip == "8.8.8.8"


def test_a_shorter_chain_than_claimed_never_indexes_off_the_end():
    with _settings(IP_TRUSTED_PROXY_DEPTH=3):
        ip = client_ip_from_request(_Req(REMOTE_ADDR="10.0.0.1"))
    assert ip == "10.0.0.1"


@pytest.mark.django_db
def test_the_endpoint_uses_the_resolver_seam(api_client):
    with _settings(IP_TRUSTED_PROXY_DEPTH=1):
        response = api_client.get(
            IP_URL, REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="8.8.8.8"
        )
    assert response.json()["ip_resolved"] is True
    assert response.json()["city"] == "Berlin"


# ---------------------------------------------------------------------------
# Registry, cache, helpers
# ---------------------------------------------------------------------------


def test_registry_merges_builtins_settings_and_runtime():
    with _settings(IP_LOCATORS={"maxmind": None, "extra": "a.b.C"}):
        registry = registered_ip_locators()
    assert "maxmind" not in registry  # removed by a None in settings
    assert registry["extra"] == "a.b.C"
    assert registry["static"].endswith("StaticIpLocator")
    assert "fake" in registry  # runtime registration wins


@pytest.mark.django_db
def test_the_answer_is_cached_per_address():
    _CountingLocator.calls.clear()
    with _settings(IP_LOCATOR="counting", IP_CACHE_TTL_S=60):
        locate_ip("8.8.8.8")
        locate_ip("8.8.8.8")
        locate_ip("9.9.9.9")
    assert _CountingLocator.calls == ["8.8.8.8", "9.9.9.9"]


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        ("8.8.8.8", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("192.168.0.1", False),
        ("::1", False),
        ("2a00:1450:4001:800::200e", True),
        ("not-an-ip", False),
        ("", False),
    ],
)
def test_is_public_ip(ip, expected):
    assert is_public_ip(ip) is expected


def test_build_label_deduplicates_a_city_that_is_its_own_region():
    assert build_label("Moscow", "Moscow", "Russia") == "Moscow, Russia"
    assert build_label(None, "", None) is None
