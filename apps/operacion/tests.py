from datetime import date

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.comites.models import Comite
from apps.core.models import Ciudadano, Manzana

from apps.core.forms import JuntaOperativaForm
from apps.operacion.models import AsistenciaJunta, Faena, Junta, RegistroFaena
from apps.operacion.services import generar_participantes_faena, generar_participantes_junta
from apps.core import views as core_views


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


class JuntaAlcanceTests(TestCase):
    def setUp(self):
        self.comite = Comite.objects.create(nombre="Comité de juntas")
        self.manzana = Manzana.objects.create(nombre="Manzana 4")

    def junta(self, **kwargs):
        data = {"comite": self.comite, "fecha": date(2026, 7, 31), "tema": "Acuerdos"}
        data.update(kwargs)
        return Junta.objects.create(**data)

    def ciudadano(self, nombre, **kwargs):
        data = {"apellido_paterno": "Pérez", "edad": 30}
        data.update(kwargs)
        return Ciudadano.objects.create(nombre=nombre, **data)

    def test_general_es_predeterminado_y_valida_combinaciones(self):
        general = Junta(comite=self.comite, fecha=date.today(), tema="General")
        self.assertEqual(general.alcance, Junta.Alcances.GENERAL)
        general.full_clean()
        general.manzana = self.manzana
        with self.assertRaises(ValidationError):
            general.full_clean()
        general.alcance, general.manzana = Junta.Alcances.MANZANA, None
        with self.assertRaises(ValidationError):
            general.full_clean()

    def test_junta_por_manzana_valida(self):
        junta = self.junta(alcance=Junta.Alcances.MANZANA, manzana=self.manzana)
        junta.full_clean()

    def test_generacion_general_idempotente_incremental_y_preserva_estados(self):
        ana = self.ciudadano("Ana")
        self.ciudadano("Inactiva", activo=False)
        junta = self.junta()
        self.assertEqual(generar_participantes_junta(junta), (1, 0, 1))
        asistencia = AsistenciaJunta.objects.get(junta=junta, ciudadano=ana)
        asistencia.estatus = AsistenciaJunta.Estatus.ASISTIO
        asistencia.save()
        self.assertEqual(generar_participantes_junta(junta), (0, 1, 1))
        asistencia.refresh_from_db()
        self.assertEqual(asistencia.estatus, AsistenciaJunta.Estatus.ASISTIO)
        beto = self.ciudadano("Beto")
        self.assertEqual(generar_participantes_junta(junta), (1, 1, 2))
        self.assertTrue(junta.asistencias.filter(ciudadano=beto).exists())

    def test_generacion_por_manzana_excluye_otros_sin_manzana_e_inactivos(self):
        incluida = self.ciudadano("Ana", manzana=self.manzana)
        otra = Manzana.objects.create(nombre="Manzana 5")
        self.ciudadano("Beto", manzana=otra)
        self.ciudadano("Carla")
        self.ciudadano("Diana", manzana=self.manzana, activo=False)
        junta = self.junta(alcance=Junta.Alcances.MANZANA, manzana=self.manzana)
        generar_participantes_junta(junta)
        self.assertEqual(list(junta.asistencias.values_list("ciudadano_id", flat=True)), [incluida.pk])

    def test_registros_bloquean_cambio_de_alcance_y_manzana_en_save(self):
        junta = self.junta()
        AsistenciaJunta.objects.create(junta=junta, ciudadano=self.ciudadano("Ana"))
        junta.alcance, junta.manzana = Junta.Alcances.MANZANA, self.manzana
        with self.assertRaises(ValidationError):
            junta.save()

    def test_formulario_conserva_manzana_historica_inactiva(self):
        junta = self.junta(alcance=Junta.Alcances.MANZANA, manzana=self.manzana)
        otra_inactiva = Manzana.objects.create(nombre="Inactiva ajena", activa=False)
        self.manzana.activa = False
        self.manzana.save()
        form = JuntaOperativaForm(instance=junta)
        ids = set(form.fields["manzana"].queryset.values_list("pk", flat=True))
        self.assertIn(self.manzana.pk, ids)
        self.assertNotIn(otra_inactiva.pk, ids)


class TerritorialInterfaceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operador", password="test")
        self.factory = RequestFactory()
        self.comite = Comite.objects.create(nombre="Comité interfaz")
        self.m4 = Manzana.objects.create(nombre="Manzana 4")
        self.m5 = Manzana.objects.create(nombre="Manzana 5")
        self.faena = Faena.objects.create(comite=self.comite, fecha=date.today(), descripcion="Faena cuatro", alcance=Faena.Alcances.MANZANA, manzana=self.m4)
        self.junta = Junta.objects.create(comite=self.comite, fecha=date.today(), tema="Junta cuatro", alcance=Junta.Alcances.MANZANA, manzana=self.m4)
        Junta.objects.create(comite=self.comite, fecha=date.today(), tema="Junta cinco", alcance=Junta.Alcances.MANZANA, manzana=self.m5)
        self.ciudadano = Ciudadano.objects.create(nombre="Ana", apellido_paterno="Pérez", edad=30, manzana=self.m4)
        RegistroFaena.objects.create(faena=self.faena, ciudadano=self.ciudadano)
        AsistenciaJunta.objects.create(junta=self.junta, ciudadano=self.ciudadano)

    def get_response(self, view, url, **kwargs):
        request = self.factory.get(url)
        request.user = self.user
        return view(request, **kwargs)

    def test_tarjetas_y_filtros_territoriales_uniformes(self):
        url = reverse("control_asistencias") + f"?alcance=MANZANA&manzana={self.m4.pk}"
        response = self.get_response(core_views.control_asistencias, url)
        self.assertContains(response, "Faena cuatro")
        self.assertContains(response, "Junta cuatro")
        self.assertNotContains(response, "Junta cinco")
        self.assertContains(response, "Manzana 4")
        self.assertContains(response, "Alcance")

    def test_csv_junta_incluye_contexto_legible(self):
        url = reverse("exportar_participantes_junta_csv", args=[self.junta.pk])
        response = self.get_response(core_views.exportar_participantes_junta_csv, url, junta_id=self.junta.pk)
        contenido = response.content.decode("utf-8-sig")
        self.assertIn("Alcance,Manzana", contenido)
        self.assertIn("Por manzana,Manzana 4", contenido)

    def test_detalle_y_capturas_muestran_manzana_de_junta_y_faena(self):
        cases = [
            (core_views.control_asistencias_junta_detalle, reverse("control_asistencias_junta_detalle", args=[self.junta.pk]), {"junta_id": self.junta.pk}),
            (core_views.captura_asistencia_junta, reverse("captura_asistencia_junta", args=[self.junta.pk]), {"junta_id": self.junta.pk}),
            (core_views.captura_asistencia_secuencial_junta, reverse("captura_asistencia_secuencial_junta", args=[self.junta.pk]), {"junta_id": self.junta.pk}),
            (core_views.captura_asistencia_faena, reverse("captura_asistencia_faena", args=[self.faena.pk]), {"faena_id": self.faena.pk}),
            (core_views.captura_asistencia_secuencial_faena, reverse("captura_asistencia_secuencial_faena", args=[self.faena.pk]), {"faena_id": self.faena.pk}),
        ]
        for view, url, kwargs in cases:
            with self.subTest(url=url):
                self.assertContains(self.get_response(view, url, **kwargs), "Manzana 4")
