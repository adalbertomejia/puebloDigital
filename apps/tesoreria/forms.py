from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.forms import DashboardFormMixin
from apps.operacion.alcance import manzanas_disponibles_para_instancia
from .models import Abono, ConceptoTesoreria


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
