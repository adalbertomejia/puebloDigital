from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase, TransactionTestCase

from apps.core.admin import ManzanaAdmin
from apps.core.models import Ciudadano, Manzana


def crear_ciudadano(nombre="Ana", **kwargs):
    return Ciudadano.objects.create(
        nombre=nombre,
        apellido_paterno=kwargs.pop("apellido_paterno", "López"),
        edad=kwargs.pop("edad", 30),
        **kwargs,
    )


class ManzanaModelTests(TestCase):
    def test_se_puede_crear_solo_con_nombre_y_sin_clave(self):
        manzana = Manzana.objects.create(nombre="Centro")

        self.assertIsNone(manzana.clave)
        self.assertIsNone(manzana.responsable)
        self.assertTrue(manzana.activa)
        self.assertEqual(str(manzana), "Centro")

    def test_nombre_y_clave_no_se_pueden_repetir(self):
        Manzana.objects.create(nombre="Centro", clave="M-01")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Manzana.objects.create(nombre="Centro")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Manzana.objects.create(nombre="Norte", clave="M-01")

    def test_clave_acepta_solo_letras_numeros_y_guiones(self):
        manzana = Manzana(nombre="Centro", clave="clave inválida")

        with self.assertRaisesMessage(
            ValidationError, "La clave solo puede contener letras, números o guiones."
        ):
            manzana.full_clean()

    def test_responsable_es_opcional_y_se_muestra_en_la_representacion(self):
        responsable = crear_ciudadano()
        manzana = Manzana.objects.create(
            nombre="Centro", clave="M-01", responsable=responsable
        )

        self.assertEqual(manzana.responsable, responsable)
        self.assertEqual(str(manzana), "Centro (M-01)")

    def test_ciudadano_puede_quedar_sin_manzana_o_asociarse(self):
        sin_manzana = crear_ciudadano()
        manzana = Manzana.objects.create(nombre="Centro")
        asociado = crear_ciudadano(nombre="Beto", manzana=manzana)

        self.assertIsNone(sin_manzana.manzana)
        self.assertEqual(asociado.manzana, manzana)
        self.assertEqual(list(manzana.ciudadanos.all()), [asociado])

    def test_no_se_puede_eliminar_manzana_con_ciudadanos(self):
        manzana = Manzana.objects.create(nombre="Centro")
        crear_ciudadano(manzana=manzana)

        with self.assertRaises(ProtectedError):
            manzana.delete()

    def test_eliminar_responsable_no_elimina_la_manzana(self):
        responsable = crear_ciudadano()
        manzana = Manzana.objects.create(nombre="Centro", responsable=responsable)

        responsable.delete()

        manzana.refresh_from_db()
        self.assertIsNone(manzana.responsable)


class ManzanaAdminTests(TestCase):
    def test_listado_anota_cantidad_y_precarga_responsable_sin_n_mas_uno(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin-manzanas", password="test", email="admin@example.com"
        )
        responsable = crear_ciudadano()
        primera = Manzana.objects.create(nombre="Centro", responsable=responsable)
        Manzana.objects.create(nombre="Norte", responsable=responsable)
        crear_ciudadano(nombre="Beto", manzana=primera)
        request = RequestFactory().get("/admin/core/manzana/")
        request.user = usuario
        model_admin = ManzanaAdmin(Manzana, admin.site)

        with self.assertNumQueries(1):
            filas = [
                (obj.responsable.nombre, model_admin.cantidad_ciudadanos(obj))
                for obj in model_admin.get_queryset(request)
            ]

        self.assertEqual(filas, [("Ana", 1), ("Ana", 0)])


class ManzanaMigrationTests(TransactionTestCase):
    migrate_from = ("core", "0008_alter_ciudadano_motivo_alta")
    migrate_to = ("core", "0009_manzana_clave_manzana_responsable_and_more")

    def test_migracion_conserva_ciudadanos_y_manzanas_sin_inventar_relaciones(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        CiudadanoAnterior = old_apps.get_model("core", "Ciudadano")
        ManzanaAnterior = old_apps.get_model("core", "Manzana")
        manzana = ManzanaAnterior.objects.create(nombre="Histórica")
        con_manzana = CiudadanoAnterior.objects.create(
            nombre="Ana", apellido_paterno="López", edad=30, manzana=manzana
        )
        sin_manzana = CiudadanoAnterior.objects.create(
            nombre="Beto", apellido_paterno="Pérez", edad=31
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        CiudadanoNuevo = new_apps.get_model("core", "Ciudadano")
        ManzanaNueva = new_apps.get_model("core", "Manzana")

        self.assertTrue(ManzanaNueva.objects.filter(pk=manzana.pk).exists())
        self.assertEqual(
            CiudadanoNuevo.objects.get(pk=con_manzana.pk).manzana_id, manzana.pk
        )
        self.assertIsNone(
            CiudadanoNuevo.objects.get(pk=sin_manzana.pk).manzana_id
        )

    def tearDown(self):
        MigrationExecutor(connection).migrate(
            MigrationExecutor(connection).loader.graph.leaf_nodes()
        )
        super().tearDown()
