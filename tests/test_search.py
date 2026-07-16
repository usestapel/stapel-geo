"""The search facade: backend resolution, Postgres default, Redis, stubs.

The geohash edge cases (equator/antimeridian/pole) are covered twice:
as pure math in test_geohash.py and here end-to-end through the facade
over real Location rows.
"""
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from stapel_geo.models import Location
from stapel_geo.search import get_backend
from stapel_geo.search.elasticsearch import ElasticsearchGeoSearchBackend
from stapel_geo.search.postgres import PostgresGeoSearchBackend, _radius_start_precision
from stapel_geo.search.redis import RedisGeoSearchBackend
from stapel_geo.search.solr import SolrGeoSearchBackend
from stapel_geo.tests.fakes import FakeRedisGeo


class TestFacadeResolution:
    def test_default_is_postgres(self):
        assert isinstance(get_backend(), PostgresGeoSearchBackend)

    @override_settings(STAPEL_GEO={"SEARCH_BACKEND": "stapel_geo.search.redis.RedisGeoSearchBackend"})
    def test_swap_by_settings(self):
        assert isinstance(get_backend(), RedisGeoSearchBackend)

    @override_settings(STAPEL_GEO={"SEARCH_BACKEND": "stapel_geo.tests.fakes.NotASearchBackend"})
    def test_non_backend_is_rejected(self):
        with pytest.raises(ImproperlyConfigured):
            get_backend()


@pytest.mark.django_db
class TestPostgresNearby:
    def _make(self, name, lat, lon):
        return Location.objects.create(name=name, lat=lat, lon=lon)

    def test_nearest_first_with_exact_distance(self):
        near = self._make("Near", 49.6112, 6.1302)
        self._make("Far", 48.0, 2.0)
        hits = PostgresGeoSearchBackend().nearby(49.611, 6.130, limit=2)
        assert hits[0][0] == str(near.uuid)
        assert hits[0][1] < 1.0  # true haversine km, not a prefix bucket

    def test_antimeridian_true_nearest_over_decoy(self):
        near = self._make("near", 0.0, -179.98)   # 2.3 km across the seam
        self._make("decoy", 0.0, 168.0)           # 1334 km, shares a coarse prefix
        hits = PostgresGeoSearchBackend().nearby(0.0, 179.999, limit=1)
        assert [h[0] for h in hits] == [str(near.uuid)]

    def test_equator_true_nearest_over_decoy(self):
        near = self._make("near", -0.0001, 10.0)  # 22 m across the equator
        self._make("decoy", 4.5, 10.0)            # 500 km, shares the 's' prefix
        hits = PostgresGeoSearchBackend().nearby(0.0001, 10.0, limit=1)
        assert [h[0] for h in hits] == [str(near.uuid)]

    def test_pole_candidates_not_dropped(self):
        for i, lon in enumerate([90.0, -90.0, 179.99]):
            self._make(f"p{i}", 89.96, lon)
        hits = PostgresGeoSearchBackend().nearby(89.96, 0.0, limit=3)
        assert len(hits) == 3


@pytest.mark.django_db
class TestPostgresRadius:
    def _make(self, name, lat, lon):
        return Location.objects.create(name=name, lat=lat, lon=lon)

    def test_membership_not_top_k(self):
        a = self._make("a", 49.61, 6.13)
        b = self._make("b", 49.62, 6.14)
        self._make("out", 50.5, 7.5)  # ~130 km away
        hits = PostgresGeoSearchBackend().radius(49.611, 6.131, 5.0)
        keys = [h[0] for h in hits]
        assert set(keys) == {str(a.uuid), str(b.uuid)}
        assert hits == sorted(hits, key=lambda h: h[1])
        assert all(dist <= 5.0 for _, dist in hits)

    def test_limit_caps_results(self):
        for i in range(4):
            self._make(f"c{i}", 49.61 + i * 0.001, 6.13)
        hits = PostgresGeoSearchBackend().radius(49.611, 6.131, 5.0, limit=2)
        assert len(hits) == 2

    def test_antimeridian_radius(self):
        near = self._make("near", 0.0, -179.98)
        self._make("decoy", 0.0, 168.0)
        hits = PostgresGeoSearchBackend().radius(0.0, 179.999, 10.0)
        assert [h[0] for h in hits] == [str(near.uuid)]

    def test_start_precision_covers_radius(self):
        # 5 km fits inside a precision-4 cell (±19.5 km), not precision-5 (±3.8).
        assert _radius_start_precision(5.0) == 4
        # A planet-scale radius falls back to the coarsest cell.
        assert _radius_start_precision(6000.0) == 1


