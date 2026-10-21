import csv
import io
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import PerfilAcceso, Comite
from apps.core.models import Ciudadano, Manzana
from apps.operacion.models import AsistenciaJunta, Faena, Junta, RegistroFaena


class AlcanceOperacionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.responsable = User.objects.create_user(username="operacion-centro", password="test-pass")
        self.comite = Comite.objects.create(nombre="Comité de agua")
        self.ciudadano_responsable = Ciudadano.objects.create(nombre="Rosa", apellido_paterno="Responsable")
        self.manzana = Manzana.objects.create(nombre="Centro", responsable=self.ciudadano_responsable)
        self.ciudadano_responsable.manzana = self.manzana
        self.ciudadano_responsable.save(update_fields=["manzana"])
        PerfilAcceso.objects.create(user=self.responsable, ciudadano=self.ciudadano_responsable)
        self.ciudadano_local = Ciudadano.objects.create(nombre="Ana", apellido_paterno="Local", manzana=self.manzana)
        otra_manzana = Manzana.objects.create(nombre="Norte")
        self.ciudadano_ajeno = Ciudadano.objects.create(nombre="Luis", apellido_paterno="Ajeno", manzana=otra_manzana)

        self.faena_local = Faena.objects.create(
            comite=self.comite, fecha=date(2026, 10, 1), alcance=Faena.Alcances.MANZANA,
            manzana=self.manzana, descripcion="Limpieza Centro",
        )
        self.faena_ajena = Faena.objects.create(
            comite=self.comite, fecha=date(2026, 10, 2), alcance=Faena.Alcances.MANZANA,
            manzana=otra_manzana, descripcion="Limpieza Norte",
        )
        self.faena_general = Faena.objects.create(
            comite=self.comite, fecha=date(2026, 10, 3), alcance=Faena.Alcances.GENERAL,
            descripcion="Limpieza general",
        )
        self.registro_local = RegistroFaena.objects.create(faena=self.faena_general, ciudadano=self.ciudadano_local)
        self.registro_ajeno = RegistroFaena.objects.create(faena=self.faena_general, ciudadano=self.ciudadano_ajeno)
        self.junta_general = Junta.objects.create(
            comite=self.comite, fecha=date(2026, 10, 4), alcance=Junta.Alcances.GENERAL, tema="Asamblea general",
        )
        self.asistencia_local = AsistenciaJunta.objects.create(junta=self.junta_general, ciudadano=self.ciudadano_local)
        self.asistencia_ajena = AsistenciaJunta.objects.create(junta=self.junta_general, ciudadano=self.ciudadano_ajeno)

    def test_queryset_de_faenas_y_registros_deriva_el_alcance_del_responsable(self):
        self.assertQuerySetEqual(
            Faena.objects.visibles_para(self.responsable).order_by("pk"),
            [self.faena_local, self.faena_general],
        )
        self.assertQuerySetEqual(
            RegistroFaena.objects.visibles_para(self.responsable).order_by("pk"),
            [self.registro_local],
        )

    def test_queryset_de_juntas_y_asistencias_limita_participantes_en_evento_general(self):
        self.assertQuerySetEqual(
            Junta.objects.visibles_para(self.responsable).order_by("pk"),
            [self.junta_general],
        )
        self.assertQuerySetEqual(
            AsistenciaJunta.objects.visibles_para(self.responsable).order_by("pk"),
            [self.asistencia_local],
        )

    def test_detalle_y_exportacion_de_evento_general_solo_muestran_su_manzana(self):
        self.client.force_login(self.responsable)
        detalle = self.client.get(reverse("control_asistencias_faena_detalle", args=[self.faena_general.pk]))
        exportacion = self.client.get(reverse("exportar_participantes_faena_csv", args=[self.faena_general.pk]))
        texto = exportacion.content.decode("utf-8-sig")

        self.assertEqual(detalle.status_code, 200)
        self.assertContains(detalle, "Ana Local")
        self.assertNotContains(detalle, "Luis Ajeno")
        self.assertIn("Ana Local", texto)
        self.assertNotIn("Luis Ajeno", texto)

    def test_peticion_directa_a_evento_de_otra_manzana_devuelve_404(self):
        self.client.force_login(self.responsable)
        response = self.client.get(reverse("control_asistencias_faena_detalle", args=[self.faena_ajena.pk]))
        self.assertEqual(response.status_code, 404)

    def test_captura_no_actualiza_registros_de_otra_manzana(self):
        self.client.force_login(self.responsable)
        self.registro_local.estatus = RegistroFaena.Estatus.PENDIENTE
        self.registro_local.save(update_fields=["estatus", "updated_at"])
        self.registro_ajeno.estatus = RegistroFaena.Estatus.PENDIENTE
        self.registro_ajeno.save(update_fields=["estatus", "updated_at"])

        response = self.client.post(
            reverse("captura_asistencia_faena", args=[self.faena_general.pk]),
            {f"registro_{self.registro_local.pk}_estatus": RegistroFaena.Estatus.ASISTIO,
             f"registro_{self.registro_ajeno.pk}_estatus": RegistroFaena.Estatus.FALTO},
        )

        self.registro_local.refresh_from_db()
        self.registro_ajeno.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.registro_local.estatus, RegistroFaena.Estatus.ASISTIO)
        self.assertEqual(self.registro_ajeno.estatus, RegistroFaena.Estatus.PENDIENTE)

    def test_superusuario_mantiene_acceso_global_a_eventos_y_registros(self):
        admin = get_user_model().objects.create_superuser(
            username="admin-op", password="test-pass", email="admin@example.com"
        )
        self.assertQuerySetEqual(
            Faena.objects.visibles_para(admin).order_by("pk"),
            [self.faena_local, self.faena_ajena, self.faena_general],
        )
        self.assertQuerySetEqual(
            RegistroFaena.objects.visibles_para(admin).order_by("pk"),
            [self.registro_local, self.registro_ajeno],
        )
