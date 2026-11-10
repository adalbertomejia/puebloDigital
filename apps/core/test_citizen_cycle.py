from apps.comites.test_helpers import asignar_cargo
from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse
from apps.comites.models import Comite, UsuarioApp
from apps.operacion.models import Faena, Junta, RegistroFaena, AsistenciaJunta
from apps.tesoreria.models import (
    ConceptoTesoreria,
    ObligacionCiudadano,
    Pago,
    Cooperacion,
)
from apps.agua.models import Toma
from .models import Ciudadano, Manzana
from .forms import CiudadanoOperativoForm


class CitizenCycleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            "root", "r@example.com", "pw"
        )
        self.client.force_login(self.user)
        self.a = Manzana.objects.create(nombre="Uno")
        self.b = Manzana.objects.create(nombre="Dos")
        self.c = Ciudadano.objects.create(
            nombre="Ana María",
            apellido_paterno="García",
            apellido_materno="López",
            edad=32,
            manzana=self.a,
        )
        self.other = Ciudadano.objects.create(
            nombre="Beatriz", apellido_paterno="Privada", edad=50, manzana=self.b
        )
        self.comite = Comite.objects.create(nombre="Delegación", tipo="DELEGACION")
        self.otro_comite = Comite.objects.create(nombre="Agua", tipo="AGUA")
        self.event = Faena.objects.create(
            comite=self.comite, fecha=date(2026, 1, 2), descripcion="Limpieza"
        )
        self.data = {
            "nombre": "Ana María",
            "apellido_paterno": "García",
            "apellido_materno": "López",
            "edad": 32,
            "manzana": self.b.pk,
            "sexo": "NO_ESPECIFICADO",
        }

    def url(self, name="perfil_ciudadano", citizen=None):
        return reverse(name, args=[(citizen or self.c).pk])

    def submit(self, name, data=None, citizen=None):
        url = self.url(name, citizen)
        response = self.client.get(url)
        payload = dict(data or {}, operation_token=response.context["operation_token"])
        return self.client.post(url, payload)

    def staff(self, perms=()):
        user = get_user_model().objects.create_user("secretary", password="pw")
        asignar_cargo(user=user, comite=self.comite, rol="SECRETARIO")
        user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="core", codename__in=perms
            )
        )
        self.client.force_login(user)
        return user

    def attendance(self, **kwargs):
        return RegistroFaena.objects.create(
            ciudadano=self.c, faena=self.event, **kwargs
        )

    def test_profile_counts_juntas_and_excludes_cancelled(self):
        self.attendance(estatus="FALTO", genera_adeudo=False)
        junta = Junta.objects.create(
            comite=self.comite, fecha=date(2026, 1, 3), tema="Asamblea"
        )
        AsistenciaJunta.objects.create(
            ciudadano=self.c, junta=junta, estatus="JUSTIFICADO"
        )
        response = self.client.get(self.url())
        self.assertEqual(response.context["resumen"]["faltas"], 1)
        self.assertEqual(response.context["resumen"]["adeudos_asistencia"], 0)
        self.assertEqual(response.context["resumen"]["justificaciones"], 1)
        self.event.estado = "CANCELADA"
        self.event.save()
        self.assertEqual(self.client.get(self.url()).context["resumen"]["faltas"], 0)

    def test_profile_isolates_citizen_and_filters(self):
        self.attendance(estatus="FALTO")
        response = self.client.get(self.url(), {"tipo": "Junta"})
        self.assertContains(response, "Sin resultados para estos filtros")
        self.assertNotContains(response, self.other.nombre_completo)
        self.assertContains(
            self.client.get(self.url(citizen=self.other)),
            "Sin registros de asistencia.",
        )
        response = self.client.get(self.url(), {"desde": "2026-02-01"})
        self.assertEqual(response.context["asistencias_page"].paginator.count, 0)

    def test_unknown_amount_not_rendered_as_zero(self):
        self.attendance()
        row = self.client.get(self.url()).context["asistencias_page"][0]
        self.assertFalse(row["genera_adeudo"])

    def test_pagination_stable_and_filters_preserved(self):
        for i in range(24):
            event = Faena.objects.create(
                comite=self.comite, fecha=date(2026, 2, 1), descripcion=f"Trabajo {i}"
            )
            RegistroFaena.objects.create(faena=event, ciudadano=self.c)
        response = self.client.get(
            self.url(), {"tipo": "Faena", "asistencias_page": "3"}
        )
        self.assertEqual(len(response.context["asistencias_page"]), 4)
        self.assertIn(
            "tipo=Faena", response.context["asistencias_page"].previous_querystring
        )

    def test_edit_moves_territory_without_changing_history(self):
        record = self.attendance()
        self.submit("editar_ciudadano_operativo", self.data)
        self.c.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(self.c.manzana, self.b)
        self.assertEqual(record.faena.comite, self.comite)
        self.assertEqual(record.ciudadano_id, self.c.pk)

    def test_deactivate_reactivate_audit_and_repeat_post(self):
        self.attendance()
        url = self.url("estado_ciudadano")
        token = self.client.get(url).context["operation_token"]
        payload = {
            "operation_token": token,
            "fecha": "2026-01-10",
            "motivo": "Cambio de residencia",
            "activo_anterior": "True",
        }
        self.client.post(url, payload)
        self.client.post(url, payload)
        self.c.refresh_from_db()
        self.assertFalse(self.c.activo)
        self.assertEqual(self.c.motivo_baja, "Cambio de residencia")
        self.assertEqual(self.c.cambios_estado.count(), 1)
        self.assertEqual(self.c.registros_faena.count(), 1)
        self.submit(
            "estado_ciudadano",
            {"fecha": "2026-01-11", "motivo": "Regresó", "activo_anterior": "False"},
        )
        self.c.refresh_from_db()
        self.assertTrue(self.c.activo)
        self.assertEqual(self.c.cambios_estado.count(), 2)
        self.assertEqual(self.c.cambios_estado.latest("pk").usuario, self.user)

    def test_state_requires_reason_and_valid_date(self):
        response = self.submit(
            "estado_ciudadano",
            {"fecha": "2099-01-01", "motivo": "", "activo_anterior": "True"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("motivo", response.context["form"].errors)
        self.assertIn("fecha", response.context["form"].errors)
        self.c.refresh_from_db()
        self.assertTrue(self.c.activo)

    def test_duplicate_names_normalize_accents_spaces_and_typo(self):
        for name in [" ana   maria ", "Ana Maria", "Ana Marìa", "Ana Mari"]:
            data = dict(self.data, nombre=name)
            form = CiudadanoOperativoForm(data)
            self.assertFalse(form.is_valid(), name)
            self.assertIn("confirmar_duplicado", form.errors)
        form = CiudadanoOperativoForm(dict(self.data, confirmar_duplicado="on"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_duplicate_warning_before_save_and_repeated_create(self):
        url = reverse("crear_ciudadano_operativo")
        token = self.client.get(url).context["operation_token"]
        response = self.client.post(url, dict(self.data, operation_token=token))
        self.assertContains(response, "Posibles duplicados")
        self.assertEqual(Ciudadano.objects.count(), 2)
        payload = dict(
            self.data,
            confirmar_duplicado="on",
            operation_token=response.context["operation_token"],
        )
        self.client.post(url, payload)
        self.client.post(url, payload)
        self.assertEqual(Ciudadano.objects.count(), 3)

    def test_delete_requires_confirmation_post(self):
        response = self.client.get(self.url("eliminar_ciudadano"))
        self.assertContains(response, self.c.nombre_completo)
        self.assertTrue(Ciudadano.objects.filter(pk=self.c.pk).exists())
        self.submit("eliminar_ciudadano")
        self.assertFalse(Ciudadano.objects.filter(pk=self.c.pk).exists())

    def test_delete_with_attendance_is_blocked_in_view_and_orm(self):
        self.attendance()
        self.assertContains(
            self.client.get(self.url("eliminar_ciudadano")), "Eliminación bloqueada"
        )
        self.submit("eliminar_ciudadano")
        self.assertTrue(Ciudadano.objects.filter(pk=self.c.pk).exists())
        with self.assertRaises(ProtectedError):
            self.c.delete()

    def test_delete_checks_relationships_created_after_confirmation(self):
        url = self.url("eliminar_ciudadano")
        token = self.client.get(url).context["operation_token"]
        self.attendance()
        self.client.post(url, {"operation_token": token})
        self.assertTrue(Ciudadano.objects.filter(pk=self.c.pk).exists())

    def test_delete_protects_payment_water_obligation_and_access(self):
        creators = [
            lambda: Pago.objects.create(
                ciudadano=self.c,
                comite=self.comite,
                monto=10,
                fecha=date(2026, 1, 1),
                concepto="Pago",
            ),
            lambda: Cooperacion.objects.create(
                ciudadano=self.c,
                comite=self.comite,
                monto=10,
                fecha=date(2026, 1, 1),
                concepto="Coop",
            ),
            lambda: Toma.objects.create(ciudadano=self.c, numero_toma="10"),
        ]
        for create in creators:
            obj = create()
            with self.assertRaises(ProtectedError):
                self.c.delete()
            obj.delete()
        asignar_cargo(
            user=self.user, ciudadano=self.c, comite=self.comite, rol="LECTURA"
        )
        self.submit("eliminar_ciudadano")
        self.assertTrue(Ciudadano.objects.filter(pk=self.c.pk).exists())

    def test_administrador_global_necesita_permiso_explicito_de_eliminacion(self):
        user=get_user_model().objects.create_user('admin-operativo',is_staff=True)
        user.user_permissions.set(Permission.objects.filter(content_type__app_label='core',codename__in=['view_ciudadano','change_ciudadano']))
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url('eliminar_ciudadano')).status_code,404)
        user.user_permissions.add(Permission.objects.get(content_type__app_label='core',codename='delete_ciudadano'))
        self.assertEqual(self.client.get(self.url('eliminar_ciudadano')).status_code,200)

    def test_no_permission_cannot_create_or_change(self):
        self.staff(["view_ciudadano"])
        self.assertEqual(
            self.client.post(
                self.url("editar_ciudadano_operativo"), self.data
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(self.url("estado_ciudadano"), {}).status_code, 404
        )
        self.assertEqual(
            self.client.get(reverse("crear_ciudadano_operativo")).status_code, 404
        )

    def test_committee_membership_does_not_grant_global_access(self):
        self.attendance()
        user = get_user_model().objects.create_user("committee")
        asignar_cargo(user=user, comite=self.otro_comite, rol="SECRETARIO")
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core", codename="change_ciudadano"
            )
        )
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard_operativo"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.other.nombre_completo)
        self.assertEqual(response.context["metricas"]["total_ciudadanos"], 0)
        for name in ["control_agua", "tesoreria_operativa", "exportar_ciudadanos_csv"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 404, name)
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.assertEqual(
            self.client.get(self.url("eliminar_ciudadano")).status_code, 404
        )
        self.assertEqual(
            self.client.get(self.url("editar_ciudadano_operativo")).status_code, 404
        )

    def test_territorial_access_and_counters(self):
        from apps.comites.models import PerfilAcceso

        user = get_user_model().objects.create_user("territory")
        self.a.responsable = self.c
        self.a.save()
        PerfilAcceso.objects.create(user=user, ciudadano=self.c)
        self.attendance()
        private = Faena.objects.create(
            comite=self.comite,
            fecha=date(2026, 1, 4),
            descripcion="Historial de otra manzana",
            alcance="MANZANA",
            manzana=self.b,
        )
        RegistroFaena.objects.create(
            faena=private,
            ciudadano=self.c,
            estatus="FALTO",
            genera_adeudo=True,
            monto_adeudo=100,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("padron_ciudadanos"))
        self.assertEqual(response.context["metricas"]["total"], 1)
        self.assertEqual(response.context["metricas"]["con_adeudo"], 0)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Historial de otra manzana")
        self.assertEqual(response.context["resumen"]["faltas"], 0)
        self.assertEqual(self.client.get(self.url(citizen=self.other)).status_code, 404)
        self.assertEqual(
            self.client.get(self.url("editar_ciudadano_operativo")).status_code, 404
        )

    def test_inactive_committee_profile_cannot_read(self):
        user = get_user_model().objects.create_user("inactive")
        asignar_cargo(
            user=user, comite=self.comite, rol="LECTURA", activo=False
        )
        self.attendance()
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_cancelled_obligations_excluded_and_abonos_refresh(self):
        concept = ConceptoTesoreria.objects.create(
            comite=self.comite,
            naturaleza="PAGO",
            concepto="Cuota",
            monto_individual=100,
            fecha=date(2026, 1, 1),
        )
        obligation = ObligacionCiudadano.objects.create(
            ciudadano=self.c, concepto=concept, monto_asignado=100
        )
        self.assertEqual(
            self.client.get(self.url()).context["resumen"]["saldo_pendiente"],
            Decimal("100"),
        )
        obligation.acreditar(40)
        self.assertEqual(
            self.client.get(self.url()).context["resumen"]["saldo_pendiente"],
            Decimal("60"),
        )
        obligation.estado = "CANCELADO"
        obligation.save()
        response = self.client.get(self.url())
        self.assertEqual(response.context["resumen"]["saldo_pendiente"], Decimal("0"))
        self.assertEqual(response.context["resumen"]["total_abonado"], Decimal("0"))
        self.assertEqual(
            response.context["abonos_page"][0].obligacion.estado, "CANCELADO"
        )
        self.submit("eliminar_ciudadano")
        self.assertTrue(Ciudadano.objects.filter(pk=self.c.pk).exists())

    def test_cargo_obsoleto_no_obtiene_padron_ni_finanzas(self):
        self.staff(['view_ciudadano'])
        self.assertEqual(self.client.get(self.url()).status_code,404)
        self.assertEqual(self.client.get(reverse('tesoreria_operativa')).status_code,404)

    def test_return_navigation_and_external_redirect_rejected(self):
        volver = reverse("padron_ciudadanos") + "?q=Ana&estado=activos&page=2"
        response = self.client.get(self.url(), {"return_to": volver})
        self.assertEqual(response.context["return_to"], volver)
        self.assertEqual(
            self.client.get(self.url(), {"return_to": "https://evil.test/"}).context[
                "return_to"
            ],
            reverse("padron_ciudadanos"),
        )

    def test_csv_uses_same_filters_as_list(self):
        response = self.client.get(
            reverse("exportar_ciudadanos_csv"),
            {"manzana": self.a.pk, "estado": "activos"},
        )
        self.assertContains(response, self.c.nombre_completo)
        self.assertNotContains(response, self.other.nombre_completo)

    def test_csrf_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for name in [
            "eliminar_ciudadano",
            "estado_ciudadano",
            "editar_ciudadano_operativo",
        ]:
            self.assertEqual(client.post(self.url(name), {}).status_code, 403)

    def test_invalid_history_dates_show_errors_without_old_results(self):
        self.attendance()
        for filters in [
            {"desde": "2026-99-99"},
            {"desde": "2026-02-01", "hasta": "2026-01-01"},
        ]:
            response = self.client.get(self.url(), filters)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["filtros_historial"].errors)
            self.assertEqual(response.context["asistencias_page"].paginator.count, 0)

    def test_central_profile_without_view_permission_cannot_read(self):
        self.staff([])
        self.attendance()
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.assertEqual(
            self.client.get(self.url("editar_ciudadano_operativo")).status_code, 404
        )

    def test_post_without_operation_token_does_not_save(self):
        response = self.client.post(self.url("editar_ciudadano_operativo"), self.data)
        self.assertEqual(response.status_code, 302)
        self.c.refresh_from_db()
        self.assertEqual(self.c.manzana, self.a)

    def test_changing_manzana_keeps_obligations_and_payments(self):
        concept = ConceptoTesoreria.objects.create(
            comite=self.comite,
            naturaleza="PAGO",
            concepto="Anterior",
            monto_individual=100,
        )
        obligation = ObligacionCiudadano.objects.create(
            ciudadano=self.c, concepto=concept, monto_asignado=100
        )
        obligation.acreditar(25)
        self.submit("editar_ciudadano_operativo", self.data)
        obligation.refresh_from_db()
        self.assertEqual(obligation.ciudadano_id, self.c.pk)
        self.assertEqual(obligation.concepto.comite_id, self.comite.pk)
        self.assertEqual(obligation.saldo_pendiente, Decimal("75"))

    def test_committee_member_with_delete_permission_cannot_delete(self):
        user = get_user_model().objects.create_user("committee-delete")
        asignar_cargo(user=user, comite=self.otro_comite, rol="SECRETARIO")
        user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="core",
                codename__in=["view_ciudadano", "delete_ciudadano"],
            )
        )
        self.client.force_login(user)
        self.assertEqual(
            self.client.get(self.url("eliminar_ciudadano")).status_code, 404
        )
        self.assertEqual(
            self.client.post(self.url("eliminar_ciudadano"), {}).status_code, 404
        )
        self.assertTrue(Ciudadano.objects.filter(pk=self.c.pk).exists())

    def test_territorial_list_does_not_expose_payment_date(self):
        from apps.comites.models import PerfilAcceso

        user = get_user_model().objects.create_user("reader-block")
        self.a.responsable = self.c
        self.a.save()
        PerfilAcceso.objects.create(user=user, ciudadano=self.c)
        Pago.objects.create(
            ciudadano=self.c,
            comite=self.comite,
            concepto="Dato financiero",
            monto=10,
            fecha=date(2026, 1, 5),
        )
        self.client.force_login(user)
        response = self.client.get(reverse("padron_ciudadanos"))
        self.assertIsNone(response.context["ciudadanos"][0].ultimo_pago_fecha)
        self.assertNotContains(self.client.get(self.url()), "Dato financiero")

    def test_registered_payments_are_visible_with_explicit_permission(self):
        Pago.objects.create(
            ciudadano=self.c,
            comite=self.comite,
            concepto="Pago histórico",
            monto=10,
            fecha=date(2026, 1, 5),
        )
        response = self.client.get(self.url(), {"tipo": "Pago"})
        self.assertContains(response, "Pago histórico")
        self.assertEqual(response.context["movimientos_page"].paginator.count, 1)
        self.assertEqual(response.context["resumen"]["saldo_pendiente"], 0)


