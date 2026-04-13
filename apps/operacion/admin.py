from django.contrib import admin
from .models import Junta, AsistenciaJunta, Faena, RegistroFaena, Actividad, ActividadArchivo

@admin.register(Junta)
class JuntaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'comite', 'tipo', 'tema')
    list_filter = ('tipo', 'comite')
    search_fields = ('tema', 'comite__nombre')

@admin.register(AsistenciaJunta)
class AsistenciaJuntaAdmin(admin.ModelAdmin):
    list_display = ('junta', 'ciudadano', 'asistio')
    list_filter = ('asistio', 'junta__comite')
    search_fields = ('ciudadano__nombre', 'ciudadano__apellido_paterno')

@admin.register(Faena)
class FaenaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'comite', 'descripcion', 'estado')
    list_filter = ('estado', 'comite')
    search_fields = ('descripcion', 'comite__nombre')

@admin.register(RegistroFaena)
class RegistroFaenaAdmin(admin.ModelAdmin):
    list_display = ('faena', 'ciudadano', 'estatus', 'genera_adeudo', 'monto_adeudo')
    list_filter = ('estatus', 'genera_adeudo', 'faena__comite')
    search_fields = ('ciudadano__nombre', 'ciudadano__apellido_paterno', 'faena__descripcion')

class ActividadArchivoInline(admin.TabularInline):
    model = ActividadArchivo
    extra = 0

@admin.register(Actividad)
class ActividadAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'comite', 'titulo')
    list_filter = ('comite',)
    search_fields = ('titulo', 'descripcion')
    inlines = [ActividadArchivoInline]
