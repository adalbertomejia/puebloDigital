"""Operational collection/report/resource screens; no duplicate Treasury system."""
import csv
import hashlib
from contextlib import contextmanager
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from . import balances, recursos
from .models import CorteRecurso, MovimientoRecurso
from .autorizacion import tiene_acceso_financiero
from .balance_autorizacion import exigir_balance, fondos_visibles, puede_gestionar_fondo, puede_preparar_corte, puede_revisar_corte
from .balance_forms import BalanceFiltroForm, FondoForm, SalidaForm, CorteForm, RevisionCorteForm, opciones_fondo


@contextmanager
def lectura_consistente():
    exterior = not connection.in_atomic_block
    with transaction.atomic():
        if exterior and connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        yield


def filtro(request):
    hoy = timezone.localdate()
    data = request.GET if request.GET else {"desde":hoy.replace(day=1), "hasta":hoy}
    form = BalanceFiltroForm(data, usuario=request.user)
    return form, form.cleaned_data if form.is_valid() else None


def contexto_filtro(request, form, data):
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return {"form":form, "filtros":data, "generado":timezone.now(), "querystring":parametros.urlencode(), "metodologia":"Recaudación por fecha de pago; cartera de conceptos del periodo con estados actuales. Aperturas y salidas de recursos se muestran por separado."}


@login_required
@require_GET
def balance_recaudacion(request):
    exigir_balance(request.user)
    form, data = filtro(request)
    with lectura_consistente():
        datos = balances.datos_balance(request.user, data) if data else None
        fondos = []
        for fondo in fondos_visibles(request.user).filter(activo=True):
            fondos.append({"fondo":fondo, **recursos.resumen_fondo(fondo)})
        cortes = CorteRecurso.objects.filter(fondo__in=fondos_visibles(request.user)).select_related("fondo").order_by("-hasta")[:5]
        return render(request, "dashboard/balance/resumen.html", {**contexto_filtro(request, form, data), "datos":datos, "fondos":fondos, "cortes":cortes})


@login_required
@require_GET
def balance_conceptos(request):
    exigir_balance(request.user)
    form, data = filtro(request)
    qs = balances.filas_conceptos(request.user, data) if data else balances.conceptos_autorizados(request.user).none()
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    for concepto in page.object_list:
        ob = balances.obligaciones_autorizadas(request.user).filter(concepto=concepto)
        if data and data.get("estado"):
            ob = ob.filter(estado=data["estado"])
        concepto.balance = balances.resumen_cartera(ob)
    return render(request, "dashboard/balance/conceptos.html", {**contexto_filtro(request,form,data), "page":page})


@login_required
@require_GET
def balance_concepto_detalle(request, pk):
    exigir_balance(request.user)
    concepto = get_object_or_404(balances.conceptos_autorizados(request.user), pk=pk)
    qs = balances.obligaciones_autorizadas(request.user).filter(concepto=concepto)
    page = Paginator(balances.cartera(qs).select_related("ciudadano").order_by("ciudadano__apellido_paterno", "pk"), 25).get_page(request.GET.get("page")) if tiene_acceso_financiero(request.user) else None
    if page:
        for o in page.object_list:
            o.saldo_balance = None if o.monto_asignado is None or o.abonos_desconocidos else max(o.monto_asignado-o.abonado_conocido, Decimal("0.00"))
    return render(request,"dashboard/balance/detalle.html",{"concepto":concepto, "cartera":balances.resumen_cartera(qs), "page":page, "individual":tiene_acceso_financiero(request.user)})


