from django.contrib import admin
from .models import Ciudadano

@admin.register(Ciudadano)
class CiudadanoAdmin(admin.ModelAdmin):
    list_display = ('nombre_completo', 'curp', 'telefono', 'activo', 'created_at')
    search_fields = ('nombre', 'apellido_paterno', 'apellido_materno', 'curp')
    list_filter = ('activo', 'created_at')
    ordering = ('apellido_paterno', 'apellido_materno', 'nombre')
