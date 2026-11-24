"""Real row-lock behavior; SQLite cannot validate these races."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, connections, close_old_connections
from django.test import TransactionTestCase
from django.utils import timezone
from apps.comites.models import Comite
from apps.comites.test_helpers import asignar_cargo
from apps.core.models import Ciudadano
from .models import FondoRecurso, MovimientoRecurso, CorteRecurso, ConceptoTesoreria, ObligacionCiudadano, Abono
from . import recursos


@skipUnless(connection.vendor=="postgresql", "Los bloqueos financieros se verifican con PostgreSQL.")
class RecursosConcurrenciaTests(TransactionTestCase):
    def setUp(self):
        self.hoy=timezone.localdate()
        self.comite=Comite.objects.create(nombre="Delegación concurrente")
        self.user=get_user_model().objects.create_user("cajero-concurrente")
        asignar_cargo(user=self.user,comite=self.comite,rol="TESORERO")
        self.fondo=recursos.abrir_fondo(usuario=self.user,nombre="Custodia concurrente",categoria="OPERACION",comite=self.comite,manzana=None,fecha_apertura=self.hoy,inicial_efectivo=500,inicial_transferencia=0,evidencia_apertura="Acta sintética")
        c=Ciudadano.objects.create(nombre="Ana",apellido_paterno="Concurrente")
        concepto=ConceptoTesoreria.objects.create(comite=self.comite,concepto="Cuota concurrente",naturaleza="PAGO",monto_individual=100,fecha=self.hoy)
        self.o=ObligacionCiudadano.objects.create(concepto=concepto,ciudadano=c,monto_asignado=100)

    def paralelo(self,accion):
        barrera=Barrier(2)
        def trabajo():
            close_old_connections()
            try:
                u=get_user_model().objects.get(pk=self.user.pk)
                f=FondoRecurso.objects.get(pk=self.fondo.pk)
                barrera.wait(timeout=15)
                try:
                    accion(u,f)
                    return "registrado"
                except ValidationError:
                    return "rechazado"
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados=list(pool.map(lambda _:trabajo(),range(2)))
        self.assertCountEqual(resultados,["registrado","rechazado"])

    def test_dos_salidas_no_pueden_gastar_el_mismo_saldo(self):
        def accion(u,f):
            recursos.registrar_salida(usuario=u,fondo=f,monto=400,medio="EFECTIVO",fecha=self.hoy,categoria_salida="MANTENIMIENTO",descripcion="Trabajo sintético",beneficiario="",evidencia="Acta",clave_operacion=uuid.uuid4())
        self.paralelo(accion)
        self.assertEqual(MovimientoRecurso.objects.count(),1)
        self.assertEqual(recursos.resumen_fondo(self.fondo)["efectivo"],100)

    def test_dos_cobros_no_superan_el_saldo_de_la_obligacion(self):
        def accion(u,f):
            o=ObligacionCiudadano.objects.get(pk=self.o.pk)
            o.acreditar(60,usuario=u,fondo=f,medio="EFECTIVO",clave_operacion=uuid.uuid4())
        self.paralelo(accion)
        self.assertEqual(Abono.objects.count(),1)
        self.assertEqual(recursos.resumen_fondo(self.fondo)["efectivo"],560)

    def test_dos_envios_no_abren_dos_cortes_del_mismo_fondo(self):
        version=recursos.version_corte(self.fondo)
        def accion(u,f):
            recursos.enviar_corte(usuario=u,fondo=f,contado=500,aclaracion="",evidencia_conteo="Acta",clave_operacion=uuid.uuid4(),version=version)
        self.paralelo(accion)
        self.assertEqual(CorteRecurso.objects.count(),1)
