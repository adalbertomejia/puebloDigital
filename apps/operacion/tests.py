from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.comites.models import Comite
from apps.core.models import Ciudadano, Manzana

from apps.operacion.models import Faena, RegistroFaena
from apps.operacion.services import generar_participantes_faena


class FaenaAlcanceTests(TestCase):
    def setUp(self):
        self.comite = Comite.objects.create(nombre="Comité")
        self.manzana = Manzana.objects.create(nombre="Manzana 4")

    def faena(self, **kwargs):
        data = {"comite": self.comite, "fecha": date(2026, 7, 31), "descripcion": "Limpieza"}
        data.update(kwargs)
        return Faena.objects.create(**data)

    def ciudadano(self, nombre, **kwargs):
        data = {"apellido_paterno": "Pérez", "edad": 30}
        data.update(kwargs)
        return Ciudadano.objects.create(nombre=nombre, **data)

    def test_alcance_general_predeterminado_y_validaciones(self):
        general = Faena(comite=self.comite, fecha=date.today(), descripcion="General")
        self.assertEqual(general.alcance, Faena.Alcances.GENERAL)
        general.full_clean()
        general.manzana = self.manzana
        with self.assertRaises(ValidationError):
            general.full_clean()
        general.alcance = Faena.Alcances.MANZANA
        general.manzana = None
        with self.assertRaises(ValidationError):
            general.full_clean()

    def test_generacion_general_es_idempotente_y_excluye_inactivos(self):
        activo = self.ciudadano("Ana")
        self.ciudadano("Beto", activo=False)
        faena = self.faena()
        self.assertEqual(generar_participantes_faena(faena), (1, 0, 1))
        registro = RegistroFaena.objects.get(faena=faena, ciudadano=activo)
        registro.estatus = RegistroFaena.Estatus.ASISTIO
        registro.save()
        self.assertEqual(generar_participantes_faena(faena), (0, 1, 1))
        registro.refresh_from_db()
        self.assertEqual(registro.estatus, RegistroFaena.Estatus.ASISTIO)

    def test_generacion_por_manzana_solo_incluye_poblacion_objetivo(self):
        incluida = self.ciudadano("Ana", manzana=self.manzana)
        otra = Manzana.objects.create(nombre="Manzana 5")
        self.ciudadano("Beto", manzana=otra)
        self.ciudadano("Carla")
        self.ciudadano("Diana", manzana=self.manzana, activo=False)
        faena = self.faena(alcance=Faena.Alcances.MANZANA, manzana=self.manzana)
        generar_participantes_faena(faena)
        self.assertEqual(list(faena.registros.values_list("ciudadano_id", flat=True)), [incluida.pk])

    def test_participantes_bloquean_cambios_de_alcance_y_manzana(self):
        ciudadano = self.ciudadano("Ana")
        faena = self.faena()
        RegistroFaena.objects.create(faena=faena, ciudadano=ciudadano)
        faena.alcance = Faena.Alcances.MANZANA
        faena.manzana = self.manzana
        with self.assertRaises(ValidationError):
            faena.full_clean()
