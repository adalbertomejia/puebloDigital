from django.contrib import admin

from apps.comites.admin_security import CommitteeAccessMixin

from .models import Junta, AsistenciaJunta, Faena, RegistroFaena, Actividad, ActividadArchivo


@admin.register(Junta)
class JuntaAdmin(CommitteeAccessMixin, admin.ModelAdmin):
    committee_lookup = "comite"
    committee_fk_fields = ("comite",)
    list_display = ("fecha", "comite", "tipo", "tema")
    list_filter = ("tipo", "comite")
    search_fields = ("tema", "comite__nombre")


@admin.register(AsistenciaJunta)
class AsistenciaJuntaAdmin(CommitteeAccessMixin, admin.ModelAdmin):
    committee_lookup = "junta__comite"
    foreign_key_committee_filters = {
        "junta": "comite",
    }
    list_display = ("junta", "ciudadano", "asistio")
    list_filter = ("asistio", "junta__comite")
    search_fields = ("ciudadano__nombre", "ciudadano__apellido_paterno")


@admin.register(Faena)
class FaenaAdmin(CommitteeAccessMixin, admin.ModelAdmin):
    committee_lookup = "comite"
    committee_fk_fields = ("comite",)
    list_display = ("fecha", "comite", "descripcion", "estado")
    list_filter = ("estado", "comite")
    search_fields = ("descripcion", "comite__nombre")


@admin.register(RegistroFaena)
class RegistroFaenaAdmin(CommitteeAccessMixin, admin.ModelAdmin):
    committee_lookup = "faena__comite"
    foreign_key_committee_filters = {
        "faena": "comite",
    }
    list_display = ("faena", "ciudadano", "estatus", "genera_adeudo", "monto_adeudo")
    list_filter = ("estatus", "genera_adeudo", "faena__comite")
    search_fields = ("ciudadano__nombre", "ciudadano__apellido_paterno", "faena__descripcion")


class ActividadArchivoInline(admin.TabularInline):
    model = ActividadArchivo
    extra = 0


@admin.register(Actividad)
class ActividadAdmin(CommitteeAccessMixin, admin.ModelAdmin):
    committee_lookup = "comite"
    committee_fk_fields = ("comite",)
    list_display = ("fecha", "comite", "titulo")
    list_filter = ("comite",)
    search_fields = ("titulo", "descripcion")
    inlines = [ActividadArchivoInline]
