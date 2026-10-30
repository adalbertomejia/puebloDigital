from django import forms
from dal import autocomplete
from apps.core.models import Ciudadano
from apps.tesoreria.selectores import identificador_valido
from .models import Solicitud, TipoSolicitud
from .autorizacion import comites_gestionables, responsables, puede_asignar
from .archivos import validar_adjunto


def estilos(form):
    for campo in form.fields.values():
        campo.widget.attrs['class'] = 'rounded-lg border px-3 py-2 w-full bg-white'


class NuevaSolicitudForm(forms.ModelForm):
    token = forms.CharField(widget=forms.HiddenInput)
    archivo = forms.FileField(required=False, label='Adjunto opcional', validators=[validar_adjunto], help_text='PDF, PNG o JPEG; máximo 5 MB.')

    class Meta:
        model = Solicitud
        fields = ('ciudadano', 'tipo', 'descripcion', 'comite', 'responsable', 'fecha_compromiso')
        widgets = {'ciudadano': autocomplete.ModelSelect2(url='secretaria:ciudadanos', attrs={'data-minimum-input-length': 2, 'data-width': '100%'}), 'descripcion': forms.Textarea(attrs={'rows': 3}), 'fecha_compromiso': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}
        labels = {'descripcion': 'Descripción breve', 'comite': 'Comité responsable', 'responsable': 'Responsable (opcional)', 'fecha_compromiso': 'Fecha de compromiso (opcional)'}

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ciudadano'].queryset = Ciudadano.objects.visibles_para(usuario).order_by('apellido_paterno', 'apellido_materno', 'nombre', 'pk')
        self.fields['comite'].queryset = comites_gestionables(usuario)
        self.fields['tipo'].queryset = TipoSolicitud.objects.filter(activo=True)
        comite_id = identificador_valido(self.data.get('comite') if self.is_bound else self.initial.get('comite'))
        ciudadano_id = identificador_valido(self.data.get('ciudadano') if self.is_bound else self.initial.get('ciudadano'))
        ciudadano = self.fields['ciudadano'].queryset.filter(pk=ciudadano_id).first()
        from django.contrib.auth import get_user_model
        self.fields['responsable'].queryset = responsables(comite_id, ciudadano) if ciudadano and self.fields['comite'].queryset.filter(pk=comite_id).exists() else get_user_model().objects.none()
        self.fields['responsable'].widget = autocomplete.ModelSelect2(url='secretaria:responsables', forward=['ciudadano', 'comite'], attrs={'data-width': '100%'})
        self.fields['responsable'].widget.choices = self.fields['responsable'].choices
        estilos(self)


class SeguimientoForm(forms.Form):
    version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    estado = forms.ChoiceField(choices=Solicitud.Estados.choices)
    responsable = forms.ModelChoiceField(queryset=None, required=False)
    fecha_compromiso = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    observaciones = forms.CharField(required=False, max_length=4000, widget=forms.Textarea(attrs={'rows': 3}))
    motivo_cierre = forms.CharField(required=False, max_length=2000, label='Motivo de resolución o cancelación', widget=forms.Textarea(attrs={'rows': 2}))
    confirmar_cierre = forms.BooleanField(required=False, label='Confirmo resolver o cancelar esta solicitud y conservar su historial sin más modificaciones.')
    archivo = forms.FileField(required=False, validators=[validar_adjunto], help_text='PDF, PNG o JPEG; máximo 5 MB.')

    def __init__(self, *args, usuario, solicitud, **kwargs):
        super().__init__(*args, **kwargs)
        if puede_asignar(usuario, solicitud):
            self.fields['responsable'].queryset = responsables(solicitud.comite_id, solicitud.ciudadano)
        else:
            self.fields.pop('responsable')
        estilos(self)

    def clean(self):
        datos = super().clean()
        if datos.get('estado') in ('RESUELTA', 'CANCELADA'):
            if not datos.get('motivo_cierre'):
                self.add_error('motivo_cierre', 'Indica el motivo para resolver o cancelar.')
            if not datos.get('confirmar_cierre'):
                self.add_error('confirmar_cierre', 'Confirma el cierre antes de guardar.')
        return datos
