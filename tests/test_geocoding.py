"""Geocoder v2: provider registry, Photon/Nominatim parsing, cache+ledger,
the throttled HTTP proxy."""
import pytest
import requests
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from stapel_geo.geocoding.base import GeocoderError
from stapel_geo.geocoding.cache import response_from_json, response_to_json
from stapel_geo.geocoding.dto import GeocodeResponse
from stapel_geo.geocoding.providers import (
    BUILTIN_GEOCODERS,
    NominatimGeocoder,
    PhotonGeocoder,
    register_geocoder,
    registered_geocoders,
)
from stapel_geo.geocoding.service import get_geocoder
from stapel_geo.models import GeocodeCache
from stapel_geo.tests.fakes import CountingGeocoder, FakeGeocoder

_FAKE = {"GEOCODERS": {"fake": "stapel_geo.tests.fakes.FakeGeocoder"}, "GEOCODER": "fake"}
_FAILING = {
    "GEOCODERS": {"failing": "stapel_geo.tests.fakes.FailingGeocoder"},
    "GEOCODER": "failing",
}

_PHOTON_PAYLOAD = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [6.13, 49.61]},
            "properties": {
                "name": "Testland",
                "country": "Testland",
                "countrycode": "TL",
                "osm_key": "place",
                "osm_value": "city",
                "extraneous": "ignored",
            },
        }
    ],
}

_NOMINATIM_PAYLOAD = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "bbox": [13.08, 52.33, 13.76, 52.68],
            "geometry": {"type": "Point", "coordinates": [13.38, 52.51]},
            "properties": {
                "name": "Berlin",
                "display_name": "Berlin, Deutschland",
                "category": "place",
                "type": "city",
                "osm_type": "relation",
                "osm_id": 62422,
                "address": {
                    "city": "Berlin",
                    "state": "Berlin",
                    "country": "Deutschland",
                    "country_code": "de",
                    "postcode": "10117",
                    "road": "Unter den Linden",
                    "house_number": "1",
                },
            },
        }
    ],
}


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


class TestRegistry:
    def test_builtins_present(self):
        assert set(BUILTIN_GEOCODERS) == {"photon", "nominatim", "google", "yandex"}

    def test_default_is_photon(self):
        assert isinstance(get_geocoder(), PhotonGeocoder)

    @override_settings(STAPEL_GEO=_FAKE)
    def test_settings_merge_and_name_selection(self):
        assert isinstance(get_geocoder(), FakeGeocoder)
        assert "photon" in registered_geocoders()  # merge, not replace

    @override_settings(STAPEL_GEO={"GEOCODERS": {"photon": None}})
    def test_none_removes_a_builtin(self):
        assert "photon" not in registered_geocoders()
        with pytest.raises(ImproperlyConfigured):
            get_geocoder()  # default name "photon" was struck from the registry

    def test_runtime_registration_wins(self):
        register_geocoder("photon", "stapel_geo.tests.fakes.FakeGeocoder")
        try:
            assert isinstance(get_geocoder("photon"), FakeGeocoder)
        finally:
            register_geocoder("photon", None)
            register_geocoder("photon", BUILTIN_GEOCODERS["photon"])

    @override_settings(STAPEL_GEO={"GEOCODER": "unknown-name"})
    def test_unknown_name_is_rejected(self):
        with pytest.raises(ImproperlyConfigured):
            get_geocoder()

    @override_settings(
        STAPEL_GEO={"GEOCODERS": {"bad": "stapel_geo.tests.fakes.NotAGeocoder"},
                    "GEOCODER": "bad"}
    )
    def test_non_geocoder_is_rejected(self):
        with pytest.raises(ImproperlyConfigured):
            get_geocoder()


class TestPhotonLanguageResolution:
    def test_supported_language_passes_through(self):
        assert PhotonGeocoder().resolve_language("de") == "de"

    def test_unsupported_language_falls_back_to_english(self):
        assert PhotonGeocoder().resolve_language("xx") == "en"

    def test_none_passes_through(self):
        assert PhotonGeocoder().resolve_language(None) is None


