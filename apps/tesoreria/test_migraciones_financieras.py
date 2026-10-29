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


class MigracionVinculosAsistenciaTests(TransactionTestCase):
    def test_sqlite_conserva_monto_null_historico_y_restricciones(self):
        if connection.vendor != 'sqlite':
            self.skipTest('Reproduce una base histórica de SQLite.')
        from django.db import IntegrityError, transaction

        executor = MigrationExecutor(connection)
        destinos = executor.loader.graph.leaf_nodes()
        anterior = [('tesoreria', '0003_cuotas_mensuales_agua'), ('operacion', '0002_evento_motivo_comite_opcional')]
        legacy_pk = None
        modelo = None
        campo_original = None
        nullable = None
        try:
            executor.migrate(anterior)
            apps = executor.loader.project_state(anterior).apps
            modelo = apps.get_model('tesoreria', 'ConceptoTesoreria')
            campo_original = modelo._meta.get_field('monto_individual')
            nullable = campo_original.clone()
            nullable.null = True
            nullable.set_attributes_from_name('monto_individual')
            nullable.model = modelo
            with connection.schema_editor() as editor:
                editor.alter_field(modelo, campo_original, nullable)
            comite = apps.get_model('comites', 'Comite').objects.create(nombre='Comité histórico NULL')
            ciudadano = apps.get_model('core', 'Ciudadano').objects.create(nombre='Ana', apellido_paterno='Histórica')
            vacio = modelo.objects.create(comite_id=comite.pk, concepto='Importe histórico por revisar', naturaleza='PAGO', monto_individual=None, fecha=date(2026, 10, 1))
            legacy_pk = vacio.pk
            valido = modelo.objects.create(comite_id=comite.pk, concepto='Cuota válida', naturaleza='PAGO', monto_individual=100, fecha=date(2026, 10, 1))
            obligacion = apps.get_model('tesoreria', 'ObligacionCiudadano').objects.create(concepto_id=valido.pk, ciudadano_id=ciudadano.pk, monto_asignado=100)
            abono = apps.get_model('tesoreria', 'Abono').objects.create(obligacion_id=obligacion.pk, monto=17, fecha=date(2026, 10, 1))
            evento = apps.get_model('operacion', 'Faena').objects.create(comite_id=comite.pk, descripcion='Histórica', fecha=date(2026, 10, 1))

            MigrationExecutor(connection).migrate(destinos)
            self.assertIsNone(ConceptoTesoreria.objects.get(pk=legacy_pk).monto_individual)
            self.assertIsNone(ConceptoTesoreria.objects.get(pk=legacy_pk).faena_id)
            self.assertEqual(Abono.objects.get(pk=abono.pk).monto, Decimal('17.00'))
            self.assertEqual(ObligacionCiudadano.objects.get(pk=obligacion.pk).saldo_pendiente, Decimal('83.00'))
            ConceptoTesoreria.objects.filter(pk=valido.pk).update(faena_id=evento.pk)
            with self.assertRaises(IntegrityError), transaction.atomic():
                ConceptoTesoreria.objects.filter(pk=legacy_pk).update(faena_id=evento.pk)
            with self.assertRaises(IntegrityError), transaction.atomic():
                ConceptoTesoreria.objects.filter(pk=legacy_pk).update(junta_id=999999)
                connection.check_constraints()
            # Rollback also preserves the NULL without rebuilding the table.
            MigrationExecutor(connection).migrate(anterior)
            self.assertIsNone(modelo.objects.get(pk=legacy_pk).monto_individual)
        finally:
            # Restore this synthetic database's original schema for other tests.
            if modelo is not None and nullable is not None:
                if legacy_pk is not None:
                    modelo.objects.filter(pk=legacy_pk, monto_individual__isnull=True).update(monto_individual=100)
                with connection.schema_editor() as editor:
                    editor.alter_field(modelo, nullable, campo_original)
            MigrationExecutor(connection).migrate(destinos)
