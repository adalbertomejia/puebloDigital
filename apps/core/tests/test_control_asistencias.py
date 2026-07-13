from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.comites.models import Comite
from apps.core.models import Ciudadano
from apps.operacion.models import Faena, RegistroFaena


class ControlAsistenciasFaenaCaptureButtonTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operador", password="password")
        self.client.force_login(self.user)
        self.comite = Comite.objects.create(nombre="Comité de prueba")
        self.ciudadano = Ciudadano.objects.create(
            nombre="Ana",
            apellido_paterno="López",
            edad=30,
        )

    def test_realizada_faena_with_records_shows_capture_button_in_control_list(self):
        faena = Faena.objects.create(
            comite=self.comite,
            fecha=timezone.localdate(),
            descripcion="Limpieza comunitaria",
            estado=Faena.Estados.REALIZADA,
        )
        RegistroFaena.objects.create(faena=faena, ciudadano=self.ciudadano)

        response = self.client.get(reverse("control_asistencias"))

        self.assertContains(response, reverse("captura_asistencia_faena", args=[faena.pk]))
        self.assertContains(response, "Capturar asistencia")

    def test_realizada_faena_with_records_allows_opening_capture_view(self):
        faena = Faena.objects.create(
            comite=self.comite,
            fecha=timezone.localdate(),
            descripcion="Limpieza comunitaria",
            estado=Faena.Estados.REALIZADA,
        )
        RegistroFaena.objects.create(faena=faena, ciudadano=self.ciudadano)

        response = self.client.get(reverse("captura_asistencia_faena", args=[faena.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Captura de asistencia")