class TestPhotonParsing:
    def _patch(self, monkeypatch, captured):
        def fake_get(url, params=None, timeout=None, headers=None):
            captured["url"] = url
            captured["params"] = params
            return _FakeResponse(_PHOTON_PAYLOAD)

        monkeypatch.setattr(requests, "get", fake_get)

    def test_search_parses_featurecollection(self, monkeypatch):
        captured = {}
        self._patch(monkeypatch, captured)
        result = PhotonGeocoder().search("Testland", lang="de", limit=5)
        assert isinstance(result, GeocodeResponse)
        assert result.type == "FeatureCollection"
        assert len(result.features) == 1
        feature = result.features[0]
        assert feature.properties.name == "Testland"
        assert feature.geometry.coordinates == [6.13, 49.61]
        # unknown provider keys are dropped, not leaked into the DTO
        assert not hasattr(feature.properties, "extraneous")
        assert captured["url"].endswith("/api")
        assert captured["params"]["q"] == "Testland"
        # None values (unset params) are stripped before the request
        assert all(v is not None for v in captured["params"].values())

    def test_reverse_hits_reverse_endpoint(self, monkeypatch):
        captured = {}
        self._patch(monkeypatch, captured)
        PhotonGeocoder().reverse(49.61, 6.13)
        assert captured["url"].endswith("/reverse")
        assert captured["params"]["lat"] == 49.61
        assert captured["params"]["lon"] == 6.13

    def test_structured_hits_structured_endpoint(self, monkeypatch):
        captured = {}
        self._patch(monkeypatch, captured)
        PhotonGeocoder().structured(city="Berlin")
        assert captured["url"].endswith("/structured")
        assert captured["params"]["city"] == "Berlin"

    def test_request_failure_raises_geocoder_error(self, monkeypatch):
        def boom(url, params=None, timeout=None, headers=None):
            raise requests.ConnectionError("refused")

        monkeypatch.setattr(requests, "get", boom)
        with pytest.raises(GeocoderError):
            PhotonGeocoder().search("x")


class TestNominatim:
    def _patch(self, monkeypatch, captured, payload=None):
        def fake_get(url, params=None, timeout=None, headers=None):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            return _FakeResponse(payload or _NOMINATIM_PAYLOAD)

        monkeypatch.setattr(requests, "get", fake_get)
        # Neutralize the 1 rps politeness sleep in tests.
        import stapel_geo.geocoding.providers as providers

        monkeypatch.setattr(providers, "_NOMINATIM_MIN_INTERVAL_S", 0.0)

    def test_search_maps_address_details(self, monkeypatch):
        captured = {}
        self._patch(monkeypatch, captured)
        result = NominatimGeocoder().search("Berlin", lang="de", limit=3)
        assert captured["url"].endswith("/search")
        assert captured["params"]["format"] == "geojson"
        assert captured["params"]["addressdetails"] == 1
        assert captured["params"]["accept-language"] == "de"
        assert "User-Agent" in captured["headers"]
        props = result.features[0].properties
        assert props.name == "Berlin"
        assert props.countrycode == "DE"
        assert props.osm_type == "R"
        assert props.street == "Unter den Linden"
        assert props.housenumber == "1"
        assert props.extent == [13.08, 52.33, 13.76, 52.68]

    def test_reverse_hits_reverse(self, monkeypatch):
        captured = {}
        self._patch(monkeypatch, captured)
        NominatimGeocoder().reverse(52.51, 13.38)
        assert captured["url"].endswith("/reverse")
        assert captured["params"]["lat"] == 52.51

    def test_structured_maps_field_names(self, monkeypatch):
        captured = {}
        self._patch(monkeypatch, captured)
        NominatimGeocoder().structured(city="Berlin", countrycode="de")
        assert captured["url"].endswith("/search")
        assert captured["params"]["city"] == "Berlin"
        assert captured["params"]["country"] == "de"

    def test_request_failure_raises_geocoder_error(self, monkeypatch):
        import stapel_geo.geocoding.providers as providers

        monkeypatch.setattr(providers, "_NOMINATIM_MIN_INTERVAL_S", 0.0)

        def boom(url, params=None, timeout=None, headers=None):
            raise requests.ConnectionError("refused")

        monkeypatch.setattr(requests, "get", boom)
        with pytest.raises(GeocoderError):
            NominatimGeocoder().search("x")


class TestKeyGatedStubs:
    @pytest.mark.parametrize("name", ["google", "yandex"])
    def test_stub_verbs_raise_with_pointer(self, name):
        provider = get_geocoder(name)
        with pytest.raises(NotImplementedError):
            provider.search("x")
        with pytest.raises(NotImplementedError):
            provider.reverse(0, 0)
        with pytest.raises(NotImplementedError):
            provider.structured(city="x")


class TestResponseRoundtrip:
    def test_dto_json_roundtrip(self):
        original = FakeGeocoder().search("Metz")
        rebuilt = response_from_json(response_to_json(original))
        assert rebuilt == original


class _RealUser:
    """Authenticated non-anonymous stand-in (satisfies IsNotAnonymousUser)."""

    is_authenticated = True
    is_anonymous = False
    pk = 424242


