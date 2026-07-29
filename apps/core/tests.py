import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from apps.comites.models import Comite
from apps.core.models import Ciudadano, Manzana
from apps.core.views import _ciudadanos_operativos_queryset, _filtrar_ciudadanos_operativos
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


class ExportacionCiudadanosCsvTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="padron", password="testpass123")
        self.client.force_login(self.user)
        self.ana = Ciudadano.objects.create(
            nombre="Ana María",
            apellido_paterno="García",
            apellido_materno="Ñúñez",
            edad=30,
            numero_contrato=None,
            activo=True,
        )
        self.beto = Ciudadano.objects.create(
            nombre="Beto",
            apellido_paterno="Pérez",
            apellido_materno="López",
            edad=40,
            numero_contrato="CT-00555",
            activo=False,
        )
        self.maria = Ciudadano.objects.create(
            nombre="María",
            apellido_paterno="Zapata",
            apellido_materno="Soto",
            edad=28,
            activo=True,
        )

    def _rows(self, response):
        content = response.content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(content)))

    def test_template_tiene_boton_csv_y_no_pdf(self):
        template = Path("templates/dashboard/padron_ciudadanos.html").read_text()

        self.assertIn("Exportar CSV", template)
        self.assertIn("exportar_ciudadanos_url", template)
        self.assertIn("exportar_ciudadanos_querystring", template)
        self.assertNotIn("Exportar PDF", template)
        self.assertNotIn("Descargar padrón activo PDF", template)

    def test_exporta_csv_con_bom_fecha_estado_legible_filtros_y_sin_paginar(self):
        response = self.client.get(reverse("exportar_ciudadanos_csv"), {"q": "Ana María", "estado": "activos", "page": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(f'filename="ciudadanos_{timezone.localdate().isoformat()}.csv"', response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        rows = self._rows(response)
        self.assertEqual(rows[0], ["ID", "Nombre", "Apellido paterno", "Apellido materno", "Nombre completo", "No. de contrato", "Manzana", "Edad", "Estado", "Fecha de registro"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1:9], ["Ana María", "García", "Ñúñez", "Ana María García Ñúñez", "", "", "30", "Activo"])
        self.assertNotIn("Beto Pérez López", response.content.decode("utf-8-sig"))

    def test_exporta_inactivos_como_inactivo_y_requiere_autenticacion(self):
        response = self.client.get(reverse("exportar_ciudadanos_csv"), {"estado": "inactivos"})
        rows = self._rows(response)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1:9], ["Beto", "Pérez", "López", "Beto Pérez López", "CT-00555", "", "40", "Inactivo"])

    def test_busca_por_contrato_y_filtra_por_manzana(self):
        centro = Manzana.objects.create(nombre="Centro")
        self.beto.manzana = centro
        self.beto.save(update_fields=["manzana"])

        ciudadanos = _filtrar_ciudadanos_operativos(
            _ciudadanos_operativos_queryset(),
            {"q": "CT-00555", "manzana": str(centro.pk)},
        )

        self.assertEqual(list(ciudadanos), [self.beto])
        template = Path("templates/dashboard/padron_ciudadanos.html").read_text()
        self.assertIn("c.numero_contrato", template)
        self.assertIn("c.manzana", template)

        self.client.logout()
        response = self.client.get(reverse("exportar_ciudadanos_csv"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])


class OperationalEventCreationViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operadora", password="testpass123")
        self.client.force_login(self.user)
        self.comite = Comite.objects.create(nombre="Comité Operativo", tipo=Comite.Tipos.DELEGACION)

    def test_abre_y_crea_faena_operativa_con_flujo_compartido(self):
        response = self.client.get(reverse("crear_faena_operativa"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Crear nueva faena")

        response = self.client.post(
            reverse("crear_faena_operativa"),
            {
                "comite": self.comite.pk,
                "fecha": "2026-07-20",
                "descripcion": "Limpieza del parque",
                "estado": Faena.Estados.PROGRAMADA,
                "notas": "Traer herramientas",
            },
        )

        faena = Faena.objects.get(descripcion="Limpieza del parque")
        self.assertRedirects(response, reverse("control_asistencias_faena_detalle", args=[faena.pk]))
        self.assertEqual(faena.comite, self.comite)
        self.assertEqual(faena.notas, "Traer herramientas")

    def test_abre_y_crea_junta_operativa_con_flujo_compartido(self):
        response = self.client.get(reverse("crear_junta_operativa"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Crear nueva junta")

        response = self.client.post(
            reverse("crear_junta_operativa"),
            {
                "comite": self.comite.pk,
                "fecha": "2026-07-21",
                "tipo": Junta.Tipos.ORDINARIA,
                "lugar": "Salón comunitario",
                "tema": "Seguimiento operativo",
                "estado": Junta.Estados.PROGRAMADA,
                "notas": "Confirmar asistencia",
            },
        )

        junta = Junta.objects.get(tema="Seguimiento operativo")
        self.assertRedirects(response, reverse("control_asistencias_junta_detalle", args=[junta.pk]))
        self.assertEqual(junta.comite, self.comite)
        self.assertEqual(junta.estado, Junta.Estados.PROGRAMADA)


class CapturaPresencialUltimoPendienteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="capturista", password="testpass123")
        self.client.force_login(self.user)
        self.comite = Comite.objects.create(nombre="Comité Captura", tipo=Comite.Tipos.DELEGACION)
        self.ana = Ciudadano.objects.create(nombre="Ana", apellido_paterno="García", apellido_materno="Ruiz", edad=30)
        self.juan = Ciudadano.objects.create(nombre="Juan", apellido_paterno="Pérez", apellido_materno="López", edad=31)
        self.pedro = Ciudadano.objects.create(nombre="Pedro", apellido_paterno="Martínez", apellido_materno="Soto", edad=32)

    def test_faena_presencial_rechaza_solicitud_manual_del_ultimo_pendiente(self):
        faena = Faena.objects.create(comite=self.comite, fecha=date(2026, 7, 20), descripcion="Limpieza")
        registro = RegistroFaena.objects.create(faena=faena, ciudadano=self.ana, estatus=RegistroFaena.Estatus.PENDIENTE)

        response = self.client.post(
            reverse("captura_asistencia_secuencial_faena", args=[faena.pk]),
            {"action": "asistio", "record_id": registro.pk},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        registro.refresh_from_db()
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["ok"])
        self.assertTrue(response.json()["requires_normal_capture"])
        self.assertEqual(response.json()["normal_capture_url"], reverse("captura_asistencia_faena", args=[faena.pk]))
        self.assertEqual(registro.estatus, RegistroFaena.Estatus.PENDIENTE)

    def test_junta_presencial_permite_marcar_uno_de_dos_y_envia_a_captura_normal(self):
        junta = Junta.objects.create(comite=self.comite, fecha=date(2026, 7, 20), tema="Asamblea")
        primero = AsistenciaJunta.objects.create(junta=junta, ciudadano=self.ana, estatus=AsistenciaJunta.Estatus.PENDIENTE)
        ultimo = AsistenciaJunta.objects.create(junta=junta, ciudadano=self.juan, estatus=AsistenciaJunta.Estatus.PENDIENTE)

        response = self.client.post(
            reverse("captura_asistencia_secuencial_junta", args=[junta.pk]),
            {"action": "falto", "record_id": primero.pk},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        primero.refresh_from_db()
        ultimo.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(primero.estatus, AsistenciaJunta.Estatus.FALTO)
        self.assertFalse(primero.asistio)
        self.assertEqual(ultimo.estatus, AsistenciaJunta.Estatus.PENDIENTE)
        data = response.json()
        self.assertTrue(data["requires_normal_capture"])
        self.assertIsNone(data["next_record"])
        self.assertEqual(data["metrics"]["pendientes"], 1)

    def test_faena_presencial_con_tres_pendientes_avanza_normalmente(self):
        faena = Faena.objects.create(comite=self.comite, fecha=date(2026, 7, 20), descripcion="Limpieza")
        primero = RegistroFaena.objects.create(faena=faena, ciudadano=self.ana, estatus=RegistroFaena.Estatus.PENDIENTE)
        RegistroFaena.objects.create(faena=faena, ciudadano=self.juan, estatus=RegistroFaena.Estatus.PENDIENTE)
        RegistroFaena.objects.create(faena=faena, ciudadano=self.pedro, estatus=RegistroFaena.Estatus.PENDIENTE)

        response = self.client.post(
            reverse("captura_asistencia_secuencial_faena", args=[faena.pk]),
            {"action": "asistio", "record_id": primero.pk},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        primero.refresh_from_db()
        data = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(primero.estatus, RegistroFaena.Estatus.ASISTIO)
        self.assertFalse(data["requires_normal_capture"])
        self.assertIsNotNone(data["next_record"])
        self.assertEqual(data["metrics"]["pendientes"], 2)

from django.contrib.auth.models import Permission
from apps.tesoreria.models import Abono, ConceptoTesoreria, ObligacionCiudadano


class SecureDeletionFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="deleter", password="pw")
        perms = Permission.objects.filter(codename__in=["delete_faena", "delete_junta", "delete_conceptotesoreria", "add_conceptotesoreria", "change_conceptotesoreria"])
        self.user.user_permissions.set(perms)
        self.client.force_login(self.user)
        self.comite = Comite.objects.create(nombre="Comité Eliminación", tipo=Comite.Tipos.DELEGACION)
        self.ana = Ciudadano.objects.create(nombre="Ana", apellido_paterno="López", edad=30)
        self.beto = Ciudadano.objects.create(nombre="Beto", apellido_paterno="Pérez", edad=31)

    def test_delete_buttons_visibility_only_on_edit_with_permission(self):
        faena = Faena.objects.create(comite=self.comite, fecha=date(2026, 7, 20), descripcion="Limpieza")
        junta = Junta.objects.create(comite=self.comite, fecha=date(2026, 7, 21), tema="Asamblea")
        concepto = ConceptoTesoreria.objects.create(naturaleza=ConceptoTesoreria.Naturalezas.PAGO, comite=self.comite, concepto="Cuota", monto_individual=Decimal("100.00"), fecha=date(2026, 7, 22))
        self.assertNotContains(self.client.get(reverse("crear_faena_operativa")), "Eliminar faena")
        self.assertContains(self.client.get(reverse("editar_faena_operativa", args=[faena.pk])), reverse("eliminar_faena_operativa", args=[faena.pk]))
        self.assertContains(self.client.get(reverse("editar_junta_operativa", args=[junta.pk])), reverse("eliminar_junta_operativa", args=[junta.pk]))
        self.assertContains(self.client.get(reverse("editar_concepto_tesoreria", args=[concepto.pk])), "Eliminar concepto")
        self.assertNotContains(self.client.get(reverse("crear_concepto_tesoreria")), "Eliminar concepto")
        limited = get_user_model().objects.create_user(username="limited", password="pw")
        limited.user_permissions.set(Permission.objects.filter(codename__in=["add_conceptotesoreria", "change_conceptotesoreria"]))
        self.client.force_login(limited)
        self.assertNotContains(self.client.get(reverse("editar_faena_operativa", args=[faena.pk])), "Eliminar faena")
        self.assertNotContains(self.client.get(reverse("editar_concepto_tesoreria", args=[concepto.pk])), "Eliminar concepto")

    def test_faena_get_confirms_post_deletes_records_and_redirects(self):
        faena = Faena.objects.create(comite=self.comite, fecha=date(2026, 7, 20), descripcion="Limpieza")
        RegistroFaena.objects.create(faena=faena, ciudadano=self.ana, estatus=RegistroFaena.Estatus.PENDIENTE)
        RegistroFaena.objects.create(faena=faena, ciudadano=self.beto, estatus=RegistroFaena.Estatus.FALTO, genera_adeudo=True, monto_adeudo=Decimal("50.00"))
        url = reverse("eliminar_faena_operativa", args=[faena.pk])
        response = self.client.get(url)
        self.assertContains(response, "Acción irreversible")
        self.assertContains(response, "Total de registros generados")
        self.assertContains(response, "$50.00")
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertTrue(Faena.objects.filter(pk=faena.pk).exists())
        response = self.client.post(url)
        self.assertRedirects(response, reverse("control_asistencias"), fetch_redirect_response=False)
        self.assertFalse(Faena.objects.filter(pk=faena.pk).exists())
        self.assertFalse(RegistroFaena.objects.filter(faena_id=faena.pk).exists())

    def test_junta_get_confirms_post_deletes_asistencias_and_redirects(self):
        junta = Junta.objects.create(comite=self.comite, fecha=date(2026, 7, 21), tema="Asamblea")
        AsistenciaJunta.objects.create(junta=junta, ciudadano=self.ana, estatus=AsistenciaJunta.Estatus.PENDIENTE)
        AsistenciaJunta.objects.create(junta=junta, ciudadano=self.beto, estatus=AsistenciaJunta.Estatus.ASISTIO, genera_adeudo=True, monto_adeudo=Decimal("25.00"))
        url = reverse("eliminar_junta_operativa", args=[junta.pk])
        response = self.client.get(url)
        self.assertContains(response, "Total de asistencias generadas")
        self.assertContains(response, "$25.00")
        response = self.client.post(url)
        self.assertRedirects(response, reverse("control_asistencias"), fetch_redirect_response=False)
        self.assertFalse(Junta.objects.filter(pk=junta.pk).exists())
        self.assertFalse(AsistenciaJunta.objects.filter(junta_id=junta.pk).exists())

    def test_post_without_auth_or_permission_does_not_delete(self):
        faena = Faena.objects.create(comite=self.comite, fecha=date(2026, 7, 20), descripcion="Limpieza")
        url = reverse("eliminar_faena_operativa", args=[faena.pk])
        self.client.logout()
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertTrue(Faena.objects.filter(pk=faena.pk).exists())
        self.client.force_login(get_user_model().objects.create_user(username="noperm", password="pw"))
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertTrue(Faena.objects.filter(pk=faena.pk).exists())

    def test_concepto_deletes_obligaciones_and_abonos_with_exact_total(self):
        concepto = ConceptoTesoreria.objects.create(naturaleza=ConceptoTesoreria.Naturalezas.COOPERACION, comite=self.comite, concepto="Cooperación", monto_individual=Decimal("100.00"), fecha=date(2026, 7, 22))
        o1 = ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=self.ana, monto_asignado=Decimal("100.00"))
        o2 = ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=self.beto, monto_asignado=Decimal("100.00"), estado=ObligacionCiudadano.Estados.PAGADO)
        Abono.objects.create(obligacion=o1, monto=Decimal("10.00"), fecha=date(2026, 7, 22))
        Abono.objects.create(obligacion=o2, monto=Decimal("10.00"), fecha=date(2026, 7, 22))
        url = reverse("eliminar_concepto_tesoreria", args=[concepto.pk])
        response = self.client.get(url)
        self.assertContains(response, "Cantidad de obligaciones")
        self.assertContains(response, "Cantidad de abonos")
        self.assertContains(response, "$20.00")
        response = self.client.post(url)
        self.assertRedirects(response, reverse("tesoreria_operativa"), fetch_redirect_response=False)
        self.assertFalse(ConceptoTesoreria.objects.filter(pk=concepto.pk).exists())
        self.assertFalse(ObligacionCiudadano.objects.filter(concepto_id=concepto.pk).exists())
        self.assertFalse(Abono.objects.filter(obligacion_id__in=[o1.pk, o2.pk]).exists())

    def test_superuser_can_delete_concepto_without_explicit_permission(self):
        superuser = get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")
        concepto = ConceptoTesoreria.objects.create(naturaleza=ConceptoTesoreria.Naturalezas.PAGO, comite=self.comite, concepto="Super", monto_individual=Decimal("100.00"), fecha=date(2026, 7, 22))
        self.client.force_login(superuser)
        response = self.client.post(reverse("eliminar_concepto_tesoreria", args=[concepto.pk]))
        self.assertRedirects(response, reverse("tesoreria_operativa"), fetch_redirect_response=False)
        self.assertFalse(ConceptoTesoreria.objects.filter(pk=concepto.pk).exists())
