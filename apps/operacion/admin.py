from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.db import transaction
from django.forms.models import BaseInlineFormSet
from django.utils import timezone

from apps.tesoreria.models import Pago

from .models import (
    Actividad,
    ActividadArchivo,
    AsistenciaJunta,
    Faena,
    Junta,
    RegistroFaena,
)


class AsistenciaJuntaInline(admin.TabularInline):
    model = AsistenciaJunta
    extra = 0
    autocomplete_fields = ("ciudadano",)
    show_change_link = True
    fields = ("ciudadano", "asistio", "observaciones")


@admin.register(Junta)
class JuntaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "comite", "tipo", "tema")
    list_filter = ("tipo", "comite")
    search_fields = ("tema", "comite__nombre")
    autocomplete_fields = ("comite",)
    date_hierarchy = "fecha"
    inlines = [AsistenciaJuntaInline]


class RegistroFaenaInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            data = form.cleaned_data
            if not data or data.get("DELETE"):
                continue

            genera_adeudo = data.get("genera_adeudo")
            monto_adeudo = data.get("monto_adeudo")

            if genera_adeudo and (monto_adeudo is None or monto_adeudo <= 0):
                raise ValidationError(
                    "Si el registro genera adeudo, el monto de adeudo debe ser mayor a 0."
                )

            if not genera_adeudo and monto_adeudo and monto_adeudo > 0:
                raise ValidationError(
                    "No puedes capturar monto de adeudo si 'genera adeudo' está desactivado."
                )


class RegistroFaenaInline(admin.TabularInline):
    model = RegistroFaena
    formset = RegistroFaenaInlineFormSet
    extra = 0
    autocomplete_fields = ["ciudadano"]
    show_change_link = True
    fields = (
        "ciudadano",
        "estado",
        "genera_adeudo",
        "monto_adeudo",
        "observaciones",
    )


