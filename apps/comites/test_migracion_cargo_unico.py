from django.apps import apps as runtime_apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracionCargoUnicoTests(TransactionTestCase):
    anteriores = [
        ("core", "0003_ciudadano_fecha_baja_ciudadano_motivo_baja_and_more"),
        ("comites", "0003_alter_usuarioapp_ciudadano"),
    ]

    def setUp(self):
        executor = MigrationExecutor(connection)
        self.finales = executor.loader.graph.leaf_nodes()
        executor.migrate(self.anteriores)
        self.old = executor.loader.project_state(self.anteriores).apps
        Usuario = self.old.get_model("auth", "User")
        Ciudadano = self.old.get_model("core", "Ciudadano")
        Comite = self.old.get_model("comites", "Comite")
        self.user = Usuario.objects.create(username="migration-role")
        self.persona = Ciudadano.objects.create(
            nombre="Identidad", apellido_paterno="Anterior"
        )
        self.comite = Comite.objects.create(nombre="Comité")
        self.otro = Comite.objects.create(nombre="Otro comité")

    def tearDown(self):
        # Dispose only of this test's deliberately invalid fixtures, then restore all leaves.
        self.old.get_model("comites", "UsuarioApp").objects.all().update(activo=False)
        MigrationExecutor(connection).migrate(self.finales)
        super().tearDown()

    def perfil(self):
        return self.old.get_model("comites", "PerfilAcceso").objects.create(
            user_id=self.user.pk, ciudadano_id=self.persona.pk
        )

    def cargo(self, comite=None, rol="LECTURA"):
        return self.old.get_model("comites", "UsuarioApp").objects.create(
            user_id=self.user.pk,
            comite_id=(comite or self.comite).pk,
            rol=rol,
            activo=True,
        )

    def test_completa_solo_el_vinculo_inequivoco_y_conserva_el_cargo(self):
        self.perfil()
        cargo = self.cargo()
        MigrationExecutor(connection).migrate(self.finales)
        actualizado = runtime_apps.get_model("comites", "UsuarioApp").objects.get(
            pk=cargo.pk
        )
        self.assertEqual(actualizado.ciudadano_id, self.persona.pk)
        self.assertEqual(actualizado.rol, "LECTURA")
        self.assertTrue(actualizado.activo)

    def test_conflicto_aborta_antes_de_modificar_o_elegir_un_cargo(self):
        self.perfil()
        self.cargo(rol="PRESIDENTE")
        self.cargo(self.otro, rol="TESORERO")
        Cargo = self.old.get_model("comites", "UsuarioApp")
        antes = list(Cargo.objects.order_by("pk").values())
        with self.assertRaisesMessage(RuntimeError, "auditar_cargos"):
            MigrationExecutor(connection).migrate(self.finales)
        self.assertEqual(antes, list(Cargo.objects.order_by("pk").values()))

    def test_cuenta_sin_identidad_se_reporta_sin_inventar_ciudadano(self):
        cargo = self.cargo()
        with self.assertRaisesMessage(RuntimeError, "cuenta_sin_vinculo"):
            MigrationExecutor(connection).migrate(self.finales)
        cargo.refresh_from_db()
        self.assertIsNone(cargo.ciudadano_id)
        self.assertTrue(cargo.activo)
