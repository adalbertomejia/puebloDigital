from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import Comite, PerfilAcceso, UsuarioApp
from apps.core.models import Ciudadano, Manzana


class ResponsabilidadesActivasTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="responsable", password="test-pass"
        )
        self.ciudadano = Ciudadano.objects.create(
            nombre="Rosa", apellido_paterno="Ejemplo", activo=True
        )
        self.manzana = Manzana.objects.create(
            nombre="Centro", activa=True, responsable=self.ciudadano
        )
        self.ciudadano.manzana = self.manzana
        self.ciudadano.save(update_fields=["manzana"])
        PerfilAcceso.objects.create(user=self.usuario, ciudadano=self.ciudadano)

    def test_deriva_responsabilidad_de_manzana_del_perfil_y_responsable(self):
        from apps.core.autorizacion import responsabilidades_activas

        responsabilidades = responsabilidades_activas(self.usuario)

        self.assertEqual(len(responsabilidades), 1)
        self.assertEqual(responsabilidades[0].tipo, "MANZANA")
        self.assertEqual(responsabilidades[0].rol, "RESPONSABLE_MANZANA")
        self.assertEqual(responsabilidades[0].manzana, self.manzana)
        self.assertIsNone(responsabilidades[0].comite)

    def test_no_deriva_manzana_si_cuenta_ciudadano_o_manzana_estan_inactivos(self):
        from apps.core.autorizacion import responsabilidades_activas

        self.usuario.is_active = False
        self.usuario.save(update_fields=["is_active"])
        self.assertEqual(responsabilidades_activas(self.usuario), [])

        self.usuario.is_active = True
        self.usuario.save(update_fields=["is_active"])
        self.ciudadano.activo = False
        self.ciudadano.save(update_fields=["activo"])
        self.assertEqual(responsabilidades_activas(self.usuario), [])

        self.ciudadano.activo = True
        self.ciudadano.save(update_fields=["activo"])
        self.manzana.activa = False
        self.manzana.save(update_fields=["activa"])
        self.assertEqual(responsabilidades_activas(self.usuario), [])

    def test_no_deriva_manzana_si_el_ciudadano_ya_no_es_responsable(self):
        from apps.core.autorizacion import responsabilidades_activas

        otra_persona = Ciudadano.objects.create(
            nombre="Luis", apellido_paterno="Ejemplo", manzana=self.manzana
        )
        self.manzana.responsable = otra_persona
        self.manzana.save(update_fields=["responsable"])

        self.assertEqual(responsabilidades_activas(self.usuario), [])

    def test_deriva_cargos_activos_de_comite_y_omite_asignaciones_inactivas(self):
        from apps.core.autorizacion import responsabilidades_activas

        comite_activo = Comite.objects.create(nombre="Comité del Agua", activo=True)
        comite_inactivo = Comite.objects.create(nombre="Comité anterior", activo=False)
        UsuarioApp.objects.create(
            user=self.usuario,
            comite=comite_activo,
            rol=UsuarioApp.Roles.TESORERO,
            activo=True,
        )
        UsuarioApp.objects.create(
            user=self.usuario,
            comite=comite_inactivo,
            rol=UsuarioApp.Roles.SECRETARIO,
            activo=True,
        )
        UsuarioApp.objects.create(
            user=self.usuario,
            comite=comite_activo,
            rol=UsuarioApp.Roles.LECTURA,
            activo=False,
        )

        responsabilidades = responsabilidades_activas(self.usuario)

        self.assertEqual(len(responsabilidades), 2)
        cargo = next(item for item in responsabilidades if item.tipo == "COMITE")
        self.assertEqual(cargo.rol, UsuarioApp.Roles.TESORERO)
        self.assertEqual(cargo.comite, comite_activo)
        self.assertIsNone(cargo.manzana)

    def test_usuario_sin_sesion_no_tiene_responsabilidades(self):
        from django.contrib.auth.models import AnonymousUser
        from apps.core.autorizacion import responsabilidades_activas

        self.assertEqual(responsabilidades_activas(AnonymousUser()), [])

    def test_superusuario_recibe_alcance_global(self):
        from apps.core.autorizacion import responsabilidades_activas

        admin = get_user_model().objects.create_superuser(
            username="admin-accesos", password="test-pass", email="admin@example.com"
        )

        responsabilidades = responsabilidades_activas(admin)

        self.assertEqual(responsabilidades[0].tipo, "GLOBAL")
        self.assertEqual(responsabilidades[0].rol, "ADMINISTRADOR")


