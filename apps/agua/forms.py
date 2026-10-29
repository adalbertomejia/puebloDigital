from decimal import Decimal
from django import forms
from apps.core.forms import DashboardFormMixin


class CuotaMensualAguaForm(DashboardFormMixin, forms.Form):
    periodo = forms.DateField(label="Mes de la cuota", input_formats=["%Y-%m"], widget=forms.DateInput(format="%Y-%m", attrs={"type": "month"}))
    monto = forms.DecimalField(label="Cuota mensual por toma", min_value=Decimal("0.01"), max_digits=10, decimal_places=2)
    descripcion = forms.CharField(label="Descripción", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_dashboard_widgets()
