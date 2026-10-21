from django.contrib import admin
from .models import Comite, PerfilAcceso, UsuarioApp

@admin.register(Comite)
class ComiteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'activo')
    list_filter = ('tipo', 'activo')
    search_fields = ('nombre',)


@admin.register(PerfilAcceso)
class PerfilAccesoAdmin(admin.ModelAdmin):
    list_display = ("user", "ciudadano", "created_at")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "ciudadano__nombre",
        "ciudadano__apellido_paterno",
        "ciudadano__apellido_materno",
    )
    autocomplete_fields = ("user", "ciudadano")
    list_select_related = ("user", "ciudadano")
    ordering = ("ciudadano__apellido_paterno", "ciudadano__apellido_materno", "ciudadano__nombre")

@admin.register(UsuarioApp)
class UsuarioAppAdmin(admin.ModelAdmin):
    list_display = ('user', 'comite', 'rol', 'activo', 'created_at')
    list_filter = ('rol', 'activo', 'comite')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'ciudadano__nombre', 'ciudadano__apellido_paterno')
