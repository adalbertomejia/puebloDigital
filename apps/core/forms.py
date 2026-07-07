from django import forms

from apps.operacion.models import Faena, Junta


class DashboardFormMixin:
    """Apply consistent dashboard styling to operational forms."""

    field_classes = {
        forms.DateInput: "rounded-lg border px-3 py-2 w-full bg-white",
        forms.Select: "rounded-lg border px-3 py-2 w-full bg-white",
        forms.Textarea: "rounded-lg border px-3 py-2 w-full bg-white min-h-28",
    }
    default_class = "rounded-lg border px-3 py-2 w-full bg-white"

    def _apply_dashboard_widgets(self):
        for field in self.fields.values():
            widget = field.widget
            css_class = self.default_class
            for widget_type, widget_class in self.field_classes.items():
                if isinstance(widget, widget_type):
                    css_class = widget_class
                    break
            existing_class = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{existing_class} {css_class}".strip()


class FaenaOperativaForm(DashboardFormMixin, forms.ModelForm):
    class Meta:
        model = Faena
        fields = ["comite", "fecha", "descripcion", "estado", "notas"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
            "notas": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {
            "comite": "Comité responsable",
            "fecha": "Fecha programada",
            "descripcion": "Descripción de la faena",
            "estado": "Estado",
            "notas": "Notas operativas",
        }
        help_texts = {
            "descripcion": "Describe de forma breve el trabajo comunitario a realizar.",
            "notas": "Agrega indicaciones para la secretaría o el equipo operativo si hace falta.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_dashboard_widgets()


class JuntaOperativaForm(DashboardFormMixin, forms.ModelForm):
    class Meta:
        model = Junta
        fields = ["comite", "fecha", "tipo", "lugar", "tema", "notas"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
            "notas": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {
            "comite": "Comité convocante",
            "fecha": "Fecha de la junta",
            "tipo": "Tipo de junta",
            "lugar": "Lugar",
            "tema": "Tema principal",
            "notas": "Notas operativas",
        }
        help_texts = {
            "tema": "Resume el motivo o asunto principal de la reunión.",
            "lugar": "Indica dónde se realizará la junta si ya está definido.",
            "notas": "Agrega acuerdos previos, indicaciones o contexto para seguimiento.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_dashboard_widgets()
