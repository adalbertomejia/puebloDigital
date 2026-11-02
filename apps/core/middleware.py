"""Restrict legacy global screens; attendance keeps its existing scoped querysets."""
from django.http import Http404


class VistasGlobalesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.user.is_authenticated or view_func.__module__ != 'apps.core.views':
            return None
        name = view_func.__name__
        permissions = []
        if 'tesoreria' in name or 'aportaciones' in name or name == 'acreditar_obligacion':
            permissions = ['core.view_ciudadano', 'tesoreria.view_obligacionciudadano']
        elif name == 'control_agua':
            permissions = ['core.view_ciudadano', 'agua.view_toma']
        elif name == 'dashboard_operativo':
            permissions = ['core.view_ciudadano', 'tesoreria.view_pago', 'tesoreria.view_cooperacion', 'agua.view_toma']
        if not all(request.user.has_perm(permission) for permission in permissions):
            raise Http404
