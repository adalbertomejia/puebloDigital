from django.contrib import admin
from .models import Comite, UsuarioApp

@admin.register(Comite)
class ComiteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'activo')
    list_filter = ('tipo', 'activo')
    search_fields = ('nombre',)

@admin.register(UsuarioApp)
class UsuarioAppAdmin(admin.ModelAdmin):
    list_display = ('user', 'comite', 'rol', 'activo', 'created_at')
    list_filter = ('rol', 'activo', 'comite')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'ciudadano__nombre', 'ciudadano__apellido_paterno')