@login_required
@require_GET
def balance_transparencia(request):
    exigir_balance(request.user)
    form, data = filtro(request)
    with lectura_consistente():
        datos = balances.datos_balance(request.user,data) if data else None
        base = f"{data}|{datos['recaudacion'] if datos else 'invalido'}|{datos['origenes'] if datos else ''}|{datos['cartera'] if datos else ''}"
        if datos:
            base += str({k: datos[k] for k in ("por_comite", "por_territorio", "mensual", "cobros_canceladas", "cobros_sin_fondo")})
        referencia = hashlib.sha256(base.encode()).hexdigest()[:16].upper()
        if request.GET.get("exportar") == "csv":
            if data is None:
                return HttpResponse("Filtros inválidos o fuera de tu ámbito.",status=400)
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"]='attachment; filename="transparencia-recaudacion.csv"'
            response.write("\ufeff")
            w=csv.writer(response)
            w.writerow(["Informe agregado privado", "Sin datos personales"])
            w.writerow(["Periodo de cobros y cohorte",data["desde"],data["hasta"]])
            w.writerow(["Generado",timezone.now().isoformat(), "Zona", "America/Mexico_City"])
            w.writerow(["Alcance","Recursos autorizados a la cuenta autenticada", "Comité solicitado", getattr(data.get("comite"), "pk", "Todos los autorizados"), "Manzana solicitada",getattr(data.get("manzana"),"pk","Todas las autorizadas")])
            w.writerow(["Metodología","Ingresos por fecha de pago; cartera con estados actuales; no incluye aperturas ni pagos históricos independientes", "Referencia",referencia])
            w.writerow(["Origen", "Cobrado conocido", "Importes desconocidos"])
            for r in datos["origenes"]:
                w.writerow([r["etiqueta"],r["conocido"],r["desconocidos"]])
            w.writerow(["Total recibido conocido",datos["recaudacion"]["conocido"],datos["recaudacion"]["desconocidos"]])
            w.writerow(["Asignado vigente conocido",datos["cartera"]["asignado"]["conocido"],datos["cartera"]["asignado"]["desconocidos"]])
            w.writerow(["Saldo actual de cohorte",datos["cartera"]["saldo"] if datos["cartera"]["saldo"] is not None else "Indeterminado"])
            return response
        return render(request,"dashboard/balance/transparencia.html",{**contexto_filtro(request,form,data), "datos":datos, "referencia":referencia})


@login_required
@require_GET
def fondos_recursos(request):
    exigir_balance(request.user)
    fondos = []
    for fondo in fondos_visibles(request.user):
        fondos.append({"fondo":fondo, **recursos.resumen_fondo(fondo)})
    comites, _, _ = opciones_fondo(request.user)
    return render(request,"dashboard/balance/fondos.html",{"fondos":fondos, "puede_crear":comites.exists()})


