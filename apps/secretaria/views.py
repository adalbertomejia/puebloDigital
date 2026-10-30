from datetime import timedelta
from urllib.parse import urlencode
from dal import autocomplete
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import Http404, FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_GET
from django.views.decorators.cache import never_cache
from apps.core.models import Ciudadano
from apps.comites.models import Comite
from apps.core.query_helpers import filtro_busqueda_ciudadano
from apps.tesoreria.selectores import identificador_valido
from .models import Solicitud, TipoSolicitud, Adjunto
from .autorizacion import puede_entrar, comites_gestionables, responsables, visibles
from .forms import NuevaSolicitudForm, SeguimientoForm
from .filtros import BandejaFilter, ABIERTAS
from .services import crear, actualizar, token_nuevo, Conflicto


def exigir(usuario):
    if not puede_entrar(usuario):
        raise Http404


def retorno(request):
    url = request.POST.get('return_to') or request.GET.get('return_to', '')
    return url if url.startswith('/') and url_has_allowed_host_and_scheme(url, {request.get_host()}, require_https=request.is_secure()) else reverse('secretaria:bandeja')


def detalle_url(solicitud, volver):
    return reverse('secretaria:detalle', args=[solicitud.pk]) + '?' + urlencode({'return_to': volver})


@login_required
@require_GET
def bandeja(request):
    exigir(request.user)
    base = visibles(request.user)
    hoy = timezone.localdate()
    abiertas = Q(estado__in=ABIERTAS)
    contadores = base.aggregate(
        mis_pendientes=Count('pk', filter=abiertas & Q(responsable=request.user)),
        sin_asignar=Count('pk', filter=abiertas & Q(responsable__isnull=True)),
        vencidas=Count('pk', filter=abiertas & Q(fecha_compromiso__lt=hoy)),
        proximas=Count('pk', filter=abiertas & Q(fecha_compromiso__range=(hoy, hoy+timedelta(days=7)))),
    )
    filtro = BandejaFilter(request.GET, queryset=base, usuario=request.user)
    qs = filtro.qs if filtro.is_valid() else base.none()
    pagina = Paginator(qs.order_by('-created_at', '-pk'), 20).get_page(request.GET.get('page'))
    params = request.GET.copy(); params.pop('page', None)
    # Choices derive from the authorized scope, not global account lists.
    from django.contrib.auth import get_user_model
    return render(request, 'secretaria/bandeja.html', {'pagina': pagina, 'filtro': filtro, 'contadores': contadores, 'estados': Solicitud.Estados.choices,
        'tipos': TipoSolicitud.objects.filter(pk__in=base.values('tipo_id')), 'comites': comites_gestionables(request.user) if request.user.is_superuser else Comite.objects.filter(pk__in=base.values('comite_id')),
        'responsables': get_user_model().objects.filter(pk__in=base.values('responsable_id')), 'puede_crear': comites_gestionables(request.user).exists(), 'consulta': params.urlencode(), 'contexto': request.get_full_path()})


