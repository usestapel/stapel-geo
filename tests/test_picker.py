"""The location-picker surface: display lines, the one-call resolve, the basemap.

The defect these cover: a listing composer shipping two raw ``latitude`` /
``longitude`` fields because the library handed over coordinates and left
the human-facing half — an address to read, a map to point at, a position
to detect — to every product to reinvent.

The Photon HTTP boundary is always mocked (``requests.get`` monkeypatched
or a registered fake provider); no test reaches a live instance.
"""
import pytest
import requests
from django.test import override_settings

from stapel_geo.basemap import build_map_config
from stapel_geo.geocoding.dto import GeocodeProperties
from stapel_geo.geocoding.format import format_address, street_line
from stapel_geo.geocoding.providers import PhotonGeocoder
from stapel_geo.geocoding.service import resolve_point
from stapel_geo.models import Location

_FAKE = {
    "GEOCODERS": {"fake": "stapel_geo.tests.fakes.FakeGeocoder"},
    "GEOCODER": "fake",
    "GEOCODER_THROTTLE": "10000/min",
}
_FAILING = {
    "GEOCODERS": {"failing": "stapel_geo.tests.fakes.FailingGeocoder"},
    "GEOCODER": "failing",
    "GEOCODER_THROTTLE": "10000/min",
}


class _RealUser:
    """Authenticated non-anonymous stand-in (satisfies IsNotAnonymousUser)."""

    is_authenticated = True
    is_anonymous = False
    pk = 424242


def _authed(api_client):
    api_client.force_authenticate(user=_RealUser())
    return api_client


# ---------------------------------------------------------------------------
# The display line
# ---------------------------------------------------------------------------


class TestAddressFormatting:
    def test_street_order_follows_the_country_not_english_habit(self):
        ru = GeocodeProperties(street="Тверская улица", housenumber="7", countrycode="RU")
        us = GeocodeProperties(street="Tverskaya Street", housenumber="7", countrycode="US")
        assert street_line(ru) == "Тверская улица, 7"
        assert street_line(us) == "7 Tverskaya Street"

    def test_full_line_is_ordered_and_deduplicated(self):
        props = GeocodeProperties(
            name="Центральный телеграф",
            street="Тверская улица",
            housenumber="7",
            city="Москва",
            state="Москва",
            country="Россия",
            countrycode="RU",
        )
        # state repeats city -> it is dropped, the line does not stutter.
        assert format_address(props) == (
            "Центральный телеграф, Тверская улица, 7, Москва, Россия"
        )

    def test_a_place_name_that_is_just_the_city_is_dropped(self):
        props = GeocodeProperties(name="Berlin", city="Berlin", country="Germany")
        assert format_address(props) == "Berlin, Germany"

    def test_district_stands_in_when_there_is_no_street(self):
        props = GeocodeProperties(district="Mitte", city="Berlin", country="Germany")
        assert format_address(props) == "Mitte, Berlin, Germany"

    def test_postcode_is_opt_in(self):
        props = GeocodeProperties(postcode="10117", city="Berlin", country="Germany")
        assert format_address(props) == "Berlin, Germany"
        with override_settings(STAPEL_GEO={"ADDRESS_INCLUDE_POSTCODE": True}):
            assert format_address(props) == "10117, Berlin, Germany"

    def test_empty_components_produce_an_empty_line_not_a_crash(self):
        assert format_address(GeocodeProperties()) == ""

    @override_settings(
        STAPEL_GEO={"ADDRESS_FORMATTER": "stapel_geo.tests.fakes.shouty_formatter"}
    )
    def test_formatter_is_a_settings_seam(self):
        from stapel_geo.geocoding.format import apply_formatter

        props = apply_formatter(GeocodeProperties(city="Berlin"))
        assert props.formatted == "BERLIN"

    @override_settings(
        STAPEL_GEO={"ADDRESS_FORMATTER": "stapel_geo.tests.fakes.exploding_formatter"}
    )
    def test_a_broken_formatter_costs_the_label_not_the_result(self):
        from stapel_geo.geocoding.format import apply_formatter

        props = apply_formatter(GeocodeProperties(city="Berlin"))
        assert props.formatted is None
        assert props.city == "Berlin"


