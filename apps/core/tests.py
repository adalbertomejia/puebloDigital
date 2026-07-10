from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.comites.models import Comite
from apps.core.models import Ciudadano
from apps.operacion.models import AsistenciaJunta, Faena, Junta, RegistroFaena


class CapturaAsistenciaFaenaTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operador", password="secret")
        self.client.force_login(self.user)
        self.comite = Comite.objects.create(nombre="Comité Central")
        self.ciudadano = Ciudadano.objects.create(
            nombre="Ana",
            apellido_paterno="López",
            apellido_materno="Pérez",
            edad=35,
        )
        self.faena = Faena.objects.create(
            comite=self.comite,
            fecha=timezone.localdate(),
            descripcion="Limpieza comunitaria",
            estado=Faena.Estados.PROGRAMADA,
        )
        RegistroFaena.objects.create(faena=self.faena, ciudadano=self.ciudadano)
        self.junta = Junta.objects.create(
            comite=self.comite,
            fecha=timezone.localdate(),
            tema="Organización vecinal",
            estado=Junta.Estados.PROGRAMADA,
        )
        AsistenciaJunta.objects.create(junta=self.junta, ciudadano=self.ciudadano)

    def test_faena_card_shows_capture_button_with_correct_route(self):
        response = self.client.get(reverse("control_asistencias") + "?tipo=faenas#faenas")

        self.assertContains(response, "Capturar asistencia")
        self.assertContains(response, reverse("captura_asistencia_faena", args=[self.faena.pk]))

    def test_faena_detail_shows_capture_button_with_correct_route(self):
        response = self.client.get(reverse("control_asistencias_faena_detalle", args=[self.faena.pk]))

        self.assertContains(response, "Capturar asistencia")
        self.assertContains(response, reverse("captura_asistencia_faena", args=[self.faena.pk]))

    def test_faena_capture_route_opens_operational_capture_view(self):
        response = self.client.get(reverse("captura_asistencia_faena", args=[self.faena.pk]))

        self.assertContains(response, "Captura de asistencia")
        self.assertContains(response, "Limpieza comunitaria")
        self.assertTemplateUsed(response, "dashboard/captura_asistencia.html")

    def test_junta_capture_button_remains_equivalent(self):
        response = self.client.get(reverse("control_asistencias_junta_detalle", args=[self.junta.pk]))

        self.assertContains(response, "Capturar asistencia")
        self.assertContains(response, reverse("captura_asistencia_junta", args=[self.junta.pk]))
