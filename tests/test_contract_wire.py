"""Every response body the contract declares is a body the views actually send.

``docs/schema.json`` is emitted from the views' ``@extend_schema``
annotations (and, for the ``ModelViewSet``, from the serializer classes the
generator infers). An annotation is a CLAIM: it says what the view returns,
and the generator has no way to check it against the method body.
``tests/test_contract.py`` compares the committed document against a FRESH
EMISSION of the same annotations — it proves the file is not stale, and
nothing else, because both sides come from the claim. stapel-alerts 0.2.0
shipped ``GET /issues`` declared as ``Issue[]`` while the wire carried
``{count, offset, limit, results}``: the drift gate was green and the
frontend pair rendered ``undefined``.

This is the gate the generator cannot be: it performs every operation the
committed schema declares with a JSON response body, and validates the body
it gets against the schema it was promised.

Rules this file holds itself to:

* an operation with a declared JSON response and no entry in ``RECIPES``
  FAILS LOUDLY — a gate that quietly covers fifteen of sixteen rows is the
  family of green that proves nothing;
* a path parameter the gate cannot fill fails at the point of substitution,
  naming the operation;
* the operations that genuinely cannot be driven in-process are listed by
  name in ``UNDRIVABLE`` with a one-line reason each. That list is asserted
  to be exactly current: a stale entry, or a missing reason, fails;
* a collection that comes back empty fails in the populated pass — an empty
  array validates against any item schema, so an empty answer is a check that
  looked at nothing. That holds for the arrays NESTED in an object too
  (``GeocodeResponse.features``), which ``COLLECTION_KEYS`` names;
* a body is checked in BOTH directions. ``jsonschema`` answers "is every
  declared property satisfied"; an OpenAPI object schema without
  ``additionalProperties`` also claims to ENUMERATE the body, and a key the
  document never mentions is a key no generated client has a field for. That
  half is :func:`_undeclared_keys`;
* every read is driven a SECOND time in its emptiest legal state
  (``EMPTY_STATE``). Every null finding in the first wave of this gate was
  there.

Runs on every interpreter: it reads the committed schema and never emits.

THE MOUNT. ``codegen_urls.py`` mounts ``geo/`` and the module's own
``urls.py`` contributes ``api/v1/``, so the document is written against
``/geo/api/v1/…``. ``tests/urls.py`` mounts the same thing — geo is one of
the libraries whose suite was already looking where its document describes,
unlike five of the first eight in this wave. The emission mount is declared
here anyway, because ``test_every_declared_path_resolves_under_this_urlconf``
can only hold if the urlconf under test is this file's own.

What it found on its first run: 16 of 16 operations driven, both states, 0
red. Every declared body is a body the views send.

The one claim that looked wrong and is not: ``LocationCompact`` declares
``distance_km`` REQUIRED (drf-spectacular lists every read-only field as
required, because a read-only field is by definition always present), while
only the two ``nearby-*`` reads annotate a distance onto the row. The three
plain tree reads answer ``"distance_km": null`` rather than omitting the key
— ``LocationCompactSerializer`` declares the field ``allow_null=True``
(serializers.py:12), and DRF's ``Field.get_attribute`` returns ``None`` for a
missing attribute when the field allows null, in preference to raising
``SkipField``. Required and nullable, sent as null: the document and the wire
agree. It is written down here because the first draft of this file recorded
it as a defect, and the XPASS is what said otherwise.

Everything else holds too, in both states and in both directions —
including every ``nullable`` field of ``GeocodeProperties``,
``PlaceResolution``, ``IpLocation``, ``MapConfig`` and ``Location``, and with
no operation answering a key the contract fails to mention (the check that
caught stapel-video's ``lobby/deny`` runs on all sixteen of these bodies and
finds nothing). And ``test_the_gate_is_not_blind`` proves
that is a finding rather than a gate that never looked: it re-drives every
operation with its declared schema swapped for ``{"type": "string"}`` and
requires all sixteen to fail.
"""
import copy
import json
import re
import uuid
from pathlib import Path

import jsonschema
import pytest
from django.test import override_settings
from django.urls import include, path as url_path
from rest_framework.test import APIClient

REPO = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((REPO / "docs" / "schema.json").read_text())

#: The mount the contract is emitted at (``codegen_urls.py``), reproduced for
#: the test client rather than borrowed from ``tests/urls.py``: a gate that
#: inherits the suite's mount cannot notice when the suite's mount is wrong.
urlpatterns = [
    url_path("geo/", include("stapel_geo.urls")),
]

pytestmark = [pytest.mark.django_db, pytest.mark.urls(__name__)]

V1 = "/geo/api/v1"


@pytest.fixture(autouse=True)
def _media_root(tmp_path):
    """Nothing here writes files today; pin the root so nothing ever does.

    ``MEDIA_ROOT`` is unset in this module's harness settings, so it defaults
    to the working directory — in stapel-auth that put a data export into the
    checkout, where a stray directory then shadowed a real module.
    """
    with override_settings(MEDIA_ROOT=str(tmp_path)):
        yield


