"""Pure geohash proximity math — no GDAL, no DB."""
from stapel_geo import geohash
from stapel_geo.tests.fakes import NearbyCandidate


class TestEncode:
    def test_encode_precision(self):
        gh = geohash.encode(49.61, 6.13, precision=6)
        assert isinstance(gh, str)
        assert len(gh) == 6

    def test_nearby_points_share_prefix(self):
        a = geohash.encode(49.6110, 6.1300, precision=7)
        b = geohash.encode(49.6111, 6.1301, precision=7)
        assert a[:5] == b[:5]


class TestDistance:
    def test_distance_is_km_and_rounded(self):
        a = geohash.encode(49.61, 6.13, precision=6)
        b = geohash.encode(49.62, 6.14, precision=6)
        d = geohash.distance_km(a, b)
        assert isinstance(d, float)
        assert d >= 0

    def test_distance_is_true_haversine_not_prefix_bucket(self):
        # 22 m apart but split across the equator (no shared geohash prefix):
        # the honest haversine reports metres, not the 20000 km a prefix
        # bucket would. (M1 regression: distance_km was a similarity bucket.)
        a = geohash.encode(0.0001, 10.0, precision=8)
        b = geohash.encode(-0.0001, 10.0, precision=8)
        assert geohash.distance_km(a, b) < 0.1
        # 2.3 km apart across the antimeridian, likewise no shared prefix.
        c = geohash.encode(0.0, 179.999, precision=8)
        d = geohash.encode(0.0, -179.98, precision=8)
        assert 1.0 < geohash.distance_km(c, d) < 5.0


class TestRanking:
    def _candidates(self):
        target = geohash.encode(49.6110, 6.1300, precision=8)
        near = NearbyCandidate("u1", "Near", "TL", geohash.encode(49.6112, 6.1302, 8))
        far = NearbyCandidate("u2", "Far", "TL", geohash.encode(48.0000, 2.0000, 8))
        missing = NearbyCandidate("u3", "NoHash", "TL", None)
        return target, [far, missing, near]

    def test_rank_orders_nearest_first(self):
        target, candidates = self._candidates()
        ranked = geohash.rank_by_proximity(target, candidates)
        names = [c.name for c, _ in ranked]
        assert names[0] == "Near"
        # candidate without a geohash sorts last with None distance
        assert ranked[-1][0].name == "NoHash"
        assert ranked[-1][1] is None


class TestNearbyExpansion:
    def test_prefix_widens_until_enough_results(self):
        target = "u0v90zzz"
        calls = []

        # Only a 3-char prefix yields two candidates; the full-length prefix
        # yields none — the algorithm must shorten the prefix to find them.
        pool = {
            "u0v": [
                NearbyCandidate("a", "A", "TL", "u0v90zzy"),
                NearbyCandidate("b", "B", "TL", "u0v9000x"),
            ]
        }

        def fetch(prefix):
            calls.append(prefix)
            return pool.get(prefix, [])

        result = geohash.nearby(target, fetch, limit=2)
        assert len(result) == 2
        # first call uses the full geohash, then it is shortened char by char
        assert calls[0] == target
        assert "u0v" in calls

    def test_limit_zero_returns_empty(self):
        assert geohash.nearby("u0v90", lambda p: [], limit=0) == []

    def test_truncates_to_limit(self):
        cands = [NearbyCandidate(str(i), str(i), "TL", "u0v90") for i in range(5)]
        result = geohash.nearby("u0v90", lambda p: cands, limit=3)
        assert len(result) == 3


def _pool_fetch(pool):
    """Mimic the ORM ``geohash__startswith`` query over a candidate pool."""

    def fetch(prefix):
        return [c for c in pool if c.geohash and c.geohash.startswith(prefix)]

    return fetch


def _cand(uuid, lat, lon):
    return NearbyCandidate(uuid, uuid, "TL", geohash.encode(lat, lon, precision=8))


class TestNearbyEdges:
    """H1: nearest neighbour across a geohash boundary must not be lost."""

    def test_antimeridian_returns_true_nearest_over_decoy(self):
        target = geohash.encode(0.0, 179.999, precision=8)
        near = _cand("near", 0.0, -179.98)   # 2.3 km across the seam
        decoy = _cand("decoy", 0.0, 168.0)   # 1334 km, shares a coarse prefix
        result = geohash.nearby(target, _pool_fetch([decoy, near]), limit=1)
        assert [c.uuid for c, _ in result] == ["near"]

    def test_antimeridian_single_candidate_not_dropped(self):
        target = geohash.encode(0.0, 179.999, precision=8)
        near = _cand("near", 0.0, -179.98)
        result = geohash.nearby(target, _pool_fetch([near]), limit=1)
        assert [c.uuid for c, _ in result] == ["near"]

    def test_pole_candidates_not_dropped(self):
        target = geohash.encode(89.96, 0.0, precision=8)
        pool = [_cand("a", 89.96, 90.0), _cand("b", 89.96, -90.0),
                _cand("c", 89.96, 179.99)]
        result = geohash.nearby(target, _pool_fetch(pool), limit=3)
        assert len(result) == 3

    def test_equator_split_returns_true_nearest_over_decoy(self):
        target = geohash.encode(0.0001, 10.0, precision=8)
        near = _cand("near", -0.0001, 10.0)  # 22 m across the equator
        decoy = _cand("decoy", 4.5, 10.0)    # 500 km, shares the 's' prefix
        result = geohash.nearby(target, _pool_fetch([decoy, near]), limit=1)
        assert [c.uuid for c, _ in result] == ["near"]