class TestFormattedReachesTheWire:
    def test_photon_features_carry_a_display_line(self, monkeypatch):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [37.61, 55.75]},
                    "properties": {
                        "name": "Центральный телеграф",
                        "street": "Тверская улица",
                        "housenumber": "7",
                        "city": "Москва",
                        "country": "Россия",
                        "countrycode": "RU",
                    },
                }
            ],
        }
        monkeypatch.setattr(
            requests,
            "get",
            lambda url, params=None, timeout=None, headers=None: _Resp(payload),
        )
        result = PhotonGeocoder().search("Тверская 7", lang="ru")
        assert result.features[0].properties.formatted == (
            "Центральный телеграф, Тверская улица, 7, Москва, Россия"
        )


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = "{}"

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"status {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self._payload


# ---------------------------------------------------------------------------
# Photon call shaping — the map's own narrowings
# ---------------------------------------------------------------------------


class TestPhotonMapParameters:
    def _capture(self, monkeypatch):
        captured = {}

        def fake_get(url, params=None, timeout=None, headers=None):
            captured["url"] = url
            captured["params"] = params
            return _Resp({"type": "FeatureCollection", "features": []})

        monkeypatch.setattr(requests, "get", fake_get)
        return captured

    def test_bbox_is_rendered_in_photon_order(self, monkeypatch):
        captured = self._capture(monkeypatch)
        PhotonGeocoder().search("x", bbox=[19.6, 41.2, 190.0, 81.9])
        assert captured["params"]["bbox"] == "19.6,41.2,190.0,81.9"

    def test_a_prerendered_bbox_string_passes_through(self, monkeypatch):
        captured = self._capture(monkeypatch)
        PhotonGeocoder().search("x", bbox="1,2,3,4")
        assert captured["params"]["bbox"] == "1,2,3,4"

    def test_viewport_bias_reaches_the_provider(self, monkeypatch):
        captured = self._capture(monkeypatch)
        PhotonGeocoder().search("x", bias_lat=55.75, bias_lon=37.61, bias_scale=0.4, zoom=14)
        assert captured["params"]["lat"] == 55.75
        assert captured["params"]["lon"] == 37.61
        assert captured["params"]["location_bias_scale"] == 0.4
        assert captured["params"]["zoom"] == 14

    def test_unset_narrowings_are_not_sent_at_all(self, monkeypatch):
        captured = self._capture(monkeypatch)
        PhotonGeocoder().search("x")
        assert "bbox" not in captured["params"]
        assert "lat" not in captured["params"]

    def test_reverse_radius_is_forwarded(self, monkeypatch):
        captured = self._capture(monkeypatch)
        PhotonGeocoder().reverse(55.75, 37.61, radius_km=0.5)
        assert captured["params"]["radius"] == 0.5

    def test_effective_language_is_echoed_back(self, monkeypatch):
        self._capture(monkeypatch)
        # "ru" is not in the default PHOTON_LANGUAGES, so it clamps — and
        # the caller can SEE that it clamped instead of guessing.
        assert PhotonGeocoder().search("x", lang="ru").lang == "default"
        assert PhotonGeocoder().search("x", lang="de").lang == "de"

    def test_an_upstream_error_body_survives_into_the_message(self, monkeypatch):
        from stapel_geo.geocoding.base import GeocoderError

        body = '{"lang":[{"message":"Language is not supported."}]}'

        def fake_get(url, params=None, timeout=None, headers=None):
            resp = _Resp({}, status=400)
            resp.text = body
            return resp

        monkeypatch.setattr(requests, "get", fake_get)
        with pytest.raises(GeocoderError) as exc:
            PhotonGeocoder().search("x")
        assert "Language is not supported" in str(exc.value)


