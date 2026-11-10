from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group
from apps.core.admin_seguridad import AdministracionGlobal
from .models import Comite, PerfilAcceso, UsuarioApp

@admin.register(Comite)
class ComiteAdmin(AdministracionGlobal, admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'activo')
    list_filter = ('tipo', 'activo')
    search_fields = ('nombre',)


@admin.register(PerfilAcceso)
class PerfilAccesoAdmin(AdministracionGlobal, admin.ModelAdmin):
    fieldsets = ((None, {
        "fields": ("user", "ciudadano"),
        "description": "Vincula una cuenta con su ciudadano. Esta identidad se muestra en Mi acceso; los cargos se asignan en Cargos de comité.",
    }),)
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
class UsuarioAppAdmin(AdministracionGlobal, admin.ModelAdmin):
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        vigentes = {'PRESIDENTE', 'TESORERO', 'LECTURA'}
        if obj is not None:
            vigentes.add(obj.rol)
        form.base_fields['rol'].choices = [('', 'Selecciona un cargo')] + [(value, label) for value, label in UsuarioApp.Roles.choices if value in vigentes]
        return form

    autocomplete_fields = ("user", "ciudadano", "comite")
    fieldsets = (
        ("Asignación del cargo", {
            "fields": ("user", "comite", "rol", "activo"),
            "description": "Asigna un rol a una cuenta dentro de un comité. Cada cuenta pertenece a un ciudadano y admite un solo cargo activo. Desactiva el anterior antes de cambiarlo.",
        }),
        ("Ciudadano registrado en el cargo", {
            "fields": ("ciudadano",),
            "description": "Debe coincidir con Vínculos de cuenta y ciudadano; si se deja vacío se toma de ese vínculo. No sustituye la identidad general de la cuenta.",
        }),
    )
    list_display = ('user', 'comite', 'rol', 'activo', 'created_at')
    list_filter = ('rol', 'activo', 'comite')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'ciudadano__nombre', 'ciudadano__apellido_paterno')


# Django's built-in user/group forms can grant superuser status or global
# permissions. Keep those authority-changing routes under the same boundary.


class CuentaGlobalAdmin(AdministracionGlobal, UserAdmin):
    pass


class GrupoGlobalAdmin(AdministracionGlobal, GroupAdmin):
    pass


admin.site.unregister(get_user_model())
admin.site.register(get_user_model(), CuentaGlobalAdmin)
admin.site.unregister(Group)
admin.site.register(Group, GrupoGlobalAdmin)