@pytest.fixture(autouse=True)
def _clear_caches():
    """``locate_ip`` memoizes per address and the geocoder ledger doubles as a
    cache; both would let the populated pass answer the empty one."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


# ─────────────────────────────────────────────────────────────────────────────
# The contract side: what the document declares
# ─────────────────────────────────────────────────────────────────────────────


def _json_schema(node):
    """OpenAPI 3.0 → JSON Schema, for the divergences that matter here.

    OAS 3.0 spells "may be null" as ``nullable: true`` beside a ``type`` (or
    beside an ``allOf`` wrapping a ``$ref``, which is how ``PlaceResolution.
    address`` and ``.feature`` are emitted); JSON Schema has no such keyword
    and would refuse the null — which is exactly what those fields answer
    when the geocoder found nothing, the state the empty pass exists for.
    Everything else drf-spectacular emits here (``$ref``, ``allOf``,
    ``required``, ``readOnly``, ``example``) is JSON Schema as written.
    """
    if isinstance(node, list):
        return [_json_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    rebuilt = {k: _json_schema(v) for k, v in node.items() if k != "nullable"}
    if node.get("nullable"):
        return {"anyOf": [rebuilt, {"type": "null"}]}
    return rebuilt


def _validator(response_schema):
    root = copy.deepcopy(response_schema)
    root["components"] = copy.deepcopy(SCHEMA["components"])
    return jsonschema.Draft202012Validator(_json_schema(root))


def _operations():
    """Every ``(method, path, 2xx code, JSON body schema)`` the contract declares."""
    ops = []
    for path, methods in SCHEMA["paths"].items():
        for method, op in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            for code, response in op.get("responses", {}).items():
                body = (
                    response.get("content", {})
                    .get("application/json", {})
                    .get("schema")
                )
                if body is not None and code.startswith("2"):
                    ops.append((method.upper(), path, int(code), body))
    return sorted(ops, key=lambda o: (o[1], o[0], o[2]))


OPERATIONS = _operations()


# ─────────────────────────────────────────────────────────────────────────────
# The second half of the check: keys the document never mentions
# ─────────────────────────────────────────────────────────────────────────────


def _deref(node):
    """Follow one ``$ref`` into ``components.schemas``."""
    ref = node.get("$ref") if isinstance(node, dict) else None
    if not ref:
        return node
    name = ref.rsplit("/", 1)[-1]
    return SCHEMA["components"]["schemas"].get(name, {})


def _properties_of(node):
    """``(properties, enumerates)`` for one object schema.

    ``enumerates`` is False when the schema declines to be a closed list —
    it has an ``additionalProperties`` of its own (a free-form map: this
    module uses several for settings, payload and answer blobs) or it is a
    ``oneOf``/``anyOf`` this walk will not try to choose between. Those are
    skipped rather than guessed at: a false positive here would be worse than
    the miss, because it would teach the next reader to distrust the check.
    """
    node = _deref(node)
    if not isinstance(node, dict):
        return {}, False
    if "oneOf" in node or "anyOf" in node:
        return {}, False
    if "additionalProperties" in node:
        return dict(node.get("properties") or {}), False
    properties = dict(node.get("properties") or {})
    for branch in node.get("allOf") or ():
        branch_properties, branch_enumerates = _properties_of(branch)
        properties.update(branch_properties)
        if not branch_enumerates:
            return properties, False
    if not properties:
        return {}, False
    return properties, True


def _undeclared_keys(body, schema, path=()):
    """Keys the received body carries that the declared schema never names.

    ``jsonschema`` answers one half of "does this body match the contract":
    every declared property is there and well typed. The other half is that
    the contract ENUMERATES the body — a client is generated from the
    document, so a key the document does not mention is a key no generated
    type has a field for, and reading it is ``undefined`` at runtime and a
    compile error in a typed client. An OpenAPI schema with ``properties``
    and no ``additionalProperties`` is exactly that claim, and this is what
    checks it. It is what caught ``POST /rooms/{join_code}/lobby/deny`` in
    stapel-video: a body carrying a ``status`` key the document never
    mentions, which plain validation passes without a word.
    """
    found = []
    if isinstance(body, list):
        items = _deref(schema).get("items") if isinstance(_deref(schema), dict) else None
        if items is not None:
            for index, item in enumerate(body):
                found.extend(_undeclared_keys(item, items, path + (index,)))
        return found
    if not isinstance(body, dict):
        return found
    properties, enumerates = _properties_of(schema)
    if enumerates:
        for key in body:
            if key not in properties:
                found.append(".".join(str(part) for part in path + (key,)))
    for key, value in body.items():
        if key in properties:
            found.extend(_undeclared_keys(value, properties[key], path + (key,)))
    return found


# ─────────────────────────────────────────────────────────────────────────────
# The wire side: harness
# ─────────────────────────────────────────────────────────────────────────────


def _unique(prefix):
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def anonymous():
    return APIClient()


def make_user(**kwargs):
    from django.contrib.auth import get_user_model

    defaults = dict(
        username=_unique("wire-"),
        email=f"{_unique('wire-')}@example.com",
        password="wire-contract-password-7",
    )
    defaults.update(kwargs)
    return get_user_model().objects.create_user(**defaults)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def member_client():
    """An ordinary account — what ``IsNotAnonymousUser`` on the proxy wants."""
    return client_for(make_user())


def superuser_client():
    """``ReadOnlyOrSuperUser`` — the write half of the location tree."""
    return client_for(make_user(is_staff=True, is_superuser=True))


def make_location(name=None, parent=None, lat=None, lon=None, **kwargs):
    from stapel_geo.models import Location

    row = Location.objects.create(
        name=name or _unique("Place-"),
        type=kwargs.pop("type", "City"),
        country=kwargs.pop("country", "Testland"),
        lat=lat,
        lon=lon,
        **kwargs,
    )
    if parent is not None:
        row.set_parent(parent)
        row.save()
    return row


#: The deterministic geocoder from this module's own fakes, selected by name
#: through the ``GEOCODERS`` merge-registry — the seam a deployment uses.
def geocoder(name="fake", **extra):
    settings = {
        "GEOCODERS": {
            "fake": "stapel_geo.tests.fakes.FakeGeocoder",
            "empty": "stapel_geo.tests.fakes.EmptyGeocoder",
            "plentiful": "stapel_geo.tests.test_contract_wire.PlentifulGeocoder",
        },
        "GEOCODER": name,
        # The proxy's default permission refuses anonymous callers; the rate
        # limiter is not a response shape and shares one process-wide locmem
        # bucket with every other module in the run, so it is stood down.
        "GEOCODER_THROTTLE": None,
        "GEOCODER_ANON_THROTTLE": None,
    }
    settings.update(extra)
    return override_settings(STAPEL_GEO=settings)


def _geocoder_base():
    from stapel_geo.geocoding.base import Geocoder

    return Geocoder


class PlentifulGeocoder(_geocoder_base()):
    """Answers with three candidates, so ``resolve`` has alternatives to give.

    The shipped ``FakeGeocoder`` returns exactly one feature, which makes
    ``PlaceResolution.alternatives`` empty — and an empty array validates
    against any item schema, so the declared ``GeocodeFeature`` inside it
    would never be looked at. Registered by dotted path through the
    ``GEOCODERS`` merge-registry, the same seam a deployment uses.
    """

    name = "wire-plentiful"

    def _three(self, label):
        from stapel_geo.tests.fakes import _feature

        return [
            _feature(f"{label} A", 6.13, 49.61),
            _feature(f"{label} B", 6.14, 49.62),
            _feature(f"{label} C", 6.15, 49.63),
        ]

    def search(self, query, *, lang=None, limit=None, **params):
        from stapel_geo.geocoding.dto import GeocodeResponse

        return GeocodeResponse(features=self._three(query))

    def reverse(self, lat, lng, *, lang=None, limit=None, **params):
        from stapel_geo.geocoding.dto import GeocodeResponse

        return GeocodeResponse(features=self._three("reversed"))

    def structured(self, *, lang=None, limit=None, **params):
        from stapel_geo.geocoding.dto import GeocodeResponse

        return GeocodeResponse(features=self._three(params.get("city", "structured")))


class WireIpLocator:
    """An IP locator that places every caller, or none of them.

    Subclassed per state below rather than configured, because the locator is
    resolved from ``STAPEL_GEO["IP_LOCATORS"]`` by dotted path — which is the
    seam a deployment wires, so the gate wires it the same way.
    """


def _locator_base():
    from stapel_geo.ipgeo.base import IpLocator

    return IpLocator


class KnowingLocator(_locator_base()):
    """Places every caller in a city it knows everything about."""

    name = "wire-knowing"

    def locate(self, ip):
        from stapel_geo.ipgeo.dto import IpLocation

        return IpLocation(
            lat=52.52,
            lon=13.405,
            source="wire-knowing",
            precision="city",
            ip_resolved=True,
            label="Berlin, Germany",
            city="Berlin",
            region="Berlin",
            country="Germany",
            country_code="DE",
            accuracy_radius_km=20.0,
        )


class BlindLocator(_locator_base()):
    """Knows nothing about anybody — the ordinary case, per ipgeo's docstring."""

    name = "wire-blind"

    def locate(self, ip):
        return None