# ---------------------------------------------------------------------------
# resolve — the one-call round trip
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestResolvePoint:
    @override_settings(STAPEL_GEO=_FAKE)
    def test_one_call_answers_everything_a_confirm_step_needs(self):
        resolution = resolve_point(49.61, 6.13)
        assert (resolution.lat, resolution.lon) == (49.61, 6.13)
        assert resolution.geohash  # what a consumer stores
        assert resolution.formatted  # what the human reads
        assert resolution.address.city == "Testville"  # what the form fills
        assert resolution.feature is not None

    @override_settings(STAPEL_GEO=_FAKE)
    def test_the_tree_is_not_queried_unless_asked(self):
        Location.objects.create(name="Near", country="TL", lat=49.6112, lon=6.1302)
        assert resolve_point(49.61, 6.13).nearest == []

    @override_settings(STAPEL_GEO=_FAKE)
    def test_nearest_returns_known_locations_when_asked(self):
        near = Location.objects.create(name="Near", country="TL", lat=49.6112, lon=6.1302)
        resolution = resolve_point(49.61, 6.13, nearest=3)
        assert [row.uuid for row in resolution.nearest] == [str(near.uuid)]
        assert resolution.nearest[0].distance_km is not None

    @override_settings(STAPEL_GEO=_FAKE)
    def test_nearest_is_capped_by_settings(self):
        for index in range(4):
            Location.objects.create(name=f"L{index}", lat=49.61 + index / 1000, lon=6.13)
        with override_settings(STAPEL_GEO={**_FAKE, "RESOLVE_NEAREST_MAX": 2}):
            assert len(resolve_point(49.61, 6.13, nearest=99).nearest) == 2

    @override_settings(
        STAPEL_GEO={
            "GEOCODERS": {"empty": "stapel_geo.tests.fakes.EmptyGeocoder"},
            "GEOCODER": "empty",
        }
    )
    def test_a_point_with_no_address_is_an_answer_not_an_error(self):
        # The middle of the sea has coordinates too. The picker shows
        # "no address here"; it does not show a failure.
        resolution = resolve_point(0.0, 0.0)
        assert resolution.formatted is None
        assert resolution.feature is None
        assert resolution.geohash


@pytest.mark.django_db
class TestResolveHTTP:
    @override_settings(STAPEL_GEO=_FAKE)
    def test_endpoint_answers_the_browser_position(self, api_client):
        resp = _authed(api_client).get("/geo/api/v1/geocoding/resolve?lat=49.61&lon=6.13")
        assert resp.status_code == 200
        body = resp.json()
        assert body["lat"] == 49.61
        assert body["geohash"]
        assert body["formatted"]
        assert body["address"]["city"] == "Testville"
        assert body["alternatives"] == []
        assert body["nearest"] == []

    @override_settings(STAPEL_GEO=_FAKE)
    def test_missing_coordinates_is_400(self, api_client):
        resp = _authed(api_client).get("/geo/api/v1/geocoding/resolve")
        assert resp.status_code == 400
        assert resp.json()["localizable_error"] == "error.400.lat_lon_required"

    @override_settings(STAPEL_GEO=_FAKE)
    @pytest.mark.parametrize("query", ["lat=nan&lon=0", "lat=91&lon=0", "lat=0&lon=181"])
    def test_impossible_coordinates_are_400_not_500(self, api_client, query):
        resp = _authed(api_client).get(f"/geo/api/v1/geocoding/resolve?{query}")
        assert resp.status_code == 400

    @override_settings(STAPEL_GEO=_FAILING)
    def test_provider_failure_is_502(self, api_client):
        resp = _authed(api_client).get("/geo/api/v1/geocoding/resolve?lat=1&lon=1")
        assert resp.status_code == 502
        assert resp.json()["localizable_error"] == "error.502.geocoder_unavailable"

    def test_anonymous_is_rejected_by_default(self, api_client):
        resp = api_client.get("/geo/api/v1/geocoding/resolve?lat=1&lon=1")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# bbox / bias at the HTTP layer
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSearchNarrowingHTTP:
    @override_settings(STAPEL_GEO=_FAKE)
    def test_malformed_bbox_is_refused_not_ignored(self, api_client):
        # Silently dropping it would widen a search the caller believed
        # it had narrowed — the worst possible way to be wrong here.
        resp = _authed(api_client).get("/geo/api/v1/geocoding/search?q=x&bbox=1,2,3")
        assert resp.status_code == 400
        assert resp.json()["localizable_error"] == "error.400.invalid_bbox"

    @override_settings(STAPEL_GEO=_FAKE)
    @pytest.mark.parametrize(
        "bbox", ["a,b,c,d", "0,-91,10,10", "0,10,10,0", "0,0,200,10"]
    )
    def test_out_of_range_bbox_values_are_refused(self, api_client, bbox):
        resp = _authed(api_client).get(f"/geo/api/v1/geocoding/search?q=x&bbox={bbox}")
        assert resp.status_code == 400

    @override_settings(STAPEL_GEO=_FAKE)
    def test_an_antimeridian_bbox_is_accepted(self, api_client):
        # min_lon > max_lon is a wrap, the same convention geo.bbox uses.
        resp = _authed(api_client).get(
            "/geo/api/v1/geocoding/search?q=x&bbox=170,-10,-170,10"
        )
        assert resp.status_code == 200

    @override_settings(STAPEL_GEO=_FAKE)
    def test_bad_bias_is_400(self, api_client):
        resp = _authed(api_client).get(
            "/geo/api/v1/geocoding/search?q=x&bias_lat=abc&bias_lon=1"
        )
        assert resp.status_code == 400

    def test_the_products_operating_area_is_inherited_from_settings(self, monkeypatch):
        """MAP_BBOX applies without every caller remembering to send it."""
        captured = {}

        def fake_get(url, params=None, timeout=None, headers=None):
            captured["params"] = params
            return _Resp({"type": "FeatureCollection", "features": []})

        monkeypatch.setattr(requests, "get", fake_get)
        with override_settings(
            STAPEL_GEO={
                "MAP_BBOX": [19.6, 41.2, 190.0, 81.9],
                "GEOCODER_THROTTLE": "10000/min",
            }
        ):
            from rest_framework.test import APIClient

            client = APIClient()
            client.force_authenticate(user=_RealUser())
            resp = client.get("/geo/api/v1/geocoding/search?q=x")
        assert resp.status_code == 200
        assert captured["params"]["bbox"] == "19.6,41.2,190.0,81.9"


