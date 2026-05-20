from django.contrib import admin

from apps.agua.models import Toma
from apps.operacion.models import RegistroFaena
from apps.tesoreria.models import Cooperacion, Pago

from .models import Ciudadano


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
    fields = ("faena", "estado", "genera_adeudo", "monto_adeudo", "observaciones")
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
        "edad",
        "telefono",
        "activo",
        "numero_toma",
        "estado_toma",
        "created_at",
    )
    search_fields = (
        "^apellido_paterno",
        "^apellido_materno",
        "^nombre",
        "telefono",
        "direccion",
    )
    list_filter = ("activo", "edad", "created_at", "registros_faena__estado", "toma__estado")
    ordering = ("apellido_paterno", "apellido_materno", "nombre")
    list_per_page = 50
    save_on_top = True
    list_select_related = ("toma",)
    inlines = [TomaInline, PagoInline, CooperacionInline, RegistroFaenaInline]
    fieldsets = (
        ("Identidad", {"fields": (("nombre", "apellido_paterno", "apellido_materno"), "activo")}),
        ("Datos de contacto", {"fields": ("edad", "fecha_nacimiento", "telefono", "direccion")}),
        ("Notas internas", {"fields": ("observaciones",), "classes": ("collapse",)}),
    )

    @admin.display(description="Toma", ordering="toma__numero_toma")
    def numero_toma(self, obj):
        return getattr(obj.toma, "numero_toma", "Sin toma")

    @admin.display(description="Estado agua", ordering="toma__estado")
    def estado_toma(self, obj):
        return getattr(obj.toma, "get_estado_display", lambda: "-")()

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.select_related("toma")
