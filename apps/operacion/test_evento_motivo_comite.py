from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.comites.models import Comite
from apps.core.models import Manzana
from apps.operacion.models import Faena, Junta


class EventoMotivoComiteTests(TestCase):
    def setUp(self):
        self.manzana = Manzana.objects.create(nombre="Manzana sintética")
        self.comite = Comite.objects.create(nombre="Comité sintético")

    def test_faena_de_manzana_no_requiere_comite_y_exige_motivo(self):
        faena = Faena(
            comite=None,
            fecha=date(2026, 10, 20),
            alcance=Faena.Alcances.MANZANA,
            manzana=self.manzana,
            descripcion="Limpieza de la manzana",
            motivo="Retirar residuos de la vía pública",
        )
        faena.full_clean()

        faena.motivo = ""
        with self.assertRaises(ValidationError) as error:
            faena.full_clean()
        self.assertIn("motivo", error.exception.message_dict)

    def test_junta_de_manzana_no_requiere_comite_y_exige_motivo(self):
        junta = Junta(
            comite=None,
            fecha=date(2026, 10, 20),
            alcance=Junta.Alcances.MANZANA,
            manzana=self.manzana,
            tema="Organización vecinal",
            motivo="Coordinar reparación del alumbrado",
        )
        junta.full_clean()

        junta.motivo = ""
        with self.assertRaises(ValidationError) as error:
            junta.full_clean()
        self.assertIn("motivo", error.exception.message_dict)

    def test_eventos_generales_conservan_comite_y_pueden_ser_generales(self):
        faena = Faena(
            comite=self.comite,
            fecha=date(2026, 10, 20),
            alcance=Faena.Alcances.GENERAL,
            descripcion="Mantenimiento comunitario",
        )
        junta = Junta(
            comite=self.comite,
            fecha=date(2026, 10, 20),
            alcance=Junta.Alcances.GENERAL,
            tema="Asamblea comunitaria",
        )

        faena.full_clean()
        junta.full_clean()