@login_required
@require_http_methods(["GET","POST"])
def fondo_crear(request):
    comites, _, _ = opciones_fondo(request.user)
    if not comites.exists():
        raise Http404
    form = FondoForm(request.POST if request.method == "POST" else None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            fondo = recursos.abrir_fondo(usuario=request.user, **form.cleaned_data)
        except ValidationError as e:
            form.add_error(None,e)
        else:
            messages.success(request,"Fondo registrado con su apertura documentada. No requiere revisión.")
            return redirect("fondo_recurso_detalle",fondo.pk)
    return render(request,"dashboard/balance/formulario.html",{"form":form,"titulo":"Registrar recurso inicial", "descripcion":"La apertura representa dinero que ya existe. No selecciones abonos que ya estén incluidos en ella.", "cancelar":reverse("fondos_recursos")})


@login_required
@require_GET
def fondo_detalle(request, pk):
    fondo = get_object_or_404(fondos_visibles(request.user), pk=pk)
    page=Paginator(fondo.movimientos.select_related("registrado_por").all(),25).get_page(request.GET.get("page"))
    return render(request,"dashboard/balance/fondo_detalle.html",{"fondo":fondo,"saldo":recursos.resumen_fondo(fondo),"page":page,"gestionar":puede_gestionar_fondo(request.user,fondo),"preparar":puede_preparar_corte(request.user,fondo)})


@login_required
@require_http_methods(["GET","POST"])
def fondo_salida(request, pk):
    fondo = get_object_or_404(fondos_visibles(request.user), pk=pk)
    if not puede_gestionar_fondo(request.user,fondo):
        raise Http404
    form=SalidaForm(request.POST if request.method=="POST" else None)
    if request.method=="POST" and form.is_valid():
        try:
            mov=recursos.registrar_salida(usuario=request.user,fondo=fondo,**form.cleaned_data)
        except ValidationError as e:
            form.add_error(None,e)
        else:
            messages.success(request,"Salida documentada. Su comprobante e historial se conservaron.")
            return redirect("comprobante_recurso",mov.pk)
    return render(request,"dashboard/balance/formulario.html",{"form":form,"titulo":"Registrar salida documentada", "descripcion":f"{fondo.nombre}. Se valida el disponible del medio elegido. El comprobante será interno e imprimible.","cancelar":reverse("fondo_recurso_detalle",args=[fondo.pk])})


@login_required
@require_GET
def comprobante_recurso(request, pk):
    mov = get_object_or_404(MovimientoRecurso.objects.filter(fondo__in=fondos_visibles(request.user)).select_related("fondo__comite","fondo__manzana","registrado_por"),pk=pk)
    return render(request,"dashboard/balance/comprobante.html",{"mov":mov})


@login_required
@require_http_methods(["GET","POST"])
def preparar_corte(request, pk):
    fondo=get_object_or_404(fondos_visibles(request.user),pk=pk)
    if not puede_preparar_corte(request.user,fondo):
        raise Http404
    form=CorteForm(request.POST if request.method=="POST" else None,initial={"version":recursos.version_corte(fondo)})
    if request.method=="POST" and form.is_valid():
        try:
            corte=recursos.enviar_corte(usuario=request.user,fondo=fondo,**form.cleaned_data)
        except ValidationError as e:
            form.add_error(None,e)
        else:
            messages.success(request,"Corte enviado a revisión. Ya se puede consultar e imprimir en modo lectura.")
            return redirect("corte_recurso_detalle",corte.pk)
    return render(request,"dashboard/balance/corte_preparar.html",{"form":form,"fondo":fondo,"resumen":recursos.manifiesto_corte(fondo)})


@login_required
@require_GET
def cortes_recursos(request):
    exigir_balance(request.user)
    qs=CorteRecurso.objects.filter(fondo__in=fondos_visibles(request.user)).select_related("fondo__comite","preparado_por","revisado_por")
    return render(request,"dashboard/balance/cortes.html",{"page":Paginator(qs,25).get_page(request.GET.get("page"))})


@login_required
@require_GET
def corte_detalle(request, pk):
    corte=get_object_or_404(CorteRecurso.objects.filter(fondo__in=fondos_visibles(request.user)).select_related("fondo__comite","fondo__manzana","preparado_por","revisado_por"),pk=pk)
    return render(request,"dashboard/balance/corte_detalle.html",{"corte":corte,"revision":puede_revisar_corte(request.user,corte) and corte.estado=="EN_REVISION", "form":RevisionCorteForm(),"eventos":corte.eventos.select_related("usuario").all()})


@login_required
@require_POST
def corte_revisar(request, pk):
    corte=get_object_or_404(CorteRecurso.objects.filter(fondo__in=fondos_visibles(request.user)).select_related("fondo__comite"),pk=pk)
    if not puede_revisar_corte(request.user,corte):
        raise Http404
    form=RevisionCorteForm(request.POST)
    if form.is_valid():
        try:
            recursos.revisar_corte(usuario=request.user,corte=corte,**form.cleaned_data)
        except ValidationError as e:
            messages.error(request," ".join(e.messages))
        else:
            messages.success(request,"Revisión registrada. El corte conserva las cifras que fueron enviadas.")
    else:
        messages.error(request,"Indica una decisión y las observaciones de revisión.")
    return redirect("corte_recurso_detalle",corte.pk)
