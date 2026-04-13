from django.contrib import admin

from .models import UsuarioApp


class CommitteeAccessMixin(admin.ModelAdmin):
    committee_lookup = None
    committee_fk_fields = ()
    foreign_key_committee_filters = {}
    treasury_only = False

    def _profiles(self, request):
        if request.user.is_superuser:
            return UsuarioApp.objects.none()
        return UsuarioApp.objects.filter(user=request.user, activo=True).select_related("comite")

    def _role_matrix(self, request):
        profiles = self._profiles(request)
        all_ids = set(profiles.values_list("comite_id", flat=True))
        delegated_ids = set(profiles.filter(rol=UsuarioApp.Roles.DELEGADO).values_list("comite_id", flat=True))
        president_ids = set(profiles.filter(rol=UsuarioApp.Roles.PRESIDENTE).values_list("comite_id", flat=True))
        treasurer_ids = set(profiles.filter(rol=UsuarioApp.Roles.TESORERO).values_list("comite_id", flat=True))
        has_read_only = profiles.filter(rol=UsuarioApp.Roles.LECTURA).exists()

        return {
            "all_ids": all_ids,
            "delegated_ids": delegated_ids,
            "president_ids": president_ids,
            "treasurer_ids": treasurer_ids,
            "has_read_only": has_read_only,
        }

    def _managed_committee_ids(self, request):
        matrix = self._role_matrix(request)
        managed = set(matrix["delegated_ids"]) | set(matrix["president_ids"])
        if self.treasury_only:
            managed |= set(matrix["treasurer_ids"])
        return managed

    def _visible_committee_ids(self, request):
        matrix = self._role_matrix(request)
        visible = set(matrix["all_ids"])
        if self.treasury_only:
            visible = set(matrix["treasurer_ids"]) | set(matrix["delegated_ids"])
        return visible

    def _can_view_module(self, request):
        if request.user.is_superuser:
            return True
        return bool(self._visible_committee_ids(request))

    def has_module_permission(self, request):
        return self._can_view_module(request)

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if not self._can_view_module(request):
            return False
        if obj is None:
            return True
        queryset = self.get_queryset(request)
        return queryset.filter(pk=obj.pk).exists()

    def has_add_permission(self, request):
        if request.user.is_superuser:
            return True
        return bool(self._managed_committee_ids(request))

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True
        if not self._managed_committee_ids(request):
            return False
        if obj is None:
            return True
        queryset = self.get_queryset(request)
        if not queryset.filter(pk=obj.pk).exists():
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        return self.has_change_permission(request, obj=obj)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        if not self.committee_lookup:
            return queryset.none()
        visible_ids = self._visible_committee_ids(request)
        if not visible_ids:
            return queryset.none()
        return queryset.filter(**{f"{self.committee_lookup}__in": visible_ids}).distinct()

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if request.user.is_superuser:
            return readonly_fields
        if not self._managed_committee_ids(request):
            fields = [field.name for field in self.model._meta.fields]
            return sorted(set(readonly_fields + fields))
        return readonly_fields

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            visible_ids = self._visible_committee_ids(request)
            if db_field.name in self.committee_fk_fields:
                kwargs["queryset"] = db_field.remote_field.model.objects.filter(pk__in=visible_ids)
            lookup = self.foreign_key_committee_filters.get(db_field.name)
            if lookup:
                kwargs["queryset"] = db_field.remote_field.model.objects.filter(**{f"{lookup}__in": visible_ids}).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
