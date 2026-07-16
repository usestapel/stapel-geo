"""Business flows of stapel-geo (stapel_core.flows).

Autodiscovered via INSTALLED_APPS by ``autodiscover_flows()``. The Flow
objects live here; the HTTP steps are attached in the view modules by
stacking ``@flow_step(FLOW, ...)`` on the endpoint methods (views import
this module — the dependency points one way, no cycle).

The literals below are the canonical English source texts; every
flow/step derives an implicit i18n key (``flow.<id>.title`` /
``flow.<id>.description`` / ``flow.<id>.step.<order>.note``).
"""
from stapel_core.flows import Flow

# ─────────────────────────────────────────────────────────────────────────────
# geo.location_browse — walking the location tree (reference data UX)
# ─────────────────────────────────────────────────────────────────────────────

LOCATION_BROWSE = Flow(
    "geo.location_browse",
    title="Browse the location tree",
    description=(
        "A user drills into the hierarchical location reference "
        "(country -> region -> city) or searches it by name — picking a "
        "location for a listing, a profile, or a filter. Flat reference "
        "data: no geometry, each node is a point with a geohash."
    ),
    actors=["Any authenticated or anonymous user"],
)
LOCATION_BROWSE.human(order=0, note="The user opens a location picker or map filter")

# ─────────────────────────────────────────────────────────────────────────────
# geo.location_nearby — proximity search over the tree
# ─────────────────────────────────────────────────────────────────────────────

LOCATION_NEARBY = Flow(
    "geo.location_nearby",
    title="Find locations near a point",
    description=(
        "A consumer (listings' radius filter, a 'near me' UI) asks which "
        "known locations are nearest to a coordinate or geohash. Served by "
        "the swappable search backend (STAPEL_GEO['SEARCH_BACKEND']) — "
        "geohash prefix expansion over the primary DB by default, correct "
        "across the equator, the antimeridian and the poles."
    ),
    actors=["Any user", "Consumer modules via comm"],
)
LOCATION_NEARBY.function(
    "geo.nearby", order=3,
    note="Modules query top-K proximity by name over comm — never importing geo",
)
LOCATION_NEARBY.function(
    "geo.radius", order=4,
    note="Radius membership (everything within N km) for radius filters",
)
LOCATION_NEARBY.function(
    "geo.bbox", order=5,
    note="Rectangle membership for map-viewport queries (antimeridian-aware)",
)

# ─────────────────────────────────────────────────────────────────────────────
# geo.location_resolve — cross-service reference checks
# ─────────────────────────────────────────────────────────────────────────────

LOCATION_RESOLVE = Flow(
    "geo.location_resolve",
    title="Validate and expand a location reference",
    description=(
        "A module holding an opaque location UUID (a listing's location_id, "
        "a calendar address) checks it still exists and expands it to a "
        "display summary. A missing UUID is a normal answer, not an error."
    ),
    actors=["Consumer modules via comm", "Frontends"],
)
LOCATION_RESOLVE.function(
    "geo.resolve", order=2,
    note="Modules resolve location UUIDs by name over comm",
)

# ─────────────────────────────────────────────────────────────────────────────
# geo.geocode_address — the geocoder proxy
# ─────────────────────────────────────────────────────────────────────────────

GEOCODE_ADDRESS = Flow(
    "geo.geocode_address",
    title="Geocode an address",
    description=(
        "A logged-in user turns free text, address components or a "
        "coordinate into normalized GeoJSON places through the swappable "
        "provider registry (photon by default; nominatim as keyless "
        "dev/fallback). Every call is throttled (scope 'geocoding'), "
        "cached (GeocodeCache, 30-day TTL) and written to the spend ledger."
    ),
    actors=["Authenticated user"],
)
GEOCODE_ADDRESS.human(order=0, note="The user types an address or drops a map pin")

__all__ = [
    "LOCATION_BROWSE",
    "LOCATION_NEARBY",
    "LOCATION_RESOLVE",
    "GEOCODE_ADDRESS",
]
