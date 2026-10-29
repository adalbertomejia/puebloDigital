class AdministracionGlobal:
    """Raw administrative access and authority assignments are reserved for superusers."""

    def _es_administrador(self, request):
        return bool(request.user.is_active and request.user.is_superuser)

    def has_module_permission(self, request):
        return self._es_administrador(request)

    def has_view_permission(self, request, obj=None):
        return self._es_administrador(request)

    def has_add_permission(self, request, obj=None):
        return self._es_administrador(request)

    def has_change_permission(self, request, obj=None):
        return self._es_administrador(request)

    def has_delete_permission(self, request, obj=None):
        return self._es_administrador(request)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset if self._es_administrador(request) else queryset.none()


