"""Admin for stapel-geo — treenode Location editor + read-only geocode ledger."""
from django.contrib import admin
from treenode.admin import TreeNodeModelAdmin
from treenode.forms import TreeNodeForm

from .models import GeocodeCache, Location


@admin.register(Location)
class LocationAdmin(TreeNodeModelAdmin):
    treenode_display_mode = TreeNodeModelAdmin.TREENODE_DISPLAY_MODE_ACCORDION
    form = TreeNodeForm
    list_display = ["name", "type", "country", "lat", "lon", "geohash", "uuid"]
    readonly_fields = ["uuid", "geohash", "display_name_narrow", "display_name_broad"]
    search_fields = ["name", "country", "uuid"]


@admin.register(GeocodeCache)
class GeocodeCacheAdmin(admin.ModelAdmin):
    """The geocoder spend ledger — an audit journal, not an editor."""

    list_display = ["provider", "verb", "status", "duration_ms", "lang", "created_at"]
    list_filter = ["provider", "verb", "status"]
    readonly_fields = [
        "provider", "verb", "query_hash", "lang", "status",
        "duration_ms", "response", "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
