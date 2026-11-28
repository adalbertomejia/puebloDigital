from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import Comite, PerfilAcceso, UsuarioApp
from apps.core.models import Ciudadano, Manzana
from apps.operacion.models import Faena, Junta, RegistroFaena
from apps.tesoreria.models import ConceptoTesoreria, ObligacionCiudadano


class DelegacionCentralTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegacion = Comite.objects.create(nombre="Delegación", tipo=Comite.Tipos.DELEGACION)
        cls.agua = Comite.objects.create(nombre="Agua", tipo=Comite.Tipos.AGUA)
        cls.manzana = Manzana.objects.create(nombre="Norte")
        cls.ciudadano = Ciudadano.objects.create(
            nombre="Ana", apellido_paterno="Norte", manzana=cls.manzana,
        )
        cls.faena = Faena.objects.create(
            comite=cls.agua, fecha=date(2026, 10, 1), descripcion="Limpieza norte",
            alcance=Faena.Alcances.MANZANA, manzana=cls.manzana,
        )
        cls.registro = RegistroFaena.objects.create(faena=cls.faena, ciudadano=cls.ciudadano)
        cls.junta = Junta.objects.create(
            comite=cls.agua, fecha=date(2026, 10, 2), tema="Reunión de Agua",
        )
        cls.concepto = ConceptoTesoreria.objects.create(
            comite=cls.agua, concepto="Cuota del Agua", naturaleza="PAGO",
            monto_individual=100, fecha=date(2026, 10, 1),
        )
        cls.obligacion = ObligacionCiudadano.objects.create(
            concepto=cls.concepto, ciudadano=cls.ciudadano, monto_asignado=100,
        )

    def asignar(self, rol, comite):
        usuario = get_user_model().objects.create_user(username=f"{rol}-{comite.pk}")
        ciudadano = Ciudadano.objects.create(nombre=usuario.username, apellido_paterno="Operador")
        PerfilAcceso.objects.create(user=usuario, ciudadano=ciudadano)
        cargo = UsuarioApp.objects.create(user=usuario, comite=comite, rol=rol)
        self.client.force_login(usuario)
        return cargo

    def test_ambos_cargos_operan_fuera_de_su_comite_sin_staff(self):
        for rol, etiqueta in (
            (UsuarioApp.Roles.SECRETARIO, "Secretaría central"),
            (UsuarioApp.Roles.PRESIDENTE, "Delegado"),
        ):
            with self.subTest(rol=rol):
                cargo = self.asignar(rol, self.delegacion)
                self.assertFalse(cargo.user.is_staff)
                self.assertContains(self.client.get(reverse("mis_responsabilidades")), etiqueta)
                inicio = self.client.get(reverse("dashboard_operativo"))
                self.assertContains(inicio, f'href="{reverse("tesoreria_operativa")}"')
                self.assertContains(inicio, f'href="{reverse("control_agua")}"')
                self.assertContains(inicio, reverse("editar_ciudadano_operativo", args=[self.ciudadano.pk]))
                self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)
                for nombre, args in (
                    ("padron_ciudadanos", []),
                    ("crear_ciudadano_operativo", []),
                    ("editar_ciudadano_operativo", [self.ciudadano.pk]),
                    ("crear_faena_operativa", []),
                    ("editar_faena_operativa", [self.faena.pk]),
                    ("captura_asistencia_faena", [self.faena.pk]),
                    ("crear_junta_operativa", []),
                    ("editar_junta_operativa", [self.junta.pk]),
                    ("control_agua", []),
                    ("crear_cuota_mensual_agua", []),
                    ("tesoreria_operativa", []),
                    ("tesoreria_concepto_detalle", [self.concepto.pk]),
                ):
                    with self.subTest(vista=nombre):
                        self.assertEqual(self.client.get(reverse(nombre, args=args)).status_code, 200)

                estatus = (
                    RegistroFaena.Estatus.ASISTIO
                    if rol == UsuarioApp.Roles.SECRETARIO
                    else RegistroFaena.Estatus.JUSTIFICADO
                )
                captura = self.client.post(
                    reverse("captura_asistencia_faena", args=[self.faena.pk]),
                    {f"registro_{self.registro.pk}_estatus": estatus},
                )
                self.assertEqual(captura.status_code, 302)
                self.registro.refresh_from_db()
                self.assertEqual(self.registro.estatus, estatus)

                abono = self.client.post(reverse("acreditar_obligacion", args=[self.obligacion.pk]), {
                    "monto": "10", "fecha": "2026-10-03", "notas": "Abono de prueba",
                })
                self.assertEqual(abono.status_code, 302)
                self.obligacion.refresh_from_db()
                self.assertTrue(self.obligacion.abonos.filter(creado_por=cargo.user, monto=Decimal("10")).exists())

    def test_secretaria_consulta_balance_y_presidente_conserva_su_ambito(self):
        self.asignar(UsuarioApp.Roles.SECRETARIO, self.delegacion)
        self.assertEqual(self.client.get(reverse("balance_recaudacion")).status_code, 200)
        self.assertEqual(self.client.get(reverse(
            "balance_concepto_detalle", args=[self.concepto.pk],
        )).status_code, 200)

        self.asignar(UsuarioApp.Roles.PRESIDENTE, self.delegacion)
        detalle = reverse("balance_concepto_detalle", args=[self.concepto.pk])
        self.assertEqual(self.client.get(detalle).status_code, 404)
        self.assertEqual(self.client.get(reverse("balance_recaudacion")).status_code, 200)

    def test_el_alcance_nuevo_no_concede_eliminacion(self):
        self.asignar(UsuarioApp.Roles.SECRETARIO, self.delegacion)
        for nombre, objeto in (
            ("eliminar_faena_operativa", self.faena),
            ("eliminar_junta_operativa", self.junta),
            ("eliminar_concepto_tesoreria", self.concepto),
        ):
            with self.subTest(vista=nombre):
                self.assertIn(self.client.post(reverse(nombre, args=[objeto.pk])).status_code, (302, 404))
                self.assertTrue(type(objeto).objects.filter(pk=objeto.pk).exists())
        edicion = self.client.get(reverse("editar_concepto_tesoreria", args=[self.concepto.pk]))
        self.assertNotContains(edicion, "Eliminar concepto")

    def test_presidente_conserva_eliminacion_financiera_en_su_propio_comite(self):
        self.asignar(UsuarioApp.Roles.PRESIDENTE, self.delegacion)
        concepto_propio = ConceptoTesoreria.objects.create(
            comite=self.delegacion, concepto="Cuota de Delegación", naturaleza="PAGO",
            monto_individual=100, fecha=date(2026, 10, 1),
        )
        for concepto in (self.concepto, concepto_propio):
            respuesta = self.client.post(reverse("eliminar_concepto_tesoreria", args=[concepto.pk]))
            self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(ConceptoTesoreria.objects.filter(pk=self.concepto.pk).exists())
        self.assertFalse(ConceptoTesoreria.objects.filter(pk=concepto_propio.pk).exists())

    def test_secretario_de_otro_comite_y_cargo_inactivo_no_obtienen_acceso(self):
        self.asignar(UsuarioApp.Roles.SECRETARIO, self.agua)
        self.assertEqual(self.client.get(reverse("tesoreria_operativa")).status_code, 404)

        cargo = self.asignar(UsuarioApp.Roles.SECRETARIO, self.delegacion)
        cargo.activo = False
        cargo.save(update_fields=["activo"])
        self.assertEqual(self.client.get(reverse("tesoreria_operativa")).status_code, 404)

    def test_delegacion_ambigua_o_inactiva_no_concede_acceso_comunitario(self):
        self.asignar(UsuarioApp.Roles.SECRETARIO, self.delegacion)
        otra = Comite.objects.create(nombre="Otra delegación", tipo=Comite.Tipos.DELEGACION)
        self.assertEqual(self.client.get(reverse("padron_ciudadanos")).status_code, 404)
        otra.activo = False
        otra.save(update_fields=["activo"])
        self.assertEqual(self.client.get(reverse("padron_ciudadanos")).status_code, 200)
        self.delegacion.activo = False
        self.delegacion.save(update_fields=["activo"])
        self.assertEqual(self.client.get(reverse("padron_ciudadanos")).status_code, 404)
