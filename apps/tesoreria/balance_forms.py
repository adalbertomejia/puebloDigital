import calendar
import uuid
from decimal import Decimal
from datetime import date
from django import forms
from django.utils import timezone
from apps.core.forms import DashboardFormMixin
from apps.comites.models import Comite
from apps.core.models import Manzana
from .models import ConceptoTesoreria, ObligacionCiudadano, FondoRecurso, MovimientoRecurso
from .balance_autorizacion import comites_de_fondos_secretaria, fondos_visibles
from apps.core.autorizacion import responsabilidades_activas


def estilo(form):
    # Same operational controls as the dashboard, native selectors for short lists.
    for field in form.fields.values():
        field.widget.attrs["class"] = "pd-input rounded-lg border px-3 py-2 w-full bg-white"


class BalanceFiltroForm(forms.Form):
    desde = forms.DateField(required=False, widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}), label="Cobros y conceptos desde")
    hasta = forms.DateField(required=False, widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}), label="Hasta")
    anio = forms.IntegerField(required=False, min_value=1, max_value=9999, label="Año (opcional)")
    mes = forms.TypedChoiceField(required=False, coerce=int, empty_value=None, choices=[("", "Todos los meses"), *[(i, str(i)) for i in range(1,13)]])
    origen = forms.ChoiceField(required=False, choices=[("", "Todos los orígenes"), *ConceptoTesoreria.Origenes.choices])
    naturaleza = forms.ChoiceField(required=False, choices=[("", "Pagos y cooperaciones"), *ConceptoTesoreria.Naturalezas.choices])
    comite = forms.ModelChoiceField(queryset=Comite.objects.none(), required=False, empty_label="Comités autorizados")
    manzana = forms.ModelChoiceField(queryset=Manzana.objects.none(), required=False, empty_label="Territorios autorizados")
    estado = forms.ChoiceField(required=False, choices=[("", "Todos los estados"), *ObligacionCiudadano.Estados.choices])
    q = forms.CharField(required=False, max_length=200, label="Buscar concepto")

    def __init__(self, *args, usuario, **kwargs):
        from .balances import conceptos_autorizados
        super().__init__(*args, **kwargs)
        qs = conceptos_autorizados(usuario)
        fondos = fondos_visibles(usuario)
        self.fields["comite"].queryset = Comite.objects.filter(Q(pk__in=qs.values("comite_id"))|Q(pk__in=fondos.values("comite_id"))).distinct()
        self.fields["manzana"].queryset = Manzana.objects.filter(Q(pk__in=qs.values("manzana_id"))|Q(pk__in=fondos.values("manzana_id"))).distinct()
        estilo(self)

    def clean(self):
        d = super().clean()
        hoy = timezone.localdate()
        if d.get("mes") and not d.get("anio"):
            self.add_error("anio", "Indica el año del mes seleccionado.")
        if d.get("anio") and (d.get("desde") or d.get("hasta")):
            self.add_error("anio", "Usa un rango de fechas o un año/mes, no ambos.")
        if d.get("anio"):
            year, month = d["anio"], d.get("mes")
            d["desde"] = date(year, month or 1, 1)
            d["hasta"] = date(year, month or 12, calendar.monthrange(year, month or 12)[1])
        else:
            d["desde"] = d.get("desde") or hoy.replace(day=1)
            d["hasta"] = d.get("hasta") or hoy
        if d["desde"] > d["hasta"]:
            self.add_error("hasta", "La fecha final debe ser igual o posterior a la inicial.")
        return d


from django.db.models import Q


def opciones_fondo(user):
    rs = responsabilidades_activas(user)
    ids = [r.comite.pk for r in rs if r.tipo == "COMITE" and r.rol in ("PRESIDENTE", "TESORERO")]
    manzanas = [r.manzana.pk for r in rs if r.tipo == "MANZANA"]
    comites = Comite.objects.filter(activo=True, pk__in=ids)
    comites = comites | comites_de_fondos_secretaria(user)
    if manzanas:
        comites = Comite.objects.filter(activo=True)
    return comites.distinct(), Manzana.objects.filter(activa=True, pk__in=manzanas), bool(manzanas)


class FondoForm(forms.ModelForm):
    clave_apertura = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    class Meta:
        model = FondoRecurso
        fields = ["nombre", "categoria", "comite", "manzana", "fecha_apertura", "inicial_efectivo", "inicial_transferencia", "evidencia_apertura"]
        widgets = {"fecha_apertura": forms.DateInput(format="%Y-%m-%d", attrs={"type":"date"})}
        labels = {"inicial_efectivo":"Efectivo inicial documentado", "inicial_transferencia":"Recursos iniciales por transferencia", "evidencia_apertura":"Referencia del acta o evidencia de apertura", "manzana":"Manzana (vacía para el comité completo)"}

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        comites, manzanas, self.territorial = opciones_fondo(usuario)
        self.fields["comite"].queryset = comites
        self.fields["manzana"].queryset = manzanas if self.territorial else Manzana.objects.filter(activa=True)
        self.fields["manzana"].required = self.territorial
        self.fields["fecha_apertura"].initial = timezone.localdate()
        estilo(self)

    def clean_fecha_apertura(self):
        value = self.cleaned_data["fecha_apertura"]
        if value > timezone.localdate():
            raise forms.ValidationError("La apertura no puede estar en el futuro.")
        return value


class SalidaForm(forms.Form):
    monto = forms.DecimalField(min_value=Decimal("0.01"), max_digits=14, decimal_places=2)
    medio = forms.ChoiceField(choices=MovimientoRecurso.Medios.choices)
    fecha = forms.DateField(widget=forms.DateInput(format="%Y-%m-%d", attrs={"type":"date"}))
    categoria_salida = forms.ChoiceField(choices=MovimientoRecurso.CategoriasSalida.choices, label="Categoría del gasto")
    descripcion = forms.CharField(max_length=250, label="Motivo de la salida")
    beneficiario = forms.CharField(max_length=150, required=False, label="Beneficiario o proveedor (dato privado)")
    evidencia = forms.CharField(max_length=250, label="Referencia del comprobante o evidencia del gasto")
    clave_operacion = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fecha"].initial = timezone.localdate()
        self.fields["clave_operacion"].initial = uuid.uuid4
        estilo(self)


class CorteForm(forms.Form):
    contado = forms.DecimalField(min_value=Decimal("0"), max_digits=14, decimal_places=2, label="Efectivo contado físicamente")
    aclaracion = forms.CharField(required=False, max_length=4000, widget=forms.Textarea(attrs={"rows":3}), label="Aclaración de diferencia")
    evidencia_conteo = forms.CharField(max_length=250, label="Referencia del acta de conteo y comprobantes revisados")
    version = forms.CharField(widget=forms.HiddenInput)
    clave_operacion = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["clave_operacion"].initial = uuid.uuid4
        estilo(self)


class RevisionCorteForm(forms.Form):
    accion = forms.ChoiceField(choices=[("DEVOLVER", "Solicitar aclaración"), ("CONFIRMAR", "Confirmar corte cuadrado")])
    motivo = forms.CharField(max_length=4000, widget=forms.Textarea(attrs={"rows":3}), label="Observaciones de revisión")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        estilo(self)
