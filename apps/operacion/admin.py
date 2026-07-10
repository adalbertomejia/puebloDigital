from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.forms.models import BaseInlineFormSet

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
    fields = ("ciudadano", "estatus", "genera_adeudo", "monto_adeudo", "asistio", "observaciones")


@admin.register(Junta)
class JuntaAdmin(admin.ModelAdmin):
    list_display = ("fecha", "comite", "tipo", "tema", "estado", "total_registros", "total_asistencias", "total_adeudos", "monto_total_adeudos")
    list_filter = ("estado", "tipo", "comite")
    search_fields = ("tema", "comite__nombre")
    autocomplete_fields = ("comite",)
    list_editable = ("estado",)
    date_hierarchy = "fecha"
    inlines = [AsistenciaJuntaInline]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            _total_registros=Count("asistencias", distinct=True),
            _total_asistencias=Count(
                "asistencias",
                filter=Q(asistencias__estatus=AsistenciaJunta.Estatus.ASISTIO),
                distinct=True,
            ),
            _total_adeudos=Count("asistencias", filter=Q(asistencias__genera_adeudo=True), distinct=True),
            _monto_total_adeudos=Sum("asistencias__monto_adeudo", filter=Q(asistencias__genera_adeudo=True)),
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

    @admin.display(ordering="_monto_total_adeudos", description="Monto adeudos")
    def monto_total_adeudos(self, obj):
        return obj._monto_total_adeudos or 0


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
        "estatus",
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
    actions = ("marcar_como_programada", "marcar_como_realizada", "marcar_como_cancelada")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(
            _total_registros=Count("registros", distinct=True),
            _total_asistencias=Count(
                "registros",
                filter=Q(registros__estatus=RegistroFaena.Estatus.ASISTIO),
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

    @admin.display(ordering="_monto_total_adeudos", description="Monto adeudos")
    def monto_total_adeudos(self, obj):
        return obj._monto_total_adeudos or 0

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

    @admin.action(description="Marcar faenas seleccionadas como Canceladas")
    def marcar_como_cancelada(self, request, queryset):
        queryset.update(estado=Faena.Estados.CANCELADA)


@admin.register(RegistroFaena)
class RegistroFaenaAdmin(admin.ModelAdmin):
    list_display = ("faena", "ciudadano", "estatus", "genera_adeudo", "monto_adeudo")
    list_filter = ("estatus", "genera_adeudo", "faena__comite", "faena__fecha")
    search_fields = (
        "ciudadano__nombre",
        "ciudadano__apellido_paterno",
        "ciudadano__apellido_materno",
        "faena__descripcion",
    )
    autocomplete_fields = ("faena", "ciudadano")


@admin.register(AsistenciaJunta)
class AsistenciaJuntaAdmin(admin.ModelAdmin):
    list_display = ("junta", "ciudadano", "estatus", "asistio")
    list_filter = ("estatus", "asistio", "junta__comite", "junta__fecha")
    search_fields = (
        "ciudadano__nombre",
        "ciudadano__apellido_paterno",
        "ciudadano__apellido_materno",
        "junta__tema",
    )
    autocomplete_fields = ("junta", "ciudadano")


class ActividadArchivoInline(admin.TabularInline):
    model = ActividadArchivo
    extra = 0


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ("fecha", "comite", "titulo")
    list_filter = ("comite",)
    search_fields = ("titulo", "descripcion")
    inlines = [ActividadArchivoInline]
