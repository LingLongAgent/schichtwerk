from django.contrib import admin

from .models import Betriebszugehoerigkeit


@admin.register(Betriebszugehoerigkeit)
class BetriebszugehoerigkeitAdmin(admin.ModelAdmin):
    list_display = ("user", "betrieb", "erstellt_am")
    search_fields = ("user__username", "betrieb__name")
