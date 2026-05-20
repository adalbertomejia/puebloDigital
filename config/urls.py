from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from apps.core.views import (
    accion_masiva_faena,
    actualizar_estado_faena,
    cerrar_faena,
    dashboard_operativo,
    faena_operativa,
    home,
    perfil_ciudadano,
)

urlpatterns = [
    path('', home, name='home'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', dashboard_operativo, name='dashboard_operativo'),
    path('dashboard/ciudadano/<int:pk>/', perfil_ciudadano, name='perfil_ciudadano'),
    path('dashboard/faenas/<int:pk>/', faena_operativa, name='faena_operativa'),
    path('dashboard/faenas/<int:pk>/accion-masiva/', accion_masiva_faena, name='accion_masiva_faena'),
    path('dashboard/faena-registro/<int:pk>/estado/', actualizar_estado_faena, name='actualizar_estado_faena'),
    path('dashboard/faenas/<int:pk>/cerrar/', cerrar_faena, name='cerrar_faena'),
    path('admin/', admin.site.urls),
]