def ip_locator(dotted_path, **extra):
    settings = {
        "IP_LOCATORS": {"wire": dotted_path},
        "IP_LOCATOR": "wire",
        # Not a response shape, and one shared anonymous bucket across the run.
        "IP_THROTTLE": None,
        "IP_ANON_THROTTLE": None,
    }
    settings.update(extra)
    return override_settings(STAPEL_GEO=settings)


# ─────────────────────────────────────────────────────────────────────────────
# The recipe table
# ─────────────────────────────────────────────────────────────────────────────


class Call:
    """Performs one declared operation, and refuses to guess a path parameter."""

    def __init__(self, method, path):
        self.method = method
        self.path = path

    def __call__(self, client, params=None, data=None, query="", **extra):
        url = self.path
        for name, value in (params or {}).items():
            url = url.replace("{%s}" % name, str(value))
        assert "{" not in url, (
            f"{self.method} {self.path}: a path parameter this gate does not "
            "know how to fill — teach its recipe, or the operation goes unchecked"
        )
        send = getattr(client, self.method.lower())
        if self.method in ("GET", "DELETE"):
            return send(url + query, **extra)
        return send(url + query, data if data is not None else {}, format="json", **extra)


#: How to perform each operation the contract declares with a JSON response
#: body, keyed by ``(METHOD, path template, status code)``. ``code`` is
#: ``None`` for the usual case of one 2xx per operation.
RECIPES = {}

