from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from apps.core.views import (
    control_asistencias,
    control_asistencias_faena_detalle,
    control_asistencias_junta_detalle,
    captura_asistencia_faena,
    captura_asistencia_junta,
    crear_faena_operativa,
    crear_junta_operativa,
    dashboard_operativo,
    generar_registros_faena,
    generar_registros_junta,
    home,
    perfil_ciudadano,
)

urlpatterns = [
    path('', home, name='home'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', dashboard_operativo, name='dashboard_operativo'),
    path('dashboard/ciudadano/<int:pk>/', perfil_ciudadano, name='perfil_ciudadano'),
    path('control-asistencias/', control_asistencias, name='control_asistencias'),
    path('operacion/faenas/nueva/', crear_faena_operativa, name='crear_faena_operativa'),
    path('operacion/juntas/nueva/', crear_junta_operativa, name='crear_junta_operativa'),
    path('control-asistencias/faena/<int:faena_id>/', control_asistencias_faena_detalle, name='control_asistencias_faena_detalle'),
    path('control-asistencias/junta/<int:junta_id>/', control_asistencias_junta_detalle, name='control_asistencias_junta_detalle'),
    path('control-asistencias/faena/<int:faena_id>/captura/', captura_asistencia_faena, name='captura_asistencia_faena'),
    path('control-asistencias/junta/<int:junta_id>/captura/', captura_asistencia_junta, name='captura_asistencia_junta'),
    path('dashboard/faena/<int:faena_id>/generar-registros/', generar_registros_faena, name='generar_registros_faena'),
    path('dashboard/junta/<int:junta_id>/generar-registros/', generar_registros_junta, name='generar_registros_junta'),
    path('admin/', admin.site.urls),
]
