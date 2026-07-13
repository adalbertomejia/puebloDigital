import csv
import io
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import Comite
from apps.core.models import Ciudadano
from apps.operacion.models import AsistenciaJunta, Faena, Junta, RegistroFaena


class ExportacionParticipantesCsvTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="secretaria", password="testpass123")
        self.client.force_login(self.user)
        self.comite = Comite.objects.create(nombre="Delegación Ñuu", tipo=Comite.Tipos.DELEGACION)
        self.ana = Ciudadano.objects.create(nombre="Ana", apellido_paterno="García", apellido_materno="Ruiz", edad=30)
        self.juan = Ciudadano.objects.create(nombre="Juan", apellido_paterno="Pérez", apellido_materno="López", edad=31)
        self.otro = Ciudadano.objects.create(nombre="Pedro", apellido_paterno="Martínez", apellido_materno="Soto", edad=32)

    def _rows(self, response):
        content = response.content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(content)))

    def test_exporta_participantes_de_faena_con_bom_nombre_y_orden_estable(self):
        faena = Faena.objects.create(comite=self.comite, fecha=date(2026, 6, 26), descripcion="Limpieza del camino, zona ñ")
        otra_faena = Faena.objects.create(comite=self.comite, fecha=date(2026, 6, 27), descripcion="Otra faena")
        RegistroFaena.objects.create(faena=faena, ciudadano=self.juan, estatus=RegistroFaena.Estatus.ASISTIO)
        RegistroFaena.objects.create(
            faena=faena,
            ciudadano=self.ana,
            estatus=RegistroFaena.Estatus.FALTO,
            genera_adeudo=True,
            monto_adeudo=Decimal("100.00"),
            observaciones="Traer justificante",
        )
        RegistroFaena.objects.create(faena=otra_faena, ciudadano=self.otro, estatus=RegistroFaena.Estatus.PENDIENTE)

        response = self.client.get(reverse("exportar_participantes_faena_csv", args=[faena.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(f'filename="faena_{faena.pk}_participantes_2026-06-26.csv"', response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        rows = self._rows(response)
        self.assertEqual(rows[0], ["Numero", "Nombre completo", "Estado", "Fecha", "Tipo de evento", "Descripcion", "Genera adeudo", "Monto adeudo", "Observaciones"])
        self.assertEqual([row[1] for row in rows[1:]], ["Ana García Ruiz", "Juan Pérez López"])
        self.assertEqual(rows[1][2:8], ["FALTO", "2026-06-26", "Faena", "Limpieza del camino, zona ñ", "Sí", "100.00"])
        self.assertNotIn("Pedro Martínez Soto", response.content.decode("utf-8-sig"))

    def test_exporta_participantes_de_junta_incluyendo_pendientes_y_justificados(self):
        junta = Junta.objects.create(comite=self.comite, fecha=date(2026, 6, 25), tema="Asamblea general", tipo=Junta.Tipos.ORDINARIA)
        AsistenciaJunta.objects.create(junta=junta, ciudadano=self.juan, estatus=AsistenciaJunta.Estatus.JUSTIFICADO, asistio=False)
        AsistenciaJunta.objects.create(junta=junta, ciudadano=self.ana, estatus=AsistenciaJunta.Estatus.PENDIENTE, asistio=False)

        response = self.client.get(reverse("exportar_participantes_junta_csv", args=[junta.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIn(f'filename="junta_{junta.pk}_participantes_2026-06-25.csv"', response["Content-Disposition"])
        rows = self._rows(response)
        self.assertEqual([row[2] for row in rows[1:]], ["PENDIENTE", "JUSTIFICADO"])
        self.assertEqual({row[4] for row in rows[1:]}, {"Junta"})

    def test_evento_sin_participantes_descarga_solo_encabezados(self):
        faena = Faena.objects.create(comite=self.comite, fecha=date(2026, 7, 1), descripcion="Sin registros")

        response = self.client.get(reverse("exportar_participantes_faena_csv", args=[faena.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self._rows(response)), 1)
