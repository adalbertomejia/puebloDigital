import django_tables2 as tables
from django.urls import reverse
from django.utils.html import format_html
from urllib.parse import urlencode
from .models import Ciudadano


class CiudadanoTable(tables.Table):
    ciudadano = tables.Column(accessor="nombre_completo", order_by=("apellido_paterno", "apellido_materno", "nombre", "pk"), verbose_name="Ciudadano")
    manzana = tables.Column(order_by="manzana.nombre", default="Sin asignar", verbose_name="Manzana")
    activo = tables.Column(verbose_name="Estado")
    toma = tables.Column(accessor="toma.numero_toma", default="Sin toma", verbose_name="Toma")
    acciones = tables.Column(empty_values=(), orderable=False, verbose_name="Acciones")

    class Meta:
        model = Ciudadano
        fields = ("ciudadano", "manzana", "activo", "toma", "acciones")
        sequence = fields
        order_by_field = "orden_tabla"
        template_name = "dashboard/components/tabla.html"
        attrs = {"class": "pd-table pd-table--compact"}
        empty_text = "No se encontraron ciudadanos con los filtros seleccionados."

    def __init__(self, *args, retorno="", puede_editar=False, **kwargs):
        self.retorno = urlencode({"return_to": retorno})
        self.puede_editar = puede_editar
        super().__init__(*args, **kwargs)

    def render_ciudadano(self, value, record):
        return format_html('<a href="{}?{}">{}</a><span class="pd-table__secondary">Contrato: {} · ID {}</span>', reverse("perfil_ciudadano", args=[record.pk]), self.retorno, value, record.numero_contrato or "Sin registro", record.pk)

    def render_activo(self, value):
        return format_html('<span class="pd-tag {}">{}</span>', "pd-tag--active" if value else "pd-tag--inactive", "Activo" if value else "Inactivo")

    def render_acciones(self, record):
        ver = format_html('<a class="pd-button pd-button--primary" href="{}?{}">Ver expediente</a>', reverse("perfil_ciudadano", args=[record.pk]), self.retorno)
        if not self.puede_editar: return ver
        return format_html('{} <a class="pd-button pd-button--secondary" href="{}?{}">Editar</a>', ver, reverse("editar_ciudadano_operativo", args=[record.pk]), self.retorno)
