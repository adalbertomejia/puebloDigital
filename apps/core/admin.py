from django.contrib import admin
from .models import Ciudadano

@admin.register(Ciudadano)
class CiudadanoAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'edad', 'telefono', 'activo', 'created_at')
    search_fields = (
        'apellido_paterno__istartswith',
        'apellido_materno__istartswith',
        'nombre__istartswith',
    )
    list_filter = ('activo', 'edad', 'created_at')
    ordering = ('apellido_paterno', 'apellido_materno', 'nombre')
    list_per_page = 50