#: The same operations again, in the emptiest state the contract still has to
#: describe: no rows, or the one row the operation addresses carrying none of
#: its optional values. A populated answer cannot say what a field holds when
#: there is nothing to hold, and that is where every null finding in the first
#: wave of this gate was.
EMPTY_STATE = {}


def recipe(method, path, code=None, table=None):
    def register(fn):
        target = RECIPES if table is None else table
        key = (method, V1 + path, code)
        assert key not in target, f"duplicate recipe for {method} {path} {code}"
        target[key] = fn
        return fn

    return register


def empty_state(method, path, code=None):
    return recipe(method, path, code, table=EMPTY_STATE)


#: Operations that cannot be driven in-process, by name and with the reason.
#:
#: EMPTY. Every operation this module declares is reachable from a test
#: client, including the four geocoder verbs and the IP verb — those are
#: provider SEAMS resolved by name from settings, so the gate registers a
#: deterministic provider exactly the way a deployment registers a real one,
#: and everything on this side of the seam runs for real.
UNDRIVABLE: dict = {}

#: Where the rows live, for operations whose collection is NESTED in an
#: object. An empty array validates against any item schema, so the populated
#: pass has to insist the array actually carried something; the top-level
#: ``LocationCompact[]`` reads are checked by shape without an entry here.
COLLECTION_KEYS = {
    ("GET", V1 + "/geocoding/search"): ("features",),
    ("GET", V1 + "/geocoding/structured"): ("features",),
    ("GET", V1 + "/geocoding/reverse"): ("features",),
    # ``resolve`` splits the provider's answer: the best candidate becomes
    # ``feature``/``address`` and the rest become ``alternatives``, so a
    # provider that returns one result leaves the alternatives empty and the
    # item schema unexamined. The populated recipe uses a provider that
    # returns three, and asks the tree for its nearest rows as well.
    ("GET", V1 + "/geocoding/resolve"): ("alternatives", "nearest"),
}


# ── the location tree ────────────────────────────────────────────────────────


@recipe("GET", "/locations/")
def _location_list(call):
    make_location(name="Testland", lat=49.6, lon=6.1)
    return call(anonymous())


@empty_state("GET", "/locations/")
def _location_list_empty(call):
    """No locations at all — the tree of a deployment that has imported none."""
    return call(anonymous())


@recipe("POST", "/locations/")
def _location_create(call):
    return call(
        superuser_client(),
        data={
            "name": "Springfield",
            "type": "City",
            "country": "Testland",
            "lat": 49.6112,
            "lon": 6.1302,
        },
    )


@recipe("GET", "/locations/{id}/")
def _location_detail(call):
    parent = make_location(name="Testland")
    row = make_location(name="Springfield", parent=parent, lat=49.6112, lon=6.1302)
    return call(anonymous(), params={"id": row.pk})


@empty_state("GET", "/locations/{id}/")
def _location_detail_empty(call):
    """A row carrying nothing optional: no coordinates, so no geohash either,
    no parent, and a blank country. Four of the declared nullables answer
    null here and nowhere else."""
    from stapel_geo.models import Location

    row = Location.objects.create(name=None, type=None, country="", lat=None, lon=None)
    return call(anonymous(), params={"id": row.pk})


@recipe("PUT", "/locations/{id}/")
def _location_put(call):
    row = make_location(name="Springfield", lat=49.6112, lon=6.1302)
    return call(
        superuser_client(),
        params={"id": row.pk},
        data={
            "name": "Springfield (renamed)",
            "type": "City",
            "country": "Testland",
            "lat": 49.7,
            "lon": 6.2,
        },
    )


