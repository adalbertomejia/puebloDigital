from django.contrib import admin
from django.db import transaction
from apps.core.admin_seguridad import AdministracionGlobal
from apps.operacion.alcance import manzanas_disponibles_para_instancia

from .models import Abono, ConceptoTesoreria, Cooperacion, ObligacionCiudadano, Pago, RegistroFinanciero
from .auditoria import registrar_movimiento


class AutorFinancieroAdmin:
    readonly_fields = ("creado_por", "created_at", "updated_at")

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if not change:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)
        registrar_movimiento(request.user, obj,
            RegistroFinanciero.Acciones.EDITAR if change else RegistroFinanciero.Acciones.CREAR,
            detalle={"campos": form.changed_data}, origen="ADMIN")

    @transaction.atomic
    def delete_model(self, request, obj):
        registrar_movimiento(request.user, obj, RegistroFinanciero.Acciones.ELIMINAR, origen="ADMIN")
        super().delete_model(request, obj)

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        for objeto in queryset:
            self.delete_model(request, objeto)

    @transaction.atomic
    def save_formset(self, request, form, formset, change):
        objetos = formset.save(commit=False)
        for objeto in formset.deleted_objects:
            registrar_movimiento(request.user, objeto, RegistroFinanciero.Acciones.ELIMINAR, origen="ADMIN")
            objeto.delete()
        for objeto in objetos:
            nuevo = objeto.pk is None
            if nuevo:
                objeto.creado_por = request.user
            objeto.save()
            registrar_movimiento(request.user, objeto,
                RegistroFinanciero.Acciones.CREAR if nuevo else RegistroFinanciero.Acciones.EDITAR, origen="ADMIN")
        formset.save_m2m()


class AbonoInline(AdministracionGlobal, admin.TabularInline):
    model = Abono
    extra = 0
    readonly_fields = ("creado_por", "created_at", "updated_at")


@admin.register(ConceptoTesoreria)
class ConceptoTesoreriaAdmin(AutorFinancieroAdmin, AdministracionGlobal, admin.ModelAdmin):
    list_display = ("fecha", "naturaleza", "alcance", "manzana", "concepto", "comite", "monto_individual", "registros_generados")
    list_filter = ("naturaleza", "alcance", "manzana", "origen", "comite", "fecha", "registros_generados")
    search_fields = ("concepto", "descripcion", "comite__nombre")
    autocomplete_fields = ("comite", "manzana")
    list_select_related = ("manzana", "comite")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["manzana"].queryset = manzanas_disponibles_para_instancia(
            obj or ConceptoTesoreria()
        )
        return form


@admin.register(ObligacionCiudadano)
class ObligacionCiudadanoAdmin(AutorFinancieroAdmin, AdministracionGlobal, admin.ModelAdmin):
    list_display = ("ciudadano", "concepto", "monto_asignado", "estado")
    list_filter = ("estado", "concepto__naturaleza", "concepto__comite")
    search_fields = ("ciudadano__nombre", "ciudadano__apellido_paterno", "ciudadano__apellido_materno", "concepto__concepto")
    autocomplete_fields = ("concepto", "ciudadano", "toma")
    inlines = [AbonoInline]


@admin.register(Abono)
class AbonoAdmin(AutorFinancieroAdmin, AdministracionGlobal, admin.ModelAdmin):
    list_display = ("fecha", "obligacion", "monto")
    list_filter = ("fecha",)
    search_fields = ("obligacion__ciudadano__nombre", "obligacion__ciudadano__apellido_paterno", "obligacion__concepto__concepto")
    autocomplete_fields = ("obligacion",)


@admin.register(Pago)
class PagoAdmin(AdministracionGlobal, admin.ModelAdmin):
    list_display = ('fecha', 'ciudadano', 'comite', 'tipo', 'monto', 'anio_periodo')
    list_filter = ('tipo', 'comite', 'fecha')
    search_fields = ('ciudadano__nombre', 'ciudadano__apellido_paterno', 'concepto', 'comprobante')
    autocomplete_fields = ('ciudadano', 'comite', 'registro_faena', 'toma')


@admin.register(Cooperacion)
class CooperacionAdmin(AdministracionGlobal, admin.ModelAdmin):
    list_display = ('fecha', 'ciudadano', 'comite', 'tipo', 'monto', 'anio_periodo')
    list_filter = ('tipo', 'comite', 'fecha')
    search_fields = ('ciudadano__nombre', 'ciudadano__apellido_paterno', 'concepto', 'comprobante')
    autocomplete_fields = ('ciudadano', 'comite')


@admin.register(RegistroFinanciero)
class RegistroFinancieroAdmin(AdministracionGlobal, admin.ModelAdmin):
    list_display = ("fecha_registro", "usuario_nombre", "accion", "comite", "concepto_nombre", "monto", "referencia")
    list_filter = ("comite", "accion", "origen")
    search_fields = ("usuario_nombre", "concepto_nombre", "referencia")
    list_select_related = ("usuario", "comite")
    readonly_fields = tuple(campo.name for campo in RegistroFinanciero._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
