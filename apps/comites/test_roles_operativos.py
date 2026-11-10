import io
import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Ciudadano, Manzana
from apps.operacion.models import Faena, Junta, RegistroFaena, AsistenciaJunta
from apps.tesoreria.models import (
    ConceptoTesoreria,
    ObligacionCiudadano,
    Abono,
    RegistroFinanciero,
)
from apps.tesoreria.autorizacion import comites_financieros, puede_operar_finanzas
from apps.comites.models import Comite, PerfilAcceso, UsuarioApp
from apps.comites.test_helpers import asignar_cargo
from apps.comites.migrations._auditoria_cargos_v1 import evaluar


class RolesOperativosTests(TestCase):
    def setUp(self):
        self.a = Comite.objects.create(nombre="Agua autorizada", tipo="AGUA")
        self.b = Comite.objects.create(nombre="Feria reservada", tipo="FERIA")
        self.presidente, self.cargo_p = self.actor("presidente", "PRESIDENTE")
        self.tesorero, self.cargo_t = self.actor("tesorero", "TESORERO")
        self.lector, self.cargo_l = self.actor("lector", "LECTURA")
        self.ciudadano = Ciudadano.objects.create(
            nombre="Ana", apellido_paterno="Ciudadana", numero_contrato="A-001"
        )
        self.otro = Ciudadano.objects.create(
            nombre="Pedro", apellido_paterno="Participante"
        )
        self.concepto = ConceptoTesoreria.objects.create(
            comite=self.a,
            naturaleza="PAGO",
            concepto="Aportación propia",
            monto_individual=100,
        )
        self.ajeno = ConceptoTesoreria.objects.create(
            comite=self.b,
            naturaleza="PAGO",
            concepto="Importe ajeno reservado",
            monto_individual=900,
        )
        self.obligacion = ObligacionCiudadano.objects.create(
            concepto=self.concepto, ciudadano=self.ciudadano, monto_asignado=100
        )
        self.obligacion_b = ObligacionCiudadano.objects.create(
            concepto=self.ajeno, ciudadano=self.ciudadano, monto_asignado=900
        )
        self.abono = self.obligacion.acreditar(25, usuario=self.presidente)
        self.abono_b = self.obligacion_b.acreditar(50)
        self.faena = Faena.objects.create(
            comite=self.a, fecha=timezone.localdate(), descripcion="Faena propia"
        )
        self.junta = Junta.objects.create(
            comite=self.a, fecha=timezone.localdate(), tema="Junta propia"
        )
        self.faena_b = Faena.objects.create(
            comite=self.b, fecha=date(2020, 1, 1), descripcion="Faena ajena reservada"
        )
        self.registro = RegistroFaena.objects.create(
            faena=self.faena, ciudadano=self.ciudadano
        )
        RegistroFaena.objects.create(
            faena=self.faena, ciudadano=self.otro, estatus="ASISTIO"
        )
        self.registro_j = AsistenciaJunta.objects.create(
            junta=self.junta, ciudadano=self.ciudadano
        )
        self.registro_b = RegistroFaena.objects.create(
            faena=self.faena_b, ciudadano=self.ciudadano
        )

    def actor(self, username, rol, comite=None):
        user = get_user_model().objects.create_user(username)
        return user, asignar_cargo(user=user, comite=comite or self.a, rol=rol)

    def login(self, user=None):
        self.client.force_login(user or self.lector)

    def snapshot(self):
        return (
            list(ConceptoTesoreria.objects.values()),
            list(ObligacionCiudadano.objects.values()),
            list(Abono.objects.values()),
            list(RegistroFaena.objects.values()),
            list(AsistenciaJunta.objects.values()),
            list(Faena.objects.values()),
            list(Junta.objects.values()),
            list(RegistroFinanciero.objects.values()),
        )

    def test_reader_consults_finance_and_scoped_exports(self):
        self.login()
        for name in [
            "tesoreria_operativa",
            "resumen_aportaciones",
            "buscar_aportaciones",
            "exportar_tesoreria_csv",
            "exportar_aportaciones_csv",
            "actividad_financiera",
        ]:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, self.ajeno.concepto)
        response = self.client.get(
            reverse("tesoreria_concepto_detalle", args=[self.concepto.pk])
        )
        self.assertContains(response, "Ana Ciudadana")
        self.assertFalse(response.context["can_modify"])
        self.assertContains(response, "Imprimir esta página")
        self.assertContains(response, "Compartir consulta")
        self.assertEqual(
            self.client.get(
                reverse("tesoreria_concepto_detalle", args=[self.ajeno.pk])
            ).status_code,
            404,
        )

    def test_reader_attendance_is_scoped_including_metrics_years_and_csv(self):
        self.login()
        response = self.client.get(reverse("control_asistencias"))
        self.assertContains(response, "Faena propia")
        self.assertNotContains(response, "Faena ajena reservada")
        self.assertNotIn(2020, response.context["anios"])
        for kind, event in [("faena", self.faena), ("junta", self.junta)]:
            response = self.client.get(
                reverse(f"control_asistencias_{kind}_detalle", args=[event.pk])
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context["can_capture"])
            self.assertEqual(response.context["admin_change_url"], "")
            self.assertEqual(
                self.client.get(
                    reverse(f"exportar_participantes_{kind}_csv", args=[event.pk])
                ).status_code,
                200,
            )
        self.assertEqual(
            self.client.get(
                reverse("control_asistencias_faena_detalle", args=[self.faena_b.pk])
            ).status_code,
            404,
        )

    def test_reader_cannot_write_finances_or_water_by_direct_url(self):
        self.login()
        before = self.snapshot()
        urls = [
            reverse("crear_concepto_tesoreria"),
            reverse("editar_concepto_tesoreria", args=[self.concepto.pk]),
            reverse("eliminar_concepto_tesoreria", args=[self.concepto.pk]),
            reverse("generar_obligaciones_tesoreria", args=[self.concepto.pk]),
            reverse("acreditar_obligacion", args=[self.obligacion.pk]),
            reverse("seleccionar_obligacion"),
            reverse("crear_cuota_mensual_agua"),
        ]
        for url in urls:
            for method in ["get", "post"]:
                response = getattr(self.client, method)(
                    url, {"monto": "10", "fecha": "2026-11-01", "comite": self.a.pk}
                )
                self.assertIn(
                    response.status_code,
                    [404, 405],
                    (method, url, response.status_code),
                )
        self.assertEqual(before, self.snapshot())

    def test_reader_cannot_write_attendance_and_event_state(self):
        self.login()
        before = self.snapshot()
        for kind, event, record in [
            ("faena", self.faena, self.registro),
            ("junta", self.junta, self.registro_j),
        ]:
            for name, args in [
                (f"captura_asistencia_{kind}", [event.pk]),
                (f"captura_asistencia_secuencial_{kind}", [event.pk]),
                (f"generar_registros_{kind}", [event.pk]),
                (f"editar_{kind}_operativa", [event.pk]),
                ("editar_estado_evento", [kind, event.pk]),
            ]:
                response = self.client.post(
                    reverse(name, args=args),
                    {f"registro_{record.pk}_estatus": "ASISTIO", "estado": "CANCELADA"},
                )
                self.assertEqual(response.status_code, 404, name)
        for name in ["crear_faena_operativa", "crear_junta_operativa"]:
            self.assertEqual(
                self.client.post(reverse(name), {"comite": self.a.pk}).status_code, 404
            )
        self.assertEqual(before, self.snapshot())

    def test_reader_prints_existing_receipts_without_creating_payments(self):
        for user in [self.lector, self.presidente, self.tesorero]:
            self.login(user)
            before = self.snapshot()
            self.assertEqual(self.client.get(reverse("buscar_recibo")).status_code, 200)
            response = self.client.get(
                reverse("recibo_abono", args=[self.abono.folio_recibo])
            )
            self.assertContains(response, self.abono.folio_recibo)
            self.assertEqual(
                self.client.get(
                    reverse("recibo_abono", args=[self.abono_b.folio_recibo])
                ).status_code,
                404,
            )
            self.assertEqual(before, self.snapshot())

    def test_both_writers_capture_faena_and_junta(self):
        for user, status in [
            (self.presidente, "ASISTIO"),
            (self.tesorero, "JUSTIFICADO"),
        ]:
            self.login(user)
            for kind, event, record in [
                ("faena", self.faena, self.registro),
                ("junta", self.junta, self.registro_j),
            ]:
                response = self.client.post(
                    reverse(f"captura_asistencia_{kind}", args=[event.pk]),
                    {f"registro_{record.pk}_estatus": status},
                )
                self.assertEqual(response.status_code, 302)
                record.refresh_from_db()
                self.assertEqual(record.estatus, status)
                self.assertEqual(
                    self.client.post(
                        reverse(f"generar_registros_{kind}", args=[event.pk])
                    ).status_code,
                    302,
                )
            self.assertEqual(
                self.client.post(
                    reverse("captura_asistencia_faena", args=[self.faena_b.pk]), {}
                ).status_code,
                404,
            )

    def test_both_writers_create_own_events_and_reject_foreign_committee(self):
        for user in [self.presidente, self.tesorero]:
            self.login(user)
            for kind in ["faena", "junta"]:
                data = {
                    "comite": self.a.pk,
                    "fecha": timezone.localdate().isoformat(),
                    "alcance": "GENERAL",
                    "estado": "PROGRAMADA",
                    "descripcion": "Nueva faena",
                    "tema": "Nueva junta",
                    "tipo": "ORDINARIA",
                }
                self.assertEqual(
                    self.client.post(
                        reverse(f"crear_{kind}_operativa"), data
                    ).status_code,
                    302,
                )
                data["comite"] = self.b.pk
                self.assertEqual(
                    self.client.post(
                        reverse(f"crear_{kind}_operativa"), data
                    ).status_code,
                    200,
                )
        self.assertEqual(Faena.objects.filter(descripcion="Nueva faena").count(), 2)
        self.assertEqual(Junta.objects.filter(tema="Nueva junta").count(), 2)

    def test_both_writers_edit_state_and_collect_payments(self):
        for user, state in [
            (self.presidente, "REALIZADA"),
            (self.tesorero, "CANCELADA"),
        ]:
            self.login(user)
            self.assertEqual(
                self.client.post(
                    reverse("editar_estado_evento", args=["faena", self.faena.pk]),
                    {"estado": state},
                ).status_code,
                302,
            )
            self.faena.refresh_from_db()
            self.assertEqual(self.faena.estado, state)
            self.assertEqual(
                self.client.post(
                    reverse("acreditar_obligacion", args=[self.obligacion.pk]),
                    {"monto": "5", "fecha": timezone.localdate().isoformat()},
                ).status_code,
                302,
            )
        self.assertEqual(self.obligacion.abonos.count(), 3)
        self.assertEqual(self.obligacion.saldo_pendiente, Decimal("65"))

    def test_reader_with_legacy_global_permissions_still_cannot_write(self):
        self.lector.is_staff = True
        self.lector.save()
        self.lector.user_permissions.set(Permission.objects.all())
        self.login()
        before = self.snapshot()
        self.assertEqual(
            self.client.get(
                reverse("control_asistencias_faena_detalle", args=[self.faena_b.pk])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("editar_estado_evento", args=["faena", self.faena.pk]),
                {"estado": "CANCELADA"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("acreditar_obligacion", args=[self.obligacion.pk]),
                {"monto": "10"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("editar_ciudadano_operativo", args=[self.ciudadano.pk]),
                {"nombre": "Cambio"},
            ).status_code,
            404,
        )
        self.assertEqual(self.client.get(reverse("padron_ciudadanos")).status_code, 404)
        self.client.post(reverse("eliminar_faena_operativa", args=[self.faena.pk]))
        self.assertEqual(before, self.snapshot())

    def test_filters_and_csv_confirm_one_citizen_without_changing_summary(self):
        self.login()
        response = self.client.get(
            reverse("control_asistencias_faena_detalle", args=[self.faena.pk]),
            {"q": "Ana Ciudadana", "estado": "PENDIENTE"},
        )
        self.assertContains(response, "Ana Ciudadana")
        self.assertNotContains(response, "Pedro Participante")
        self.assertEqual(response.context["metricas"]["total_participantes"], 2)
        response = self.client.get(
            reverse("exportar_participantes_faena_csv", args=[self.faena.pk]),
            {"q": "Ana Ciudadana"},
        )
        self.assertContains(response, "Ana Ciudadana")
        self.assertNotContains(response, "Pedro Participante")

    def test_deactivating_role_committee_or_citizen_revokes_access(self):
        self.login()
        for obj, field in [
            (self.cargo_l, "activo"),
            (self.a, "activo"),
            (self.cargo_l.ciudadano, "activo"),
        ]:
            setattr(obj, field, False)
            obj.save()
            self.assertEqual(
                self.client.get(reverse("tesoreria_operativa")).status_code, 404
            )
            self.assertEqual(
                self.client.get(
                    reverse("control_asistencias_faena_detalle", args=[self.faena.pk])
                ).status_code,
                404,
            )
            setattr(obj, field, True)
            obj.save()

    def test_obsolete_roles_have_no_committee_business_capabilities(self):
        for role in ["SECRETARIO", "CAPTURISTA", "DELEGADO"]:
            user, _ = self.actor(role.lower(), role)
            self.login(user)
            self.assertFalse(comites_financieros(user).exists())
            self.assertEqual(
                self.client.get(reverse("tesoreria_operativa")).status_code, 404
            )
            self.assertEqual(
                self.client.get(
                    reverse("control_asistencias_faena_detalle", args=[self.faena.pk])
                ).status_code,
                404,
            )

    def test_second_active_role_rejected_but_inactive_history_retained(self):
        with self.assertRaises(ValidationError):
            UsuarioApp.objects.create(user=self.lector, comite=self.b, rol="TESORERO")
        self.cargo_l.activo = False
        self.cargo_l.save()
        nuevo = UsuarioApp.objects.create(
            user=self.lector, comite=self.b, rol="TESORERO"
        )
        self.assertEqual(nuevo.ciudadano_id, self.cargo_l.ciudadano_id)
        self.assertEqual(self.lector.perfiles_app.count(), 2)
        self.assertEqual(self.lector.perfiles_app.filter(activo=True).count(), 1)
        self.assertTrue(puede_operar_finanzas(self.lector, self.b.pk))
        self.assertFalse(puede_operar_finanzas(self.lector, self.a.pk))

    def test_identity_required_and_cannot_be_substituted(self):
        sin_vinculo = get_user_model().objects.create_user("sin-vinculo")
        with self.assertRaises(ValidationError):
            UsuarioApp.objects.create(user=sin_vinculo, comite=self.a, rol="LECTURA")
        with self.assertRaises(ValidationError):
            UsuarioApp.objects.create(
                user=self.lector, ciudadano=self.otro, comite=self.b, rol="LECTURA"
            )
        perfil = self.lector.perfil_acceso
        perfil.ciudadano = self.otro
        with self.assertRaises(ValidationError):
            perfil.full_clean()

    def test_database_rejects_second_active_assignment_and_null_citizen(self):
        for citizen in [self.cargo_l.ciudadano, None]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                UsuarioApp.objects.bulk_create(
                    [
                        UsuarioApp(
                            user=self.lector,
                            ciudadano=citizen,
                            comite=self.b,
                            rol="PRESIDENTE",
                        )
                    ]
                )

    def test_block_responsibility_is_exclusive_with_committee_role(self):
        with self.assertRaises(ValidationError):
            Manzana.objects.create(
                nombre="Manzana incompatible", responsable=self.cargo_l.ciudadano
            )
        self.cargo_l.activo = False
        self.cargo_l.save()
        manzana = Manzana.objects.create(
            nombre="Manzana propia", responsable=self.cargo_l.ciudadano
        )
        self.cargo_l.ciudadano.manzana = manzana
        self.cargo_l.ciudadano.save()
        with self.assertRaises(ValidationError):
            self.cargo_l.activo = True
            self.cargo_l.save()
        with self.assertRaises(ValidationError):
            Manzana.objects.create(
                nombre="Otra manzana", responsable=self.cargo_l.ciudadano
            )

    def test_audit_is_read_only_and_flags_legacy_conflicts(self):
        stream = io.StringIO()
        call_command("auditar_cargos", stdout=stream)
        self.assertEqual(json.loads(stream.getvalue())["problemas"], [])
        before = list(UsuarioApp.objects.values())
        # Simulate an old inconsistent identity, without bypassing uniqueness constraints.
        UsuarioApp.objects.filter(pk=self.cargo_l.pk).update(ciudadano_id=self.otro.pk)
        stream = io.StringIO()
        with self.assertRaises(CommandError):
            call_command("auditar_cargos", stdout=stream)
        self.assertIn("identidad_no_coincide", stream.getvalue())
        self.assertFalse(comites_financieros(self.lector).exists())
        self.assertEqual(
            UsuarioApp.objects.get(pk=self.cargo_l.pk).ciudadano_id, self.otro.pk
        )
        UsuarioApp.objects.filter(pk=self.cargo_l.pk).update(
            ciudadano_id=self.cargo_l.ciudadano_id
        )

    def test_preflight_reports_duplicates_and_never_chooses_a_role(self):
        informe = evaluar(
            [
                {"id": 1, "user_id": 1, "ciudadano_id": None},
                {"id": 2, "user_id": 1, "ciudadano_id": None},
            ],
            [{"user_id": 1, "ciudadano_id": 10}],
            [{"id": 5, "responsable_id": 10}, {"id": 6, "responsable_id": 10}],
        )
        codes = {p["codigo"] for p in informe["problemas"]}
        self.assertTrue(
            {
                "varios_cargos_cuenta",
                "varios_cargos_ciudadano",
                "comite_y_manzana",
                "varias_manzanas",
            }
            <= codes
        )

    def test_admin_solo_ofrece_los_tres_roles_vigentes_para_altas(self):
        administrador = get_user_model().objects.create_superuser(
            "admin-roles", "admin@example.com", "pw"
        )
        self.login(administrador)
        response = self.client.get(reverse("admin:comites_usuarioapp_add"))
        self.assertEqual(response.status_code, 200)
        choices = dict(response.context["adminform"].form.fields["rol"].choices)
        self.assertEqual(set(choices), {"", "PRESIDENTE", "TESORERO", "LECTURA"})