@recipe("PATCH", "/locations/{id}/")
def _location_patch(call):
    row = make_location(name="Springfield", lat=49.6112, lon=6.1302)
    return call(superuser_client(), params={"id": row.pk}, data={"name": "Shelbyville"})


@recipe("GET", "/locations/countries/")
def _countries(call):
    make_location(name="Testland", lat=49.6, lon=6.1)
    return call(anonymous())


@empty_state("GET", "/locations/countries/")
def _countries_empty(call):
    return call(anonymous())


@recipe("GET", "/locations/by-parent/{parent_id}/")
def _by_parent(call):
    parent = make_location(name="Testland")
    make_location(name="Springfield", parent=parent, lat=49.6112, lon=6.1302)
    return call(anonymous(), params={"parent_id": parent.pk})


@empty_state("GET", "/locations/by-parent/{parent_id}/")
def _by_parent_empty(call):
    """A leaf: a real parent id with no children under it."""
    return call(anonymous(), params={"parent_id": make_location(name="Leafland").pk})


@recipe("GET", "/locations/nearby-by-coords/")
def _nearby_by_coords(call):
    make_location(name="Near", lat=49.6112, lon=6.1302)
    make_location(name="Far", lat=48.0, lon=2.0)
    return call(anonymous(), query="?lat=49.611&lon=6.130")


@empty_state("GET", "/locations/nearby-by-coords/")
def _nearby_by_coords_empty(call):
    """A coordinate with nothing anywhere near it — in fact, nothing at all."""
    return call(anonymous(), query="?lat=49.611&lon=6.130")


@recipe("GET", "/locations/nearby-by-geohash/")
def _nearby_by_geohash(call):
    make_location(name="Near", lat=49.6112, lon=6.1302)
    return call(anonymous(), query="?geohash=u0u65x90")


@empty_state("GET", "/locations/nearby-by-geohash/")
def _nearby_by_geohash_empty(call):
    return call(anonymous(), query="?geohash=u0u65x90")


@recipe("GET", "/locations/validate-uuid/{uuid}/")
def _validate_uuid(call):
    row = make_location(name="Testland", lat=49.6, lon=6.1)
    return call(anonymous(), params={"uuid": row.uuid})


@empty_state("GET", "/locations/validate-uuid/{uuid}/")
def _validate_uuid_empty(call):
    """A well-formed uuid nothing answers to — ``valid: false``."""
    return call(anonymous(), params={"uuid": uuid.uuid4()})


# ── the geocoder proxy ───────────────────────────────────────────────────────


@recipe("GET", "/geocoding/search")
def _geocode_search(call):
    with geocoder():
        return call(member_client(), query="?q=Testville&lang=en")


@empty_state("GET", "/geocoding/search")
def _geocode_search_empty(call):
    """A provider that found nothing — the middle of the sea, not a failure.

    ``features`` is empty and ``lang`` is whatever survived clamping, which
    is the state a client's "no results" branch renders.
    """
    with geocoder("empty"):
        return call(member_client(), query="?q=nowhere-at-all")


@recipe("GET", "/geocoding/structured")
def _geocode_structured(call):
    with geocoder():
        return call(member_client(), query="?city=Testville&street=Test+Street")


@empty_state("GET", "/geocoding/structured")
def _geocode_structured_empty(call):
    with geocoder("empty"):
        return call(member_client(), query="?city=Nowhere")


@recipe("GET", "/geocoding/reverse")
def _geocode_reverse(call):
    with geocoder():
        return call(member_client(), query="?lat=49.61&lon=6.13&lang=en")


@empty_state("GET", "/geocoding/reverse")
def _geocode_reverse_empty(call):
    with geocoder("empty"):
        return call(member_client(), query="?lat=0&lon=0")


@recipe("GET", "/geocoding/resolve")
def _geocode_resolve(call):
    """The full answer: a pick, its components, alternatives and the nearest
    known tree rows — every optional half of ``PlaceResolution`` populated."""
    make_location(name="Near", lat=49.6112, lon=6.1302)
    make_location(name="Also near", lat=49.6120, lon=6.1310)
    with geocoder("plentiful"):
        return call(member_client(), query="?lat=49.611&lon=6.130&limit=5&nearest=3")


@empty_state("GET", "/geocoding/resolve")
def _geocode_resolve_empty(call):
    """Nothing found and nothing asked for: ``formatted``, ``address`` and
    ``feature`` all null, ``alternatives`` and ``nearest`` both empty.

    This is the state that would catch a ``PlaceResolution`` claiming a
    required display line — the exact family of defect the first wave of this
    gate found in stapel-auth and stapel-profiles.
    """
    with geocoder("empty"):
        return call(member_client(), query="?lat=0&lon=0")


# ── the map's own configuration, and the visitor's position ──────────────────