@login_required
@require_http_methods(['GET', 'POST'])
def nueva(request):
    if not comites_gestionables(request.user).exists():
        raise Http404
    codigo = 200
    inicial = {'token': token_nuevo(request.user)}
    ciudadano_id = identificador_valido(request.GET.get('ciudadano'))
    if ciudadano_id:
        inicial['ciudadano'] = get_object_or_404(Ciudadano.objects.visibles_para(request.user), pk=ciudadano_id).pk
    comites = comites_gestionables(request.user)
    if comites.count() == 1: inicial['comite'] = comites.first().pk
    form = NuevaSolicitudForm(request.POST if request.method == 'POST' else None, request.FILES or None, usuario=request.user, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        try:
            solicitud, creada = crear(request.user, form.cleaned_data, form.cleaned_data['token'], form.cleaned_data.get('archivo'))
        except ValidationError as exc:
            form.add_error(None, exc)
            codigo = 409 if isinstance(exc, Conflicto) else 400
        else:
            messages.success(request, 'Solicitud registrada.' if creada else 'Este envío ya fue registrado; mostramos la solicitud original.')
            return redirect(detalle_url(solicitud, retorno(request)))
    return render(request, 'secretaria/form.html', {'form': form, 'titulo': 'Registrar solicitud', 'return_to': retorno(request), 'sin_tipos': not TipoSolicitud.objects.filter(activo=True).exists()}, status=codigo)


@login_required
@require_http_methods(['GET', 'POST'])
def detalle(request, pk):
    solicitud = get_object_or_404(visibles(request.user), pk=pk)
    form = None
    codigo = 200
    if request.method == 'POST' and solicitud.cerrada:
        return render(request, 'secretaria/detalle.html', {'solicitud': solicitud, 'historial': solicitud.historial.select_related('autor'), 'adjuntos': solicitud.adjuntos.all(), 'return_to': retorno(request), 'error': 'La solicitud está cerrada.'}, status=409)
    if not solicitud.cerrada:
        form = SeguimientoForm(request.POST if request.method == 'POST' else None, request.FILES or None, usuario=request.user, solicitud=solicitud, initial={'version': solicitud.version, 'estado': solicitud.estado, 'responsable': solicitud.responsable_id, 'fecha_compromiso': solicitud.fecha_compromiso})
        if request.method == 'POST' and form.is_valid():
            try:
                actualizar(request.user, pk, form.cleaned_data['version'], form.cleaned_data, form.cleaned_data.get('archivo'))
            except ValidationError as exc:
                form.add_error(None, exc)
                codigo = 409 if isinstance(exc, Conflicto) else 400
            else:
                messages.success(request, 'Seguimiento guardado.')
                return redirect(detalle_url(solicitud, retorno(request)))
    return render(request, 'secretaria/detalle.html', {'solicitud': solicitud, 'form': form, 'historial': solicitud.historial.select_related('autor'), 'adjuntos': solicitud.adjuntos.all(), 'return_to': retorno(request)}, status=codigo)


@login_required
@require_GET
@never_cache
def constancia(request, pk):
    solicitud = get_object_or_404(visibles(request.user), pk=pk)
    return render(request, 'secretaria/constancia.html', {'solicitud': solicitud})


@login_required
@require_GET
@never_cache
def descargar(request, pk, adjunto_id):
    solicitud = get_object_or_404(visibles(request.user), pk=pk)
    adjunto = get_object_or_404(Adjunto, pk=adjunto_id, solicitud=solicitud)
    try:
        response = FileResponse(adjunto.archivo.open('rb'), as_attachment=True, filename=adjunto.nombre, content_type='application/octet-stream')
    except FileNotFoundError:
        raise Http404('El archivo no está disponible.')
    response['X-Content-Type-Options'] = 'nosniff'
    return response


class CiudadanosAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    paginate_by = 20

    def get_queryset(self):
        if not comites_gestionables(self.request.user).exists(): raise Http404
        qs = Ciudadano.objects.visibles_para(self.request.user).order_by('apellido_paterno', 'apellido_materno', 'nombre', 'pk')
        return qs.filter(filtro_busqueda_ciudadano(self.q[:200], extra_fields=('toma__numero_toma',))) if len(self.q.strip()) >= 2 else qs.none()

    def get_result_label(self, ciudadano):
        return f'{ciudadano.nombre_completo} · Contrato {ciudadano.numero_contrato or "sin registro"} · ID {ciudadano.pk}'


class ResponsablesAutocomplete(LoginRequiredMixin, autocomplete.Select2QuerySetView):
    paginate_by = 20

    def get_queryset(self):
        comite_id = identificador_valido(self.forwarded.get('comite'))
        ciudadano_id = identificador_valido(self.forwarded.get('ciudadano'))
        if not comites_gestionables(self.request.user).filter(pk=comite_id).exists(): raise Http404
        ciudadano = get_object_or_404(Ciudadano.objects.visibles_para(self.request.user), pk=ciudadano_id)
        return responsables(comite_id, ciudadano).filter(Q(username__icontains=self.q[:100]) | Q(first_name__icontains=self.q[:100]) | Q(last_name__icontains=self.q[:100]))
