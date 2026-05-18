from django.contrib import admin
from django.db.models import Count, Q

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


class RegistroFaenaInline(admin.TabularInline):
    model = RegistroFaena
    extra = 0
    autocomplete_fields = ["ciudadano"]
    show_change_link = True
    fields = (
        "ciudadano",
        "asistio",
        "estatus",
        "genera_adeudo",
        "monto_adeudo",
        "observaciones",
    )
    readonly_fields = ("asistio",)

    @admin.display(boolean=True, description="Asistió")
    def asistio(self, obj):
        return obj.estatus == RegistroFaena.Estatus.ASISTIO


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
    )
    list_filter = ("estado", "comite", "fecha")
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
    save_on_top = True
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


class ActividadArchivoInline(admin.TabularInline):
    model = ActividadArchivo
    extra = 0


@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ("fecha", "comite", "titulo")
    list_filter = ("comite",)
    search_fields = ("titulo", "descripcion")
    inlines = [ActividadArchivoInline]