@recipe("GET", "/map/config")
def _map_config(call):
    """A deployment that has answered every optional question."""
    with override_settings(
        STAPEL_GEO={
            "MAP_DEFAULT_CENTER": [55.7558, 37.6173],
            "MAP_BBOX": [19.6, 41.2, 190.0, 81.9],
            "MAP_TILE_SUBDOMAINS": ["a", "b", "c"],
        }
    ):
        return call(anonymous())


@empty_state("GET", "/map/config")
def _map_config_empty(call):
    """A deployment with no opinion: no opening centre, no operating area, no
    tile shards and no usage-policy URL — three declared nullables at null."""
    with override_settings(
        STAPEL_GEO={
            "MAP_DEFAULT_CENTER": None,
            "MAP_BBOX": None,
            "MAP_TILE_SUBDOMAINS": [],
            "MAP_TILE_POLICY_URL": None,
        }
    ):
        return call(anonymous())


@recipe("GET", "/ip")
def _ip_location(call):
    with ip_locator("stapel_geo.tests.test_contract_wire.KnowingLocator"):
        return call(anonymous())


@empty_state("GET", "/ip")
def _ip_location_empty(call):
    """A locator that places nobody, and a deployment that still has a centre.

    The documented shape of "we have no idea, here is where this site lives":
    ``ip_resolved: false``, ``precision: default``, and every one of the six
    nullable descriptive fields at null. The 204 branch (no fallback centre
    either) declares no JSON body and is therefore not an operation here.
    """
    with ip_locator(
        "stapel_geo.tests.test_contract_wire.BlindLocator",
        MAP_DEFAULT_CENTER=[55.7558, 37.6173],
        IP_FALLBACK_LABEL="",
    ):
        return call(anonymous())


# ─────────────────────────────────────────────────────────────────────────────
# The gate
# ─────────────────────────────────────────────────────────────────────────────


#: Operations whose declared body the wire does not send.
#:
#: EMPTY, and that is the finding rather than the absence of one: 16 of 16
#: operations were driven and every declared body held, in both the populated
#: and the empty state. The mechanism stays because the next change will need
#: it — an entry must name the defect AND its owner, and ``strict=True`` turns
#: a fixed one into a failure until the entry is deleted, so a finding can be
#: neither forgotten nor quietly kept. That is not decoration: the first draft
#: of this file recorded ``LocationCompact.distance_km`` here and the strict
#: XPASS deleted the entry for it.
KNOWN_MISMATCHES: dict = {}

#: Which pass each recorded mismatch applies to.
#:
#: A defect that shows in only ONE state must not xfail the other: with
#: ``strict=True`` an honest answer marked xfail is itself a failure, and
#: marking both passes would be a claim this gate has not made. Anything not
#: named here applies to both.
MISMATCH_STATES: dict = {}

_ALL_STATES = frozenset({"populated", "empty"})


def _mismatch_reason(method, path, state):
    """The recorded reason if this operation lies in THIS state, else None."""
    key = (method, path)
    if key not in KNOWN_MISMATCHES:
        return None
    if state not in MISMATCH_STATES.get(key, _ALL_STATES):
        return None
    return KNOWN_MISMATCHES[key]


def _recipe_for(table, method, path, code):
    """The code-specific recipe if there is one, else the operation's."""
    return table.get((method, path, code)) or table.get((method, path, None))


def test_the_contract_declares_something_to_check():
    assert OPERATIONS, "docs/schema.json declares no JSON responses at all"


def test_every_declared_path_resolves_under_this_urlconf():
    """The suite must be looking where the document describes.

    Five of the first eight libraries this gate was written for had a
    committed contract that nothing had ever driven, because the test urlconf
    mounted somewhere the document does not describe: a prefix one segment
    short, the paths bare, less than the emission, both segments skipped, a
    doubled prefix. In every case the operations were "covered" by a file that
    could not have reached a single one of them.

    That is the same family as a gate nobody asks: the recipes can all be
    written, the run can be green, and not one request went where the contract
    says it goes. A missing recipe already fails loudly; this fails when the
    MOUNT is wrong, which no per-operation check can see, because when the
    mount is wrong every operation is equally and silently unreachable.

    Asserted against the urlconf THIS module declares — inheriting the suite's
    mount would be exactly the blindness the check exists to remove.
    """
    from django.urls import Resolver404, resolve

    # Resolution cares about the SHAPE of a segment, and this URL set mixes
    # integer pks, a uuid and a free-form slug. A path counts as reachable if
    # any one shape resolves: the question here is whether the mount exists,
    # not whether a particular id does.
    candidates = (
        "00000000-0000-4000-8000-000000000000",
        "1",
        "a-slug",
    )

    unreachable = []
    for _method, path, _code, _schema in OPERATIONS:
        for value in candidates:
            try:
                resolve(re.sub(r"\{[^}]+\}", value, path))
                break
            except Resolver404:
                continue
        else:
            unreachable.append(path)

    assert not unreachable, (
        "these declared paths do not resolve under this module's urlconf, so "
        "nothing here can be driving them — the mount is wrong, not the "
        "recipes:\n  " + "\n  ".join(sorted(set(unreachable)))
    )


