from django.contrib import admin
from django.db.models import Count

from apps.agua.models import Toma
from apps.operacion.models import RegistroFaena
from apps.tesoreria.models import Cooperacion, Pago

from .models import Ciudadano, Manzana


@admin.register(Manzana)
class ManzanaAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "clave",
        "responsable",
        "activa",
        "cantidad_ciudadanos",
        "updated_at",
    )
    search_fields = (
        "nombre",
        "clave",
        "responsable__nombre",
        "responsable__apellido_paterno",
        "responsable__apellido_materno",
    )
    list_filter = ("activa",)
    autocomplete_fields = ("responsable",)
    list_select_related = ("responsable",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("responsable")
            .annotate(_cantidad_ciudadanos=Count("ciudadanos"))
        )

    @admin.display(description="Cantidad de ciudadanos", ordering="_cantidad_ciudadanos")
    def cantidad_ciudadanos(self, obj):
        return obj._cantidad_ciudadanos


class PagoInline(admin.TabularInline):
    model = Pago
    extra = 0
    fields = (
        "fecha",
        "tipo",
        "monto",
        "comite",
        "concepto",
        "anio_periodo",
        "comprobante",
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    ordering = ("-fecha", "-created_at")
    autocomplete_fields = ("comite",)
    verbose_name = "Pago"
    verbose_name_plural = "Pagos (historial)"

    def has_add_permission(self, request, obj=None):
        return False


class CooperacionInline(admin.TabularInline):
    model = Cooperacion
    extra = 0
    fields = ("fecha", "tipo", "monto", "comite", "concepto", "anio_periodo", "comprobante")
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    ordering = ("-fecha", "-created_at")
    autocomplete_fields = ("comite",)
    verbose_name = "Cooperación"
    verbose_name_plural = "Cooperaciones (historial)"

    def has_add_permission(self, request, obj=None):
        return False


class RegistroFaenaInline(admin.TabularInline):
    model = RegistroFaena
    extra = 0
    fields = ("faena", "estatus", "genera_adeudo", "monto_adeudo", "observaciones")
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    ordering = ("-faena__fecha", "-created_at")
    autocomplete_fields = ("faena",)
    verbose_name = "Registro de faena"
    verbose_name_plural = "Faenas (asistencias e historial)"

    def has_add_permission(self, request, obj=None):
        return False


class TomaInline(admin.StackedInline):
    model = Toma
    extra = 0
    max_num = 1
    fields = ("numero_toma", "estado", "ubicacion", "costo_anual", "observaciones")
    show_change_link = True
    verbose_name = "Toma de agua"
    verbose_name_plural = "Agua"


@admin.register(Ciudadano)
class CiudadanoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre_completo",
        "edad_actual",
        "sexo",
        "numero_contrato",
        "manzana",
        "motivo_alta_legible",
        "activo",
        "numero_toma",
        "estado_toma",
        "created_at",
    )
    search_fields = (
        "^apellido_paterno",
        "^apellido_materno",
        "^nombre",
        "numero_contrato",
        "manzana__nombre",
        "direccion",
    )
    list_filter = ("activo", "sexo", "motivo_alta", "manzana", "edad", "created_at", "registros_faena__estatus", "toma__estado")
    ordering = ("apellido_paterno", "apellido_materno", "nombre")
    list_per_page = 50
    save_on_top = True
    list_select_related = ("toma", "manzana")
    autocomplete_fields = ("manzana",)
    inlines = [TomaInline, PagoInline, CooperacionInline, RegistroFaenaInline]
    fieldsets = (
        ("Identidad", {"fields": (("nombre", "apellido_paterno", "apellido_materno"), "activo")}),
        ("Datos del padrón", {"fields": ("fecha_nacimiento", "edad", "sexo", "numero_contrato", "manzana", "direccion")}),
        ("Participación y alta", {"fields": ("labor_social", "motivo_alta")}),
        ("Notas internas", {"fields": ("observaciones",), "classes": ("collapse",)}),
    )

    @admin.display(description="Motivo de alta", ordering="motivo_alta")
    def motivo_alta_legible(self, obj):
        return obj.get_motivo_alta_display()

    @admin.display(description="Toma", ordering="toma__numero_toma")
    def numero_toma(self, obj):
        return getattr(obj.toma, "numero_toma", "Sin toma")

    @admin.display(description="Estado agua", ordering="toma__estado")
    def estado_toma(self, obj):
        return getattr(obj.toma, "get_estado_display", lambda: "-")()

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related("toma", "manzana")
