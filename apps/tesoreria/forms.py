from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.forms import DashboardFormMixin
from apps.operacion.alcance import manzanas_disponibles_para_instancia
from .models import Abono, ConceptoTesoreria, ObligacionCiudadano


class BuscarAportacionesForm(DashboardFormMixin, forms.Form):
    """Valida la URL compartible de la búsqueda de movimientos."""

    q = forms.CharField(required=False, label="Buscar ciudadano, contrato o concepto")
    mes = forms.ChoiceField(required=False, choices=[("todos", "Todos")], label="Mes")
    anio = forms.ChoiceField(required=False, choices=[("todos", "Todos")], label="Año")
    naturaleza = forms.ChoiceField(
        required=False, label="Naturaleza",
        choices=[("todos", "Todas"), *ConceptoTesoreria.Naturalezas.choices],
    )
    alcance = forms.ChoiceField(
        required=False, label="Alcance",
        choices=[("todos", "Todos"), *ConceptoTesoreria.Alcances.choices],
    )
    manzana = forms.ChoiceField(required=False, choices=[("todas", "Todas las manzanas")], label="Manzana")
    comite = forms.ChoiceField(required=False, choices=[("todos", "Todos los comités")], label="Comité")
    concepto = forms.CharField(required=False, label="Concepto")
    estado = forms.ChoiceField(
        required=False, label="Estado de la obligación",
        choices=[("todos", "Todos"), *ObligacionCiudadano.Estados.choices],
    )
    fecha_inicial = forms.DateField(required=False, label="Fecha inicial", widget=forms.DateInput(attrs={"type": "date"}))
    fecha_final = forms.DateField(required=False, label="Fecha final", widget=forms.DateInput(attrs={"type": "date"}))
    importe_minimo = forms.DecimalField(required=False, min_value=0, label="Importe mínimo")
    importe_maximo = forms.DecimalField(required=False, min_value=0, label="Importe máximo")
    orden = forms.ChoiceField(required=False, choices=[
        ("reciente", "Más reciente"), ("antiguo", "Más antiguo"),
        ("mayor_importe", "Mayor importe"), ("menor_importe", "Menor importe"),
        ("ciudadano", "Ciudadano"), ("concepto", "Concepto"),
    ])
    por_pagina = forms.ChoiceField(required=False, choices=[("10", "10"), ("25", "25"), ("50", "50")])

    def __init__(self, *args, anios=(), manzanas=(), comites=(), meses=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mes"].choices += [(str(v), n) for v, n in meses]
        self.fields["anio"].choices += [(str(a), str(a)) for a in anios]
        self.fields["manzana"].choices += [(str(m.pk), str(m)) for m in manzanas]
        self.fields["comite"].choices += [(str(c.pk), c.nombre) for c in comites]
        self.fields["q"].widget.attrs.update({"placeholder": "Nombre, apellidos, contrato o concepto", "autocomplete": "off"})
        self.fields["concepto"].widget.attrs["placeholder"] = "Nombre o descripción"
        self._apply_dashboard_widgets()

    def clean(self):
        data = super().clean()
        if data.get("fecha_inicial") and data.get("fecha_final") and data["fecha_inicial"] > data["fecha_final"]:
            self.add_error("fecha_final", "La fecha final debe ser posterior a la fecha inicial.")
        if data.get("importe_minimo") is not None and data.get("importe_maximo") is not None and data["importe_minimo"] > data["importe_maximo"]:
            self.add_error("importe_maximo", "El importe máximo debe ser mayor o igual al mínimo.")
        return data


class ConceptoTesoreriaForm(DashboardFormMixin, forms.ModelForm):
    class Meta:
        model = ConceptoTesoreria
        fields = ["naturaleza", "alcance", "manzana", "comite", "concepto", "descripcion", "monto_individual", "fecha", "anio_periodo"]
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"}), "descripcion": forms.Textarea(attrs={"rows": 4})}
        labels = {
            "naturaleza": "Pago o Cooperación",
            "alcance": "Alcance",
            "manzana": "Manzana",
            "comite": "Comité",
            "concepto": "Concepto",
            "descripcion": "Descripción",
            "monto_individual": "Monto individual",
            "fecha": "Fecha",
            "anio_periodo": "Año del periodo (opcional)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manzana"].queryset = manzanas_disponibles_para_instancia(self.instance)
        self.fields["manzana"].empty_label = "Selecciona una manzana"
        self._apply_dashboard_widgets()


class AbonoForm(DashboardFormMixin, forms.ModelForm):
    class Meta:
        model = Abono
        fields = ["monto", "fecha", "notas"]
        widgets = {"fecha": forms.DateInput(attrs={"type": "date"}), "notas": forms.Textarea(attrs={"rows": 3})}
        labels = {"monto": "Monto a abonar", "fecha": "Fecha", "notas": "Notas"}

    def __init__(self, *args, obligacion=None, **kwargs):
        self.obligacion = obligacion
        super().__init__(*args, **kwargs)
        self._apply_dashboard_widgets()
        if not self.is_bound:
            self.fields["fecha"].initial = timezone.localdate()
            if obligacion:
                self.fields["monto"].initial = obligacion.saldo_pendiente

    def clean_monto(self):
        monto = self.cleaned_data["monto"]
        if monto <= 0:
            raise ValidationError("El monto del abono debe ser mayor que cero.")
        if self.obligacion and monto > self.obligacion.saldo_pendiente:
            raise ValidationError(f"El abono no puede superar el saldo pendiente de ${self.obligacion.saldo_pendiente:.2f}.")
        return monto
