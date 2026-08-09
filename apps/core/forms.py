from django import forms
from apps.operacion.models import Faena, Junta
from apps.operacion.alcance import manzanas_disponibles_para_instancia

from .models import Ciudadano, Manzana


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
        fields = ["comite", "fecha", "descripcion", "alcance", "manzana", "estado", "notas"]
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
            "manzana": "Selecciona una manzana únicamente cuando el alcance sea Por manzana.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manzana"].queryset = manzanas_disponibles_para_instancia(self.instance)
        self.fields["manzana"].empty_label = "Selecciona una manzana"
        self._apply_dashboard_widgets()

    def clean_manzana(self):
        manzana = self.cleaned_data.get("manzana")
        if manzana and not manzana.activa and manzana.pk != self.instance.manzana_id:
            raise forms.ValidationError("Selecciona una manzana activa.")
        return manzana


class JuntaOperativaForm(DashboardFormMixin, forms.ModelForm):
    class Meta:
        model = Junta
        fields = ["comite", "fecha", "tipo", "lugar", "tema", "alcance", "manzana", "estado", "notas"]
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
            "estado": "Estado",
            "notas": "Notas operativas",
        }
        help_texts = {
            "tema": "Resume el motivo o asunto principal de la reunión.",
            "lugar": "Indica dónde se realizará la junta si ya está definido.",
            "notas": "Agrega acuerdos previos, indicaciones o contexto para seguimiento.",
            "manzana": "Selecciona una manzana únicamente cuando el alcance sea Por manzana.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manzana"].queryset = manzanas_disponibles_para_instancia(self.instance)
        self.fields["manzana"].empty_label = "Selecciona una manzana"
        self._apply_dashboard_widgets()

    def clean_manzana(self):
        manzana = self.cleaned_data.get("manzana")
        if manzana and not manzana.activa and manzana.pk != self.instance.manzana_id:
            raise forms.ValidationError("Selecciona una manzana activa.")
        return manzana


class CiudadanoOperativoForm(DashboardFormMixin, forms.ModelForm):
    class Meta:
        model = Ciudadano
        fields = [
            "nombre",
            "apellido_paterno",
            "apellido_materno",
            "edad",
            "fecha_nacimiento",
            "sexo",
            "numero_contrato",
            "manzana",
            "labor_social",
            "motivo_alta",
            "direccion",
            "activo",
            "observaciones",
        ]
        widgets = {
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date"}),
            "direccion": forms.Textarea(attrs={"rows": 3}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "nombre": "Nombre",
            "apellido_paterno": "Apellido paterno",
            "apellido_materno": "Apellido materno",
            "edad": "Edad registrada",
            "fecha_nacimiento": "Fecha de nacimiento",
            "numero_contrato": "No. de contrato",
            "motivo_alta": "Motivo de alta",
            "direccion": "Domicilio o referencia",
            "activo": "Ciudadano activo",
            "observaciones": "Observaciones",
        }
        help_texts = {
            "edad": "Dato heredado opcional; se usa solo cuando no hay fecha de nacimiento.",
            "fecha_nacimiento": "Cuando existe, determina automáticamente la edad actual.",
            "numero_contrato": "Opcional; admite letras, guiones y ceros iniciales.",
            "manzana": "Opcional; selecciona la manzana identificada para el ciudadano.",
            "motivo_alta": "Selecciona la razón por la que la persona se incorpora al padrón.",
            "direccion": "Agrega domicilio, barrio, referencia o ubicación conocida.",
            "activo": "Mantén esta opción marcada para incluirlo en la operación diaria.",
            "observaciones": "Notas internas relevantes para el expediente ciudadano.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manzana"].queryset = manzanas_disponibles_para_instancia(self.instance)
        self.fields["manzana"].empty_label = "Sin asignar"
        self._apply_dashboard_widgets()
        self.fields["activo"].widget.attrs["class"] = "h-4 w-4 rounded border-slate-300 text-indigo-600"
