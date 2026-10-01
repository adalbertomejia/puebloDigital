from django.test import SimpleTestCase

from apps.comites.models import Comite


class ComiteTiposTests(SimpleTestCase):
    def test_incluye_todos_los_tipos_de_comite_requeridos(self):
        tipos_requeridos = {
            "AGUA": "Agua",
            "PANTEON": "Panteón",
            "FERIA": "Feria",
            "IGLESIA": "Iglesia",
            "PEREGRINO": "Peregrino",
            "CLINICA": "Clínica",
            "PEREGRINACION": "Peregrinación",
        }

        self.assertLessEqual(tipos_requeridos.items(), dict(Comite.Tipos.choices).items())
