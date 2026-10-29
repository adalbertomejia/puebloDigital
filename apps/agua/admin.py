from django.contrib import admin
from apps.core.admin_seguridad import AdministracionGlobal
from .models import Toma

@admin.register(Toma)
class TomaAdmin(AdministracionGlobal, admin.ModelAdmin):
    list_display = ('numero_toma', 'ciudadano', 'costo_anual', 'estado')
    list_filter = ('estado',)
    search_fields = ('numero_toma', 'ciudadano__nombre', 'ciudadano__apellido_paterno')