def test_every_declared_operation_is_driven_or_named_undrivable():
    """No operation is covered by silence, and no entry outlives its operation."""
    missing = [
        (method, path, code)
        for method, path, code, _schema in OPERATIONS
        if _recipe_for(RECIPES, method, path, code) is None
        and (method, path) not in UNDRIVABLE
    ]
    assert not missing, (
        "operations with a declared JSON response body and no recipe:\n"
        + "\n".join(f"  {m} {p} -> {c}" for m, p, c in missing)
    )

    declared_codes = {(m, p, c) for m, p, c, _ in OPERATIONS}
    declared_ops = {(m, p) for m, p, _c, _ in OPERATIONS}
    stale = sorted(
        key
        for key in RECIPES
        if (key[0], key[1]) not in declared_ops
        or (key[2] is not None and key not in declared_codes)
    )
    assert not stale, (
        "recipes for operations/status codes the contract no longer declares:\n"
        + "\n".join(f"  {m} {p} -> {c}" for m, p, c in stale)
    )
    stale_exclusions = sorted(set(UNDRIVABLE) - declared_ops)
    assert not stale_exclusions, (
        f"exclusions for operations the contract no longer declares: {stale_exclusions}"
    )
    both = sorted((m, p) for m, p, _c in RECIPES if (m, p) in UNDRIVABLE)
    assert not both, f"driven AND excluded: {both}"
    for key, reason in UNDRIVABLE.items():
        assert reason and reason.strip(), f"{key} is excluded with no reason"

    # RECIPES ∪ UNDRIVABLE is EXACTLY the declared set — asserted as sets, so
    # neither an operation nobody drives nor an entry nobody needs survives.
    covered = {(m, p) for m, p, _c in RECIPES} | set(UNDRIVABLE)
    assert covered == declared_ops, (
        "RECIPES ∪ UNDRIVABLE is not the declared set:\n"
        f"  declared but uncovered: {sorted(declared_ops - covered)}\n"
        f"  covered but undeclared: {sorted(covered - declared_ops)}"
    )

    stale_collections = sorted(set(COLLECTION_KEYS) - declared_ops)
    assert not stale_collections, (
        f"COLLECTION_KEYS names operations the contract no longer declares: "
        f"{stale_collections}"
    )


def test_every_read_is_also_driven_in_its_emptiest_state():
    """A populated answer cannot say what a field holds when there is nothing.

    Every null finding in the first wave of this gate was on the empty state.
    A gate that only ever seeds three rows and asks never sees any of them.
    """
    exempt: set = set()
    reads = {
        (method, path)
        for method, path, _code, _schema in OPERATIONS
        if method == "GET"
    }
    covered = {(m, p) for m, p, _c in EMPTY_STATE}
    missing = sorted(reads - covered - exempt)
    assert not missing, (
        "reads driven only against a populated database — the state where "
        "every null claim in this gate's history was found is unchecked:\n"
        + "\n".join(f"  {m} {p}" for m, p in missing)
    )
    declared_ops = {(m, p) for m, p, _c, _ in OPERATIONS}
    stale = sorted({(m, p) for m, p, _c in EMPTY_STATE} - declared_ops)
    assert not stale, f"empty-state recipes for undeclared operations: {stale}"


def test_every_known_mismatch_is_still_declared_and_explained():
    """A recorded defect must name a live operation and carry its reason.

    Without this, an operation that is renamed or removed leaves an entry that
    silences nothing and reads like a known problem forever.
    """
    declared = {(method, path) for method, path, _code, _schema in OPERATIONS}
    for key, reason in KNOWN_MISMATCHES.items():
        assert key in declared, (
            f"{key} is recorded as a known mismatch but the contract no longer "
            "declares it — delete the entry"
        )
        assert reason and reason.strip(), f"{key} is recorded with no reason"

    stale_states = sorted(set(MISMATCH_STATES) - set(KNOWN_MISMATCHES))
    assert not stale_states, (
        f"MISMATCH_STATES narrows operations that are not recorded as "
        f"mismatches at all: {stale_states}"
    )
    for key, states in MISMATCH_STATES.items():
        assert states and states <= _ALL_STATES, (
            f"{key} is narrowed to {sorted(states)}, which is not a subset of "
            f"{sorted(_ALL_STATES)} — an empty or unknown set silences nothing"
        )