# ---------------------------------------------------------------------------
# The permission seam
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestGeocoderPermissionSeam:
    @override_settings(
        STAPEL_GEO={
            **_FAKE,
            "GEOCODER_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
            "GEOCODER_ANON_THROTTLE": "10000/min",
        }
    )
    def test_a_public_search_page_can_be_opened_from_settings(self, api_client):
        resp = api_client.get("/geo/api/v1/geocoding/search?q=Metz")
        assert resp.status_code == 200

    @override_settings(
        STAPEL_GEO={
            **_FAKE,
            "GEOCODER_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
            "GEOCODER_ANON_THROTTLE": "1/min",
        }
    )
    def test_an_opened_proxy_still_has_a_brake(self, api_client):
        from django.core.cache import cache

        cache.clear()
        assert api_client.get("/geo/api/v1/geocoding/search?q=a").status_code == 200
        assert api_client.get("/geo/api/v1/geocoding/search?q=b").status_code == 429
        cache.clear()

    @override_settings(
        STAPEL_GEO={
            **_FAKE,
            "GEOCODER_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
            "GEOCODER_ANON_THROTTLE": "1/min",
            "GEOCODER_THROTTLE": "10000/min",
        }
    )
    def test_an_identified_caller_gets_the_authenticated_rate(self, api_client):
        from django.core.cache import cache

        cache.clear()
        client = _authed(api_client)
        assert client.get("/geo/api/v1/geocoding/search?q=a").status_code == 200
        assert client.get("/geo/api/v1/geocoding/search?q=b").status_code == 200
        cache.clear()


# ---------------------------------------------------------------------------
# The basemap
# ---------------------------------------------------------------------------


class TestMapConfig:
    def test_attribution_is_present_and_flagged_as_obligatory(self):
        config = build_map_config()
        assert config.tiles.attribution_html
        assert config.tiles.attribution_text
        assert config.tiles.requires_attribution is True
        assert config.tiles.policy_url

    def test_defaults_are_a_usable_map(self):
        config = build_map_config()
        assert "{z}" in config.tiles.url_template
        assert config.tiles.min_zoom < config.tiles.max_zoom
        assert config.default_zoom < config.picked_zoom
        assert config.search_min_chars >= 1
        assert config.search_debounce_ms > 0
        assert set(config.endpoints) >= {"search", "reverse", "resolve"}

    @override_settings(
        STAPEL_GEO={
            "MAP_TILE_URL": "https://tiles.example.com/{z}/{x}/{y}.png",
            "MAP_DEFAULT_CENTER": [55.7558, 37.6173],
            "MAP_BBOX": [19.6, 41.2, 190.0, 81.9],
            "MAP_GEOLOCATION": False,
        }
    )
    def test_every_field_is_a_settings_seam(self):
        config = build_map_config()
        assert config.tiles.url_template == "https://tiles.example.com/{z}/{x}/{y}.png"
        assert config.default_center == [55.7558, 37.6173]
        assert config.bbox == [19.6, 41.2, 190.0, 81.9]
        assert config.geolocation is False


@pytest.mark.django_db
class TestMapConfigHTTP:
    def test_a_map_renders_before_login(self, api_client):
        # An unauthenticated visitor must be able to draw the map; only
        # the geocoding calls behind it are guarded.
        resp = api_client.get("/geo/api/v1/map/config")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tiles"]["requires_attribution"] is True
        assert body["tiles"]["attribution_text"]
        assert body["endpoints"]["resolve"] == "api/v1/geocoding/resolve"
        assert body["geohash_precision"] == 8
