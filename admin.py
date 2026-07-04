"""Admin for stapel-geo (spatial — loaded only with the app).

Location uses the treenode + GeoDjango admin mixins; GeoFile is a mostly
read-only import journal.
"""
from django.contrib import admin
from django.contrib.gis.admin.options import GeoModelAdminMixin
from treenode.admin import TreeNodeModelAdmin
from treenode.forms import TreeNodeForm

from .models import GeoFile, Location


@admin.register(GeoFile)
class GeoFileAdmin(admin.ModelAdmin):
    list_display = ["id", "geo_json", "location_level", "import_status", "added"]
    readonly_fields = [
        "validation_result", "location_level", "added",
        "import_status", "import_progress", "import_total", "import_error",
    ]


@admin.register(Location)
class LocationAdmin(GeoModelAdminMixin, TreeNodeModelAdmin):
    treenode_display_mode = TreeNodeModelAdmin.TREENODE_DISPLAY_MODE_ACCORDION
    form = TreeNodeForm
    list_display = ["name", "type", "country", "uuid", "g_id"]
    readonly_fields = ["uuid"]
    search_fields = ["name", "g_id", "uuid"]