@pytest.mark.django_db
class TestPostgresBbox:
    def _make(self, name, lat, lon):
        return Location.objects.create(name=name, lat=lat, lon=lon)

    def test_plain_box(self):
        inside = self._make("in", 49.6, 6.1)
        self._make("north", 52.0, 6.1)
        self._make("west", 49.6, 2.0)
        keys = PostgresGeoSearchBackend().bbox(49.0, 5.0, 50.0, 7.0)
        assert keys == [str(inside.uuid)]

    def test_antimeridian_box_wraps_lon(self):
        east = self._make("east", 0.0, 179.5)    # west of the seam
        west = self._make("west", 0.0, -179.5)   # east of the seam
        self._make("out", 0.0, 0.0)
        keys = PostgresGeoSearchBackend().bbox(-1.0, 179.0, 1.0, -179.0)
        assert set(keys) == {str(east.uuid), str(west.uuid)}

    def test_rows_without_coords_are_excluded(self):
        self._make("in", 49.6, 6.1)
        Location.objects.create(name="nocoords")
        keys = PostgresGeoSearchBackend().bbox(49.0, 5.0, 50.0, 7.0)
        assert len(keys) == 1

    def test_limit(self):
        for i in range(3):
            self._make(f"b{i}", 49.5 + i * 0.01, 6.1)
        keys = PostgresGeoSearchBackend().bbox(49.0, 5.0, 50.0, 7.0, limit=2)
        assert len(keys) == 2


class TestRedisBackend:
    def _backend(self):
        return RedisGeoSearchBackend(client=FakeRedisGeo())

    def test_nearby_is_top_k_ascending(self):
        backend = self._backend()
        backend.client().geoadd("k", (6.1302, 49.6112, "near"))
        backend.client().geoadd("k", (2.0, 48.0, "far"))
        hits = backend.nearby(49.611, 6.130, limit=1)
        assert [h[0] for h in hits] == ["near"]

    def test_radius_filters_membership(self):
        backend = self._backend()
        backend.client().geoadd("k", (6.1302, 49.6112, "in"))
        backend.client().geoadd("k", (7.5, 50.5, "out"))
        hits = backend.radius(49.611, 6.130, 5.0)
        assert [h[0] for h in hits] == ["in"]

    def test_bbox_antimeridian(self):
        backend = self._backend()
        backend.client().geoadd("k", (179.5, 0.0, "east"))
        backend.client().geoadd("k", (-179.5, 0.0, "west"))
        backend.client().geoadd("k", (0.0, 0.0, "out"))
        keys = backend.bbox(-1.0, 179.0, 1.0, -179.0)
        assert set(keys) == {"east", "west"}

    def test_index_and_remove_mirror_rows(self):
        backend = self._backend()

        class Row:
            uuid = "u-1"
            lat, lon = 49.6, 6.1

        backend.index(Row())
        assert backend.nearby(49.6, 6.1, limit=1)
        backend.remove("u-1")
        assert backend.nearby(49.6, 6.1, limit=1) == []

    def test_index_row_without_coords_removes(self):
        backend = self._backend()

        class Row:
            uuid = "u-2"
            lat, lon = 49.6, 6.1

        backend.index(Row())
        Row.lat = None
        backend.index(Row())
        assert backend.nearby(49.6, 6.1, limit=1) == []


@pytest.mark.django_db
class TestRedisSideIndexSignals:
    @override_settings(STAPEL_GEO={"SEARCH_BACKEND": "stapel_geo.search.redis.RedisGeoSearchBackend"})
    def test_sync_failure_never_breaks_saves(self):
        # No Redis server behind the default URL — the receiver must swallow
        # the connection error (the primary DB is the source of truth).
        loc = Location.objects.create(name="Safe", lat=1.0, lon=1.0)
        assert loc.pk is not None
        loc.delete()


class TestStubs:
    @pytest.mark.parametrize("backend_cls", [ElasticsearchGeoSearchBackend, SolrGeoSearchBackend])
    def test_every_verb_raises_not_implemented(self, backend_cls):
        backend = backend_cls()
        with pytest.raises(NotImplementedError):
            backend.nearby(0, 0, limit=1)
        with pytest.raises(NotImplementedError):
            backend.radius(0, 0, 1.0)
        with pytest.raises(NotImplementedError):
            backend.bbox(0, 0, 1, 1)
