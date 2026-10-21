from django.test import SimpleTestCase
from django.contrib import admin

from apps.comites.models import Comite, PerfilAcceso
from apps.core.admin import CiudadanoAdmin, PerfilAccesoInline
from apps.core.models import Ciudadano


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


class PerfilAccesoAdministracionTests(SimpleTestCase):
    def test_perfil_acceso_se_puede_asignar_desde_el_admin_del_ciudadano(self):
        self.assertIn(PerfilAccesoInline, CiudadanoAdmin.inlines)
        self.assertIn(PerfilAcceso, admin.site._registry)

    def test_ciudadano_muestra_el_vinculo_de_cuenta_en_su_admin(self):
        inline = PerfilAccesoInline(Ciudadano, CiudadanoAdmin(Ciudadano, admin.site))

        self.assertEqual(inline.model, PerfilAcceso)
        self.assertEqual(inline.max_num, 1)
        self.assertIn("user", inline.fields)