from copy import copy
from django.db import connection
from django.test import TransactionTestCase
from .expediente import obtener_resumen_ciudadano


class LegacyUnknownAmountTests(TransactionTestCase):
    """Reproduce nullable historical money without changing the production model."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            "legacy", "legacy@example.com", "pw"
        )
        self.ciudadano = Ciudadano.objects.create(
            nombre="Importe", apellido_paterno="Histórico"
        )
        comite = Comite.objects.create(nombre="Comité")
        concepto = ConceptoTesoreria.objects.create(
            comite=comite, naturaleza="PAGO", concepto="Anterior", monto_individual=100
        )
        self.obligacion = ObligacionCiudadano.objects.create(
            ciudadano=self.ciudadano, concepto=concepto, monto_asignado=100
        )

    def comprobar_importe_desconocido(self, model, field_name, obj, expected_key):
        original = model._meta.get_field(field_name)
        nullable = copy(original)
        nullable.null = True
        with connection.schema_editor() as schema:
            schema.alter_field(model, original, nullable)
        try:
            model.objects.filter(pk=obj.pk).update(**{field_name: None})
            resumen = obtener_resumen_ciudadano(self.ciudadano, usuario=self.user)
            self.assertIsNone(resumen["saldo_pendiente"])
            self.assertIsNone(resumen[expected_key])
            self.client.force_login(self.user)
            response = self.client.get(
                reverse("perfil_ciudadano", args=[self.ciudadano.pk])
            )
            self.assertContains(response, "Por revisar")
            self.assertContains(
                response,
                "Desconocido" if expected_key == "asignado" else "Importe desconocido",
            )
        finally:
            model.objects.filter(pk=obj.pk).update(**{field_name: Decimal("100")})
            with connection.schema_editor() as schema:
                schema.alter_field(model, nullable, original)

    def test_unknown_assigned_amount_does_not_become_zero(self):
        self.comprobar_importe_desconocido(
            ObligacionCiudadano, "monto_asignado", self.obligacion, "asignado"
        )

    def test_unknown_payment_does_not_become_zero(self):
        abono = self.obligacion.acreditar(20)
        self.comprobar_importe_desconocido(type(abono), "monto", abono, "total_abonado")
