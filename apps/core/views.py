from django.shortcuts import render

from apps.comites.models import UsuarioApp


def home(request):
    perfiles = []
    if request.user.is_authenticated:
        perfiles = (
            UsuarioApp.objects.filter(user=request.user, activo=True)
            .select_related('comite')
            .order_by('comite__nombre', 'rol')
        )

    return render(request, 'home.html', {'perfiles': perfiles})
