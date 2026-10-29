from datetime import date
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.tesoreria.models import Abono, ConceptoTesoreria, ObligacionCiudadano, RegistroFinanciero


class MigracionTrazabilidadTests(TransactionTestCase):
    def test_conserva_importes_y_registros_previos_sin_inventar_autores(self):
        executor = MigrationExecutor(connection)
        destinos = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([("tesoreria", "0001_initial")])
            anteriores = executor.loader.project_state([("tesoreria", "0001_initial")]).apps
            comite = anteriores.get_model("comites", "Comite").objects.create(nombre="Comité anterior")
            ciudadano = anteriores.get_model("core", "Ciudadano").objects.create(nombre="Ana", apellido_paterno="Anterior")
            concepto = anteriores.get_model("tesoreria", "ConceptoTesoreria").objects.create(comite_id=comite.pk, concepto="Cuota anterior", naturaleza="PAGO", monto_individual=100, fecha=date(2026, 10, 1))
            obligacion = anteriores.get_model("tesoreria", "ObligacionCiudadano").objects.create(concepto_id=concepto.pk, ciudadano_id=ciudadano.pk, monto_asignado=100)
            abono = anteriores.get_model("tesoreria", "Abono").objects.create(obligacion_id=obligacion.pk, monto=17, fecha=date(2026, 10, 2), notas="Registro conservado")
        finally:
            MigrationExecutor(connection).migrate(destinos)
        self.assertEqual(ConceptoTesoreria.objects.get(pk=concepto.pk).concepto, "Cuota anterior")
        self.assertIsNone(ConceptoTesoreria.objects.get(pk=concepto.pk).creado_por_id)
        self.assertIsNone(ObligacionCiudadano.objects.get(pk=obligacion.pk).creado_por_id)
        actual = Abono.objects.get(pk=abono.pk)
        self.assertEqual(actual.monto, Decimal("17.00"))
        self.assertEqual(actual.notas, "Registro conservado")
        self.assertEqual(actual.referencia, "")
        self.assertIsNone(actual.creado_por_id)
        self.assertEqual(ObligacionCiudadano.objects.get(pk=obligacion.pk).saldo_pendiente, Decimal("83.00"))
        self.assertFalse(RegistroFinanciero.objects.exists())