@admin.register(Faena)
class FaenaAdmin(admin.ModelAdmin):
    list_display = (
        "fecha",
        "comite",
        "descripcion",
        "estado",
        "total_registros",
        "total_asistencias",
        "total_adeudos",
        "monto_total_adeudos",
    )
    list_filter = ("estado", "comite", "fecha")
    list_editable = ("estado",)
    search_fields = (
        "descripcion",
        "notas",
        "comite__nombre",
        "registros__ciudadano__nombre",
        "registros__ciudadano__apellido_paterno",
        "registros__ciudadano__apellido_materno",
    )
    date_hierarchy = "fecha"
    autocomplete_fields = ("comite",)
    inlines = [RegistroFaenaInline]
    list_select_related = ("comite",)
    list_per_page = 50
    ordering = ("-fecha",)
    save_on_top = True
    readonly_fields = ("total_registros", "total_asistencias", "total_adeudos", "monto_total_adeudos")
    fieldsets = (
        ("Datos de la faena", {"fields": ("comite", "fecha", "descripcion", "estado")}),
        ("Notas y control", {"fields": ("notas",)}),
        ("Resumen operativo", {"fields": ("total_registros", "total_asistencias", "total_adeudos", "monto_total_adeudos")}),
    )
    actions = ("marcar_como_programada", "marcar_como_realizada", "marcar_como_cerrada", "marcar_como_cancelada", "generar_participantes", "generar_adeudos_por_faltas")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            _total_registros=Count("registros", distinct=True),
            _total_asistencias=Count(
                "registros",
                filter=Q(registros__estado=RegistroFaena.EstadosAsistencia.ASISTIO),
                distinct=True,
            ),
            _total_adeudos=Count(
                "registros",
                filter=Q(registros__genera_adeudo=True),
                distinct=True,
            ),
            _monto_total_adeudos=Sum(
                "registros__monto_adeudo",
                filter=Q(registros__genera_adeudo=True),
            ),
        )

    @admin.display(ordering="_total_registros", description="Registros")
    def total_registros(self, obj):
        return obj._total_registros

    @admin.display(ordering="_total_asistencias", description="Asistencias")
    def total_asistencias(self, obj):
        return obj._total_asistencias

    @admin.display(ordering="_total_adeudos", description="Adeudos")
    def total_adeudos(self, obj):
        return obj._total_adeudos

    @admin.display(ordering="_monto_total_adeudos", description="Monto total adeudos")
    def monto_total_adeudos(self, obj):
        return obj._monto_total_adeudos or 0

    @admin.action(description="Marcar faenas seleccionadas como Programadas")
    def marcar_como_programada(self, request, queryset):
        queryset.update(estado=Faena.Estados.PROGRAMADA)

    @admin.action(description="Marcar faenas seleccionadas como Realizadas")
    def marcar_como_realizada(self, request, queryset):
        queryset.update(estado=Faena.Estados.REALIZADA)

    @admin.action(description="Marcar faenas seleccionadas como Cerradas")
    def marcar_como_cerrada(self, request, queryset):
        queryset.update(estado=Faena.Estados.CERRADA)

    @admin.action(description="Marcar faenas seleccionadas como Canceladas")
    def marcar_como_cancelada(self, request, queryset):
        queryset.update(estado=Faena.Estados.CANCELADA)

    @admin.action(description="Generar participantes (ciudadanos activos)")
    def generar_participantes(self, request, queryset):
        from apps.core.models import Ciudadano

        ciudadanos_ids = list(Ciudadano.objects.filter(activo=True).values_list('id', flat=True))
        if not ciudadanos_ids:
            self.message_user(request, "No hay ciudadanos activos para generar participantes.", level=messages.WARNING)
            return

        total_creados = 0
        with transaction.atomic():
            for faena in queryset:
                existentes = set(
                    RegistroFaena.objects.filter(faena=faena).values_list('ciudadano_id', flat=True)
                )
                nuevos = [
                    RegistroFaena(faena=faena, ciudadano_id=ciudadano_id, estado=RegistroFaena.EstadosAsistencia.PENDIENTE)
                    for ciudadano_id in ciudadanos_ids
                    if ciudadano_id not in existentes
                ]
                RegistroFaena.objects.bulk_create(nuevos, ignore_conflicts=True)
                total_creados += len(nuevos)

        self.message_user(
            request,
            f"Generación completada. Se crearon {total_creados} registros nuevos."
        )

    @admin.action(description="Generar adeudos por faltas")
    def generar_adeudos_por_faltas(self, request, queryset):
        faenas = queryset.filter(estado__in=[Faena.Estados.REALIZADA, Faena.Estados.CERRADA])
        hoy = timezone.localdate()
        total = 0

        with transaction.atomic():
            for faena in faenas:
                faltas = RegistroFaena.objects.filter(
                    faena=faena,
                    estado=RegistroFaena.EstadosAsistencia.FALTO,
                ).select_related('ciudadano')

                nuevos = [
                    Pago(
                        ciudadano=registro.ciudadano,
                        comite=faena.comite,
                        tipo=Pago.Tipos.DEUDA_FAENA,
                        estado=Pago.Estados.PENDIENTE,
                        monto=registro.monto_adeudo,
                        fecha=hoy,
                        concepto=f'Adeudo por falta en faena {faena.fecha}',
                        anio_periodo=faena.fecha.year,
                        registro_faena=registro,
                    )
                    for registro in faltas
                    if registro.genera_adeudo and registro.monto_adeudo > 0
                ]
                Pago.objects.bulk_create(nuevos, ignore_conflicts=True)
                total += len(nuevos)

        self.message_user(request, f'Se procesaron {total} adeudos por faltas. Duplicados omitidos.')


@admin.register(RegistroFaena)
class RegistroFaenaAdmin(admin.ModelAdmin):
    list_display = ("faena", "ciudadano", "estado", "genera_adeudo", "monto_adeudo")
    list_filter = ("estado", "genera_adeudo", "faena__comite", "faena__fecha")
    search_fields = (
        "ciudadano__nombre",
        "ciudadano__apellido_paterno",
        "ciudadano__apellido_materno",
        "faena__descripcion",
    )
    autocomplete_fields = ("faena", "ciudadano")


class ActividadArchivoInline(admin.TabularInline):
    model = ActividadArchivo
    extra = 0


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ("fecha", "comite", "titulo")
    list_filter = ("comite",)
    search_fields = ("titulo", "descripcion")
    inlines = [ActividadArchivoInline]
