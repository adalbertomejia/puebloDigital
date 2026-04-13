from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from apps.agua.models import Toma
from apps.comites.models import Comite, UsuarioApp


@login_required
def toma_list_view(request):
    perfiles = UsuarioApp.objects.filter(
        user=request.user,
        activo=True,
        comite__tipo=Comite.Tipos.AGUA,
    )
    tiene_acceso = request.user.is_superuser or perfiles.exists()

    tomas = []
    if tiene_acceso:
        estado = request.GET.get('estado')
        q = request.GET.get('q', '').strip()

        tomas = Toma.objects.select_related('ciudadano').all()
        if estado:
            tomas = tomas.filter(estado=estado)
        if q:
            tomas = tomas.filter(
                Q(ciudadano__nombre__icontains=q)
                | Q(ciudadano__apellido_paterno__icontains=q)
                | Q(ciudadano__curp__icontains=q)
                | Q(numero_toma__icontains=q)
            )

    context = {
        'tiene_acceso': tiene_acceso,
        'tomas': tomas,
        'estados': Toma.Estados.choices,
        'filtro_estado': request.GET.get('estado', ''),
        'filtro_q': request.GET.get('q', '').strip(),
    }
    return render(request, 'agua/toma_list.html', context)
