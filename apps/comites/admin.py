from django.contrib import admin

from .admin_security import CommitteeAccessMixin
from .models import Comite, UsuarioApp


@admin.register(Comite)
class ComiteAdmin(CommitteeAccessMixin, admin.ModelAdmin):
    committee_lookup = "pk"
    list_display = ("nombre", "tipo", "activo")
    list_filter = ("tipo", "activo")
    search_fields = ("nombre",)


@admin.register(UsuarioApp)
class UsuarioAppAdmin(CommitteeAccessMixin, admin.ModelAdmin):
    committee_lookup = "comite"
    committee_fk_fields = ("comite",)
    list_display = ("user", "comite", "rol", "activo", "created_at")
    list_filter = ("rol", "activo", "comite")
    search_fields = ("user__username", "user__first_name", "user__last_name", "ciudadano__nombre", "ciudadano__apellido_paterno")

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        return UsuarioApp.objects.filter(user=request.user, activo=True, rol=UsuarioApp.Roles.DELEGADO).exists()

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if not self.has_module_permission(request):
            return False
        return super().has_view_permission(request, obj=obj)

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if not self.has_module_permission(request):
            return False
        return super().has_change_permission(request, obj=obj)

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj=obj)