@pytest.mark.django_db
class TestGeocodeProxyHTTP:
    def _client(self, api_client):
        api_client.force_authenticate(user=_RealUser())
        return api_client

    def test_anonymous_is_rejected(self, api_client):
        assert api_client.get("/geo/api/v1/geocoding/search?q=x").status_code in (401, 403)

    @override_settings(STAPEL_GEO=_FAKE)
    def test_search_uses_configured_provider(self, api_client):
        resp = self._client(api_client).get("/geo/api/v1/geocoding/search?q=Metz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "FeatureCollection"
        assert body["features"][0]["properties"]["name"] == "Metz"

    @override_settings(STAPEL_GEO=_FAKE)
    def test_reverse_requires_coordinates(self, api_client):
        resp = self._client(api_client).get("/geo/api/v1/geocoding/reverse")
        assert resp.status_code == 400

    @override_settings(STAPEL_GEO=_FAKE)
    def test_reverse_returns_feature(self, api_client):
        resp = self._client(api_client).get("/geo/api/v1/geocoding/reverse?lat=49.6&lon=6.1")
        assert resp.status_code == 200
        assert resp.json()["features"][0]["geometry"]["coordinates"] == [6.1, 49.6]

    @override_settings(STAPEL_GEO=_FAILING)
    def test_provider_failure_is_502_and_ledgered(self, api_client):
        resp = self._client(api_client).get("/geo/api/v1/geocoding/search?q=x")
        assert resp.status_code == 502
        row = GeocodeCache.objects.latest("created_at")
        assert row.status == GeocodeCache.Status.ERROR
        assert row.provider == "failing"

    @override_settings(STAPEL_GEO=_FAKE)
    @pytest.mark.parametrize("collision", ["query=boom", "self=boom", "params=boom", "verb=boom"])
    def test_search_ignores_params_colliding_with_method_kwargs(self, api_client, collision):
        # M3: a query param whose name matches a provider-method parameter
        # must be dropped, not forwarded as a kwarg (which would TypeError 500).
        resp = self._client(api_client).get(f"/geo/api/v1/geocoding/search?q=paris&{collision}")
        assert resp.status_code == 200

    @override_settings(STAPEL_GEO=_FAKE)
    @pytest.mark.parametrize("collision", ["lng=boom", "self=boom", "params=boom"])
    def test_reverse_ignores_params_colliding_with_method_kwargs(self, api_client, collision):
        resp = self._client(api_client).get(
            f"/geo/api/v1/geocoding/reverse?lat=49.6&lon=6.1&{collision}"
        )
        assert resp.status_code == 200

    @override_settings(STAPEL_GEO=_FAKE)
    def test_oversized_limit_is_clamped(self, api_client):
        # M3: an out-of-range limit is clamped, not forwarded verbatim (which
        # could provoke an upstream 4xx later masked as a 502).
        resp = self._client(api_client).get("/geo/api/v1/geocoding/search?q=x&limit=999999999")
        assert resp.status_code == 200


@pytest.mark.django_db
class TestCacheAndLedger:
    @override_settings(
        STAPEL_GEO={"GEOCODERS": {"counting": "stapel_geo.tests.fakes.CountingGeocoder"},
                    "GEOCODER": "counting",
                    "GEOCODER_THROTTLE": "10000/min"}
    )
    def test_repeat_call_is_served_from_cache(self, api_client):
        CountingGeocoder.calls = 0
        api_client.force_authenticate(user=_RealUser())
        first = api_client.get("/geo/api/v1/geocoding/search?q=Metz")
        second = api_client.get("/geo/api/v1/geocoding/search?q=Metz")
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert CountingGeocoder.calls == 1  # the second answer came from cache
        statuses = list(
            GeocodeCache.objects.order_by("created_at").values_list("status", flat=True)
        )
        assert statuses == [GeocodeCache.Status.OK, GeocodeCache.Status.CACHE_HIT]

    @override_settings(
        STAPEL_GEO={"GEOCODERS": {"counting": "stapel_geo.tests.fakes.CountingGeocoder"},
                    "GEOCODER": "counting",
                    "GEOCODER_THROTTLE": "10000/min"}
    )
    def test_different_query_misses_the_cache(self, api_client):
        CountingGeocoder.calls = 0
        api_client.force_authenticate(user=_RealUser())
        api_client.get("/geo/api/v1/geocoding/search?q=Metz")
        api_client.get("/geo/api/v1/geocoding/search?q=Nancy")
        assert CountingGeocoder.calls == 2

    @override_settings(STAPEL_GEO=_FAKE)
    def test_every_call_writes_a_ledger_row(self, api_client):
        api_client.force_authenticate(user=_RealUser())
        api_client.get("/geo/api/v1/geocoding/search?q=Metz")
        row = GeocodeCache.objects.latest("created_at")
        assert row.provider == "fake"
        assert row.verb == "search"
        assert row.status == GeocodeCache.Status.OK
        assert row.response["features"][0]["properties"]["name"] == "Metz"


@pytest.mark.django_db
class TestThrottle:
    @override_settings(
        STAPEL_GEO={"GEOCODERS": {"fake": "stapel_geo.tests.fakes.FakeGeocoder"},
                    "GEOCODER": "fake",
                    "GEOCODER_THROTTLE": "2/min"}
    )
    def test_scoped_throttle_caps_the_proxy(self, api_client):
        from django.core.cache import cache

        cache.clear()  # isolate from other tests' throttle history
        api_client.force_authenticate(user=_RealUser())
        first = api_client.get("/geo/api/v1/geocoding/search?q=a")
        second = api_client.get("/geo/api/v1/geocoding/search?q=b")
        third = api_client.get("/geo/api/v1/geocoding/search?q=c")
        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
