from django.urls import path
from . import balance_views as v

urlpatterns = [
    path("balance/",v.balance_recaudacion,name="balance_recaudacion"),
    path("balance/conceptos/",v.balance_conceptos,name="balance_conceptos"),
    path("balance/conceptos/<int:pk>/",v.balance_concepto_detalle,name="balance_concepto_detalle"),
    path("balance/transparencia/",v.balance_transparencia,name="balance_transparencia"),
    path("recursos/",v.fondos_recursos,name="fondos_recursos"),
    path("recursos/nuevo/",v.fondo_crear,name="fondo_recurso_crear"),
    path("recursos/<int:pk>/",v.fondo_detalle,name="fondo_recurso_detalle"),
    path("recursos/<int:pk>/salida/",v.fondo_salida,name="fondo_recurso_salida"),
    path("recursos/movimientos/<uuid:pk>/comprobante/",v.comprobante_recurso,name="comprobante_recurso"),
    path("recursos/<int:pk>/corte/",v.preparar_corte,name="preparar_corte_recurso"),
    path("cortes/",v.cortes_recursos,name="cortes_recursos"),
    path("cortes/<uuid:pk>/",v.corte_detalle,name="corte_recurso_detalle"),
    path("cortes/<uuid:pk>/revisar/",v.corte_revisar,name="corte_recurso_revisar"),
]
