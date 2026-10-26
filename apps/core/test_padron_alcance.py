import csv
import io

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import Comite, PerfilAcceso, UsuarioApp
from apps.core.models import Ciudadano, Manzana


class AlcancePadronTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.responsable = User.objects.create_user(
            username="responsable-centro", password="test-pass"
        )
        self.ciudadano_responsable = Ciudadano.objects.create(
            nombre="Rosa", apellido_paterno="Responsable", activo=True
        )
        self.manzana = Manzana.objects.create(
            nombre="Centro", activa=True, responsable=self.ciudadano_responsable
        )
        self.ciudadano_responsable.manzana = self.manzana
        self.ciudadano_responsable.save(update_fields=["manzana"])
        PerfilAcceso.objects.create(
            user=self.responsable, ciudadano=self.ciudadano_responsable
        )
        self.ciudadano_local = Ciudadano.objects.create(
            nombre="Ana", apellido_paterno="Local", manzana=self.manzana
        )
        otra_manzana = Manzana.objects.create(nombre="Norte", activa=True)
        self.ciudadano_ajeno = Ciudadano.objects.create(
            nombre="Luis", apellido_paterno="Ajeno", manzana=otra_manzana
        )

    def test_queryset_visible_para_responsable_contiene_solo_su_manzana(self):
        visibles = Ciudadano.objects.visibles_para(self.responsable)

        self.assertQuerySetEqual(
            visibles.order_by("pk"),
            [self.ciudadano_responsable, self.ciudadano_local],
        )

    def test_padron_y_peticion_htmx_no_exponen_otras_manzanas(self):
        self.client.force_login(self.responsable)

        response = self.client.get(reverse("padron_ciudadanos"))
        htmx = self.client.get(
            reverse("padron_ciudadanos"), HTTP_HX_REQUEST="true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ana Local")
        self.assertNotContains(response, "Luis Ajeno")
        self.assertEqual(htmx.status_code, 200)
        self.assertContains(htmx, "Ana Local")
        self.assertNotContains(htmx, "Luis Ajeno")
        self.assertEqual(response.context["metricas"]["total"], 2)
        self.assertEqual(list(response.context["manzanas"]), [self.manzana])

    def test_exportacion_csv_respeta_el_mismo_alcance(self):
        self.client.force_login(self.responsable)

        response = self.client.get(reverse("exportar_ciudadanos_csv"))
        filas = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        nombres = {fila[4] for fila in filas[1:]}

        self.assertEqual(response.status_code, 200)
        self.assertIn("Ana Local", nombres)
        self.assertIn("Rosa Responsable", nombres)
        self.assertNotIn("Luis Ajeno", nombres)

    def test_peticion_directa_a_expediente_ajeno_devuelve_404(self):
        self.client.force_login(self.responsable)

        response = self.client.get(
            reverse("perfil_ciudadano", args=[self.ciudadano_ajeno.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_expediente_de_su_manzana_muestra_operacion_y_oculta_tesoreria(self):
        self.client.force_login(self.responsable)
        response = self.client.get(reverse("perfil_ciudadano", args=[self.ciudadano_local.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Datos generales")
        self.assertNotContains(response, "Historial financiero por concepto")
        self.assertNotContains(response, "Ver obligaciones en Tesorería")

    def test_cargo_de_tesoreria_sin_rol_operativo_no_abre_el_padron(self):
        tesorero = get_user_model().objects.create_user(username="tesorero")
        comite = Comite.objects.create(nombre="Comité financiero")
        UsuarioApp.objects.create(
            user=tesorero,
            comite=comite,
            rol=UsuarioApp.Roles.TESORERO,
            activo=True,
        )
        self.client.force_login(tesorero)

        self.assertEqual(self.client.get(reverse("padron_ciudadanos")).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("exportar_ciudadanos_csv")).status_code, 404
        )

    def test_responsable_no_puede_editar_o_crear_ciudadanos_por_url_directa(self):
        self.client.force_login(self.responsable)

        crear = self.client.get(reverse("crear_ciudadano_operativo"))
        editar = self.client.get(
            reverse("editar_ciudadano_operativo", args=[self.ciudadano_local.pk])
        )

        self.assertEqual(crear.status_code, 404)
        self.assertEqual(editar.status_code, 404)

    def test_superusuario_conserva_acceso_global_al_padron_y_exportacion(self):
        admin = get_user_model().objects.create_superuser(
            username="admin-padron", password="test-pass", email="admin@example.com"
        )
        self.client.force_login(admin)

        response = self.client.get(reverse("padron_ciudadanos"))
        exportacion = self.client.get(reverse("exportar_ciudadanos_csv"))

        self.assertContains(response, "Luis Ajeno")
        self.assertIn("Luis Ajeno", exportacion.content.decode("utf-8-sig"))

    def test_sin_sesion_sigue_redirigiendo_al_login(self):
        response = self.client.get(reverse("padron_ciudadanos"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('padron_ciudadanos')}",
        )