class VistaMisResponsabilidadesTests(TestCase):
    def test_exige_inicio_de_sesion(self):
        response = self.client.get(reverse("mis_responsabilidades"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('mis_responsabilidades')}",
        )

    def test_muestra_cargo_y_ambito_activos_de_la_cuenta(self):
        usuario = get_user_model().objects.create_user(username="tesorero")
        self.client.force_login(usuario)
        ciudadano = Ciudadano.objects.create(
            nombre="Rosa", apellido_paterno="Ejemplo", activo=True
        )
        manzana = Manzana.objects.create(
            nombre="Centro", activa=True, responsable=ciudadano
        )
        ciudadano.manzana = manzana
        ciudadano.save(update_fields=["manzana"])
        PerfilAcceso.objects.create(user=usuario, ciudadano=ciudadano)
        comite = Comite.objects.create(nombre="Comité del Agua", activo=True)
        UsuarioApp.objects.create(
            user=usuario,
            comite=comite,
            rol=UsuarioApp.Roles.TESORERO,
            activo=True,
        )

        response = self.client.get(reverse("mis_responsabilidades"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Responsable de manzana")
        self.assertContains(response, "Centro")
        self.assertContains(response, "Tesorero")
        self.assertContains(response, "Comité del Agua")
        self.assertIn("ámbito asociado", response.content.decode().casefold())

    def test_muestra_ciudadano_vinculado_a_la_cuenta_actual_sin_cargos(self):
        usuario = get_user_model().objects.create_user(username="cuenta-actual")
        otro_usuario = get_user_model().objects.create_user(username="otra-cuenta")
        ciudadano = Ciudadano.objects.create(nombre="Elena", apellido_paterno="Vinculada", apellido_materno="Actual")
        otro = Ciudadano.objects.create(nombre="Persona", apellido_paterno="Ajena")
        PerfilAcceso.objects.create(user=usuario, ciudadano=ciudadano)
        PerfilAcceso.objects.create(user=otro_usuario, ciudadano=otro)
        self.client.force_login(usuario)

        response = self.client.get(reverse("mis_responsabilidades"), {"user_id": otro_usuario.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["ciudadano_vinculado"], ciudadano)
        self.assertContains(response, "cuenta-actual")
        self.assertContains(response, "Elena Vinculada Actual")
        self.assertContains(response, "Sin manzana asignada")
        self.assertNotContains(response, "Persona Ajena")
        self.assertContains(response, "Tu cuenta no tiene responsabilidades activas registradas.")

    def test_cuenta_sin_perfil_no_infiere_identidad_del_cargo_de_comite(self):
        usuario = get_user_model().objects.create_user(username="sin-vinculo-general")
        ciudadano = Ciudadano.objects.create(nombre="Identidad", apellido_paterno="Historica")
        comite = Comite.objects.create(nombre="Comité del Agua")
        UsuarioApp.objects.create(user=usuario, ciudadano=ciudadano, comite=comite, rol=UsuarioApp.Roles.TESORERO)
        self.client.force_login(usuario)

        response = self.client.get(reverse("mis_responsabilidades"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["ciudadano_vinculado"])
        self.assertContains(response, "Tu cuenta no tiene un ciudadano vinculado.")
        self.assertContains(response, "Tesorero")
        self.assertNotContains(response, "Identidad Historica")

    def test_ciudadano_inactivo_se_muestra_sin_habilitar_responsabilidad(self):
        usuario = get_user_model().objects.create_user(username="vinculo-inactivo")
        ciudadano = Ciudadano.objects.create(nombre="Rosa", apellido_paterno="Inactiva", activo=False)
        manzana = Manzana.objects.create(nombre="Centro inactivo", responsable=ciudadano)
        ciudadano.manzana = manzana
        ciudadano.save(update_fields=["manzana"])
        PerfilAcceso.objects.create(user=usuario, ciudadano=ciudadano)
        self.client.force_login(usuario)

        response = self.client.get(reverse("mis_responsabilidades"))

        self.assertContains(response, "Rosa Inactiva")
        self.assertContains(response, "Centro inactivo")
        self.assertContains(response, "Inactivo")
        self.assertEqual(response.context["responsabilidades"], [])

    def test_mi_acceso_describe_funciones_por_cargo_sin_mezclar_comites(self):
        usuario = get_user_model().objects.create_user(username="cargos-distintos")
        agua = Comite.objects.create(nombre="Comité Agua")
        feria = Comite.objects.create(nombre="Comité Feria")
        UsuarioApp.objects.create(user=usuario, comite=agua, rol="PRESIDENTE")
        UsuarioApp.objects.create(user=usuario, comite=feria, rol="TESORERO")
        self.client.force_login(usuario)
        response = self.client.get(reverse("mis_responsabilidades"))
        responsabilidades = {r.comite.pk: r for r in response.context["responsabilidades"]}
        self.assertIn("Crear y gestionar eventos generales de este comité", responsabilidades[agua.pk].funciones)
        self.assertNotIn("Crear y gestionar eventos generales de este comité", responsabilidades[feria.pk].funciones)
        self.assertIn("Generar obligaciones y registrar abonos de este comité", responsabilidades[feria.pk].funciones)
        self.assertContains(response, "Funciones de este cargo", count=2)
        self.assertContains(response, "Comité Agua")
        self.assertContains(response, "Comité Feria")

    def test_secretario_describe_solicitudes_sin_prometer_funciones_financieras(self):
        usuario = get_user_model().objects.create_user(username="solo-secretario")
        comite = Comite.objects.create(nombre="Comité local")
        UsuarioApp.objects.create(user=usuario, comite=comite, rol="SECRETARIO")
        self.client.force_login(usuario)
        response = self.client.get(reverse("mis_responsabilidades"))
        self.assertContains(response, "Secretario")
        self.assertContains(response, "Registrar, asignar y dar seguimiento a solicitudes de este comité para ciudadanos autorizados")
        self.assertNotContains(response, "Generar obligaciones y registrar abonos de este comité")
