from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from apps.core.views import dashboard_operativo, generar_registros_faena, home, perfil_ciudadano

urlpatterns = [
    path('', home, name='home'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('dashboard/', dashboard_operativo, name='dashboard_operativo'),
    path('dashboard/ciudadano/<int:pk>/', perfil_ciudadano, name='perfil_ciudadano'),
    path('dashboard/faena/<int:faena_id>/generar-registros/', generar_registros_faena, name='generar_registros_faena'),
    path('admin/', admin.site.urls),
]
