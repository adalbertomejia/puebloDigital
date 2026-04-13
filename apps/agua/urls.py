from django.urls import path

from apps.agua.views import toma_list_view

app_name = 'agua'

urlpatterns = [
    path('tomas/', toma_list_view, name='toma_list'),
]
