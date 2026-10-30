from django.urls import path
from . import views
app_name = 'secretaria'
urlpatterns = [
    path('', views.bandeja, name='bandeja'),
    path('nueva/', views.nueva, name='nueva'),
    path('ciudadanos/', views.CiudadanosAutocomplete.as_view(), name='ciudadanos'),
    path('responsables/', views.ResponsablesAutocomplete.as_view(), name='responsables'),
    path('<int:pk>/', views.detalle, name='detalle'),
    path('<int:pk>/constancia/', views.constancia, name='constancia'),
    path('<int:pk>/adjuntos/<int:adjunto_id>/', views.descargar, name='descargar'),
]