def _drive(table, method, path, code, body_schema, *, expect_rows):
    perform = _recipe_for(table, method, path, code)
    assert perform is not None, (
        f"{method} {path} declares a response body and has no recipe — an "
        "unchecked operation is a schema nobody proves. Teach RECIPES, or "
        "name it in UNDRIVABLE with a reason."
    )

    response = perform(Call(method, path))
    assert response.status_code == code, (
        f"{method} {path}: expected the declared {code}, got "
        f"{response.status_code}: {response.content[:400]}"
    )

    body = response.json()
    errors = sorted(_validator(body_schema).iter_errors(body), key=lambda e: list(e.path))
    assert not errors, (
        f"{method} {path} answers a body the contract does not describe:\n"
        + "\n".join(f"  at {list(e.path) or '<root>'}: {e.message}" for e in errors[:10])
        + f"\n  body: {json.dumps(body)[:600]}"
    )
    # The other direction: a key the document never mentions is a key no
    # generated client has a field for.
    undeclared = _undeclared_keys(body, body_schema)
    assert not undeclared, (
        f"{method} {path} answers keys the contract never mentions, so no "
        f"generated client has a field for them: {sorted(undeclared)}"
        + f"\n  body: {json.dumps(body)[:600]}"
    )
    # An empty list validates against any item schema, so a collection must
    # actually carry a row for the check to have looked at anything — both the
    # top-level arrays and the ones nested in an envelope.
    if expect_rows:
        if isinstance(body, list):
            assert body, f"{method} {path}: the declared collection came back empty"
        if isinstance(body, dict):
            for key in COLLECTION_KEYS.get((method, path), ()):
                assert body.get(key), (
                    f"{method} {path}: the declared {key!r} collection came "
                    "back empty, so its item schema was never looked at"
                )
    return body


@pytest.mark.parametrize(
    "method,path,code,body_schema",
    OPERATIONS,
    ids=[f"{m} {p} {c}" for m, p, c, _ in OPERATIONS],
)
def test_the_wire_matches_the_declared_response(method, path, code, body_schema, request):
    if (method, path) in UNDRIVABLE:
        pytest.skip(f"excluded by name: {UNDRIVABLE[(method, path)]}")

    reason = _mismatch_reason(method, path, "populated")
    if reason is not None:
        request.node.add_marker(
            pytest.mark.xfail(strict=True, reason=f"{method} {path}: {reason}")
        )

    _drive(RECIPES, method, path, code, body_schema, expect_rows=True)


_EMPTY_OPERATIONS = [
    (method, path, code, schema)
    for method, path, code, schema in OPERATIONS
    if _recipe_for(EMPTY_STATE, method, path, code) is not None
]


@pytest.mark.parametrize(
    "method,path,code,body_schema",
    _EMPTY_OPERATIONS,
    ids=[f"{m} {p} {c}" for m, p, c, _ in _EMPTY_OPERATIONS],
)
def test_the_wire_matches_the_declared_response_when_there_is_nothing_there(
    method, path, code, body_schema, request
):
    """The same claim, asked in the state where the nulls live."""
    reason = _mismatch_reason(method, path, "empty")
    if reason is not None:
        request.node.add_marker(
            pytest.mark.xfail(strict=True, reason=f"{method} {path}: {reason}")
        )

    _drive(EMPTY_STATE, method, path, code, body_schema, expect_rows=False)


def test_the_undeclared_key_check_is_not_blind():
    """The enumeration half, canaried the way the validation half is.

    A check that silently returned an empty list for every input would look
    exactly like a clean run. So: give it a real body and a schema that
    enumerates only one of its keys, and require it to name the rest.
    """
    schema = {"type": "object", "properties": {"kept": {"type": "string"}}}
    body = {"kept": "yes", "extra": 1, "another": None}
    assert sorted(_undeclared_keys(body, schema)) == ["another", "extra"]

    # A schema that declines to enumerate (a free-form map) reports nothing,
    # and a nested object is walked rather than skipped.
    assert _undeclared_keys(body, {"type": "object", "additionalProperties": {}}) == []
    nested = {
        "type": "object",
        "properties": {"inner": {"type": "object", "properties": {}}},
    }
    assert _undeclared_keys({"inner": {"surprise": 1}}, nested) == []


def test_the_gate_is_not_blind():
    """A canary: swap a declared schema for one the wire cannot satisfy.

    Everything above can be green for two reasons — the claims are honest, or
    the check never looks at the body. This tells them apart by validating a
    real response against ``{"type": "string"}``: every operation here answers
    an object or an array, so every one of them must fail. If any passes, the
    validation in ``_drive`` is not reaching the received body and this whole
    file proves nothing.
    """
    honest = [
        (method, path, code)
        for method, path, code, _schema in OPERATIONS
        if (method, path) not in KNOWN_MISMATCHES and (method, path) not in UNDRIVABLE
    ]
    assert honest, "nothing left to canary"

    survivors = []
    for method, path, code in honest:
        try:
            _drive(RECIPES, method, path, code, {"type": "string"}, expect_rows=False)
        except AssertionError:
            continue
        survivors.append(f"{method} {path}")
    assert not survivors, (
        "these operations passed validation against {'type': 'string'} — the "
        "gate is not looking at the body it received:\n  " + "\n  ".join(survivors)
    )
