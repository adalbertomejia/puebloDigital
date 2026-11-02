import django_tables2 as tables
from django.utils.html import format_html
from .models import RegistroFinanciero


class ActividadFinancieraTable(tables.Table):
    fecha_registro = tables.DateTimeColumn(format="d/m/Y H:i:s", verbose_name="Fecha de registro")
    usuario_nombre = tables.Column(verbose_name="Usuario")
    accion = tables.Column(verbose_name="Operación")
    comite = tables.Column(accessor="comite.nombre", verbose_name="Comité")
    concepto_nombre = tables.Column(verbose_name="Concepto")
    registro = tables.Column(empty_values=(), verbose_name="Registro", orderable=False)
    monto = tables.Column(verbose_name="Importe", default="—")
    referencia = tables.Column(verbose_name="Referencia", default="Sin referencia")

    class Meta:
        model = RegistroFinanciero
        fields = ("fecha_registro", "usuario_nombre", "accion", "comite", "concepto_nombre", "registro", "monto", "referencia")
        sequence = fields
        template_name = "dashboard/components/tabla.html"
        attrs = {"class": "pd-table pd-table--compact"}
        empty_text = "No hay operaciones registradas para este ámbito."
        order_by_field = "orden_tabla"
        page_field = "pagina"

    def render_accion(self, record):
        texto = record.get_accion_display()
        if record.detalle.get("creados"):
            return format_html('{}<span class="block text-xs">{} obligaciones nuevas</span>', texto, record.detalle["creados"])
        if "total_abonado" in record.detalle:
            return format_html('{}<span class="block text-xs">Total abonado al eliminar: ${}</span>', texto, record.detalle["total_abonado"])
        return texto

    def render_registro(self, record):
        tipo = {"abono": "Abono", "obligacionciudadano": "Obligación"}.get(record.tipo_objeto, "Concepto")
        return f"{tipo} #{record.objeto_id}"

    def render_monto(self, value):
        return format_html('${}', f'{value:,.2f}')
