"""Geocoder provider seam: PhotonGeocoder parsing, the GEOCODER swap, HTTP proxy."""
import pytest
import requests
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from stapel_geo.geocoding.base import GeocoderError
from stapel_geo.geocoding.dto import GeocodeResponse
from stapel_geo.geocoding.providers import PhotonGeocoder
from stapel_geo.geocoding.service import get_geocoder
from stapel_geo.tests.fakes import FakeGeocoder

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


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


class TestPhotonLanguageResolution:
    def test_supported_language_passes_through(self):
        assert PhotonGeocoder().resolve_language("de") == "de"

    def test_unsupported_language_falls_back_to_english(self):
        assert PhotonGeocoder().resolve_language("xx") == "en"

    def test_none_passes_through(self):
        assert PhotonGeocoder().resolve_language(None) is None


class TestPhotonParsing:
    def _patch(self, monkeypatch, captured):
        def fake_get(url, params=None, timeout=None):
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
        def boom(url, params=None, timeout=None):
            raise requests.ConnectionError("refused")

        monkeypatch.setattr(requests, "get", boom)
        with pytest.raises(GeocoderError):
            PhotonGeocoder().search("x")


class TestGeocoderSeam:
    def test_default_is_photon(self):
        assert isinstance(get_geocoder(), PhotonGeocoder)

    @override_settings(STAPEL_GEO={"GEOCODER": "stapel_geo.tests.fakes.FakeGeocoder"})
    def test_dotted_path_swap(self):
        assert isinstance(get_geocoder(), FakeGeocoder)

    @override_settings(STAPEL_GEO={"GEOCODER": "stapel_geo.tests.fakes.NotAGeocoder"})
    def test_non_geocoder_is_rejected(self):
        with pytest.raises(ImproperlyConfigured):
            get_geocoder()


class _RealUser:
    """Authenticated non-anonymous stand-in (satisfies IsNotAnonymousUser)."""

    is_authenticated = True
    is_anonymous = False


class TestGeocodeProxyHTTP:
    def _client(self, api_client):
        api_client.force_authenticate(user=_RealUser())
        return api_client

    def test_anonymous_is_rejected(self, api_client):
        assert api_client.get("/geo/geocoding/search?q=x").status_code in (401, 403)

    @override_settings(STAPEL_GEO={"GEOCODER": "stapel_geo.tests.fakes.FakeGeocoder"})
    def test_search_uses_configured_provider(self, api_client):
        resp = self._client(api_client).get("/geo/geocoding/search?q=Metz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["type"] == "FeatureCollection"
        assert body["features"][0]["properties"]["name"] == "Metz"

    @override_settings(STAPEL_GEO={"GEOCODER": "stapel_geo.tests.fakes.FakeGeocoder"})
    def test_reverse_requires_coordinates(self, api_client):
        resp = self._client(api_client).get("/geo/geocoding/reverse")
        assert resp.status_code == 400

    @override_settings(STAPEL_GEO={"GEOCODER": "stapel_geo.tests.fakes.FakeGeocoder"})
    def test_reverse_returns_feature(self, api_client):
        resp = self._client(api_client).get("/geo/geocoding/reverse?lat=49.6&lon=6.1")
        assert resp.status_code == 200
        assert resp.json()["features"][0]["geometry"]["coordinates"] == [6.1, 49.6]

    @override_settings(STAPEL_GEO={"GEOCODER": "stapel_geo.tests.fakes.FailingGeocoder"})
    def test_provider_failure_is_502(self, api_client):
        resp = self._client(api_client).get("/geo/geocoding/search?q=x")
        assert resp.status_code == 502

    @override_settings(STAPEL_GEO={"GEOCODER": "stapel_geo.tests.fakes.FakeGeocoder"})
    @pytest.mark.parametrize("collision", ["query=boom", "self=boom", "params=boom"])
    def test_search_ignores_params_colliding_with_method_kwargs(self, api_client, collision):
        # M3: a query param whose name matches a provider-method parameter
        # must be dropped, not forwarded as a kwarg (which would TypeError 500).
        resp = self._client(api_client).get(f"/geo/geocoding/search?q=paris&{collision}")
        assert resp.status_code == 200

    @override_settings(STAPEL_GEO={"GEOCODER": "stapel_geo.tests.fakes.FakeGeocoder"})
    @pytest.mark.parametrize("collision", ["lng=boom", "self=boom", "params=boom"])
    def test_reverse_ignores_params_colliding_with_method_kwargs(self, api_client, collision):
        resp = self._client(api_client).get(
            f"/geo/geocoding/reverse?lat=49.6&lon=6.1&{collision}"
        )
        assert resp.status_code == 200

    @override_settings(STAPEL_GEO={"GEOCODER": "stapel_geo.tests.fakes.FakeGeocoder"})
    def test_oversized_limit_is_clamped(self, api_client):
        # M3: an out-of-range limit is clamped, not forwarded verbatim (which
        # could provoke an upstream 4xx later masked as a 502).
        resp = self._client(api_client).get("/geo/geocoding/search?q=x&limit=999999999")
        assert resp.status_code == 200
