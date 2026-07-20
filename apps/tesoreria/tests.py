from decimal import Decimal
from datetime import date

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import Comite
from apps.core.models import Ciudadano
from apps.tesoreria.models import Abono, ConceptoTesoreria, ObligacionCiudadano


class TesoreriaOperativaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tesorero", password="pw")
        self.reader = User.objects.create_user("lector", password="pw")
        perms = Permission.objects.filter(codename__in=["add_conceptotesoreria", "change_conceptotesoreria", "add_abono"])
        self.user.user_permissions.set(perms)
        self.comite = Comite.objects.create(nombre="Comité de Delegación", tipo=Comite.Tipos.DELEGACION)
        self.agua = Comite.objects.create(nombre="Comité de Agua", tipo=Comite.Tipos.AGUA)
        self.activo1 = Ciudadano.objects.create(nombre="Ana", apellido_paterno="López", apellido_materno="A", edad=30, activo=True)
        self.activo2 = Ciudadano.objects.create(nombre="Beto", apellido_paterno="Pérez", apellido_materno="B", edad=31, activo=True)
        self.inactivo = Ciudadano.objects.create(nombre="Ciro", apellido_paterno="Ruiz", apellido_materno="C", edad=32, activo=False)

    def login(self, user=None):
        self.client.login(username=(user or self.user).username, password="pw")

    def concepto(self, **kwargs):
        data = dict(naturaleza=ConceptoTesoreria.Naturalezas.PAGO, comite=self.comite, concepto="Cuota anual de agua 2026", monto_individual=Decimal("100.00"), fecha=date(2026, 7, 20))
        data.update(kwargs)
        return ConceptoTesoreria.objects.create(**data)

    def generar(self, concepto):
        self.login()
        return self.client.post(reverse("generar_obligaciones_tesoreria", args=[concepto.pk]))

    def test_crear_concepto_pago_y_cooperacion(self):
        pago = self.concepto(naturaleza=ConceptoTesoreria.Naturalezas.PAGO)
        coop = self.concepto(naturaleza=ConceptoTesoreria.Naturalezas.COOPERACION, concepto="Cooperación fiesta")
        self.assertEqual(pago.get_naturaleza_display(), "Pago")
        self.assertEqual(coop.get_naturaleza_display(), "Cooperación")

    def test_generar_obligaciones_solo_activos_e_idempotente(self):
        concepto = self.concepto()
        self.generar(concepto)
        self.assertEqual(concepto.obligaciones.count(), 2)
        self.assertFalse(concepto.obligaciones.filter(ciudadano=self.inactivo).exists())
        self.generar(concepto)
        self.assertEqual(concepto.obligaciones.count(), 2)

    def test_pago_completo_y_estado_pagado(self):
        concepto = self.concepto()
        self.generar(concepto)
        obligacion = concepto.obligaciones.first()
        obligacion.acreditar(Decimal("100.00"), date(2026, 7, 20), "liquidado")
        obligacion.refresh_from_db()
        self.assertEqual(obligacion.estado, ObligacionCiudadano.Estados.PAGADO)
        self.assertEqual(obligacion.saldo_pendiente, Decimal("0.00"))

    def test_varios_abonos_parciales(self):
        concepto = self.concepto()
        self.generar(concepto)
        obligacion = concepto.obligaciones.first()
        obligacion.acreditar(Decimal("40.00"), date(2026, 7, 20), "1")
        obligacion.acreditar(Decimal("60.00"), date(2026, 7, 21), "2")
        obligacion.refresh_from_db()
        self.assertEqual(obligacion.abonos.count(), 2)
        self.assertEqual(obligacion.total_abonado, Decimal("100.00"))
        self.assertEqual(obligacion.estado, ObligacionCiudadano.Estados.PAGADO)

    def test_rechaza_abonos_invalidos_pagados_y_cancelados(self):
        concepto = self.concepto()
        self.generar(concepto)
        o1, o2 = list(concepto.obligaciones.all())
        for monto in [Decimal("0"), Decimal("-1"), Decimal("101")]:
            with self.assertRaises(ValidationError):
                o1.acreditar(monto)
        o1.acreditar(Decimal("100"))
        with self.assertRaises(ValidationError):
            o1.acreditar(Decimal("1"))
        o2.estado = ObligacionCiudadano.Estados.CANCELADO
        o2.save()
        with self.assertRaises(ValidationError):
            o2.acreditar(Decimal("1"))

    def test_metricas_y_filtros_principal(self):
        pago = self.concepto(naturaleza=ConceptoTesoreria.Naturalezas.PAGO, fecha=date(2026, 7, 1), concepto="Agua julio")
        coop = self.concepto(naturaleza=ConceptoTesoreria.Naturalezas.COOPERACION, fecha=date(2026, 6, 1), concepto="Fiesta patronal", comite=self.agua)
        self.generar(pago)
        o = pago.obligaciones.first(); o.acreditar(Decimal("100"))
        self.login()
        self.assertContains(self.client.get(reverse("tesoreria_operativa") + "?q=Agua&naturaleza=PAGO&mes=7&anio=2026"), "Agua julio")
        self.assertNotContains(self.client.get(reverse("tesoreria_operativa") + "?naturaleza=COOPERACION"), "Agua julio")
        self.assertContains(self.client.get(reverse("tesoreria_operativa") + "?estado=SIN_GENERAR"), "Fiesta patronal")
        self.assertContains(self.client.get(reverse("tesoreria_operativa") + "?estado=CON_PENDIENTES"), "Agua julio")
        pago.obligaciones.exclude(pk=o.pk).update(estado=ObligacionCiudadano.Estados.PAGADO)
        self.assertContains(self.client.get(reverse("tesoreria_operativa") + "?estado=COMPLETADO"), "Agua julio")


    def test_nuevas_metricas_tesoreria_operativa(self):
        self.concepto(concepto="Sin obligaciones")
        en_cobro = self.concepto(concepto="Feria 2027")
        completado = self.concepto(concepto="Cooperación completada")
        otro_mes = self.concepto(concepto="Abono histórico")

        for concepto in [en_cobro, completado, otro_mes]:
            ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=self.activo1, monto_asignado=Decimal("100.00"))
            ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=self.activo2, monto_asignado=Decimal("100.00"))

        # Dos obligaciones pendientes del mismo ciudadano en conceptos diferentes deben contarse una sola vez.
        ObligacionCiudadano.objects.create(concepto=en_cobro, ciudadano=self.inactivo, monto_asignado=Decimal("100.00"))
        ObligacionCiudadano.objects.create(concepto=otro_mes, ciudadano=self.inactivo, monto_asignado=Decimal("100.00"))

        for obligacion in completado.obligaciones.all():
            obligacion.acreditar(Decimal("100.00"), date(2026, 7, 5))

        en_cobro.obligaciones.get(ciudadano=self.activo1).acreditar(Decimal("40.00"), date(2026, 7, 10))
        Abono.objects.create(
            obligacion=otro_mes.obligaciones.get(ciudadano=self.activo1),
            monto=Decimal("25.00"),
            fecha=date(2026, 6, 30),
        )

        self.login()
        response = self.client.get(reverse("tesoreria_operativa"))
        metricas = response.context["metricas"]

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("total_generado", metricas)
        self.assertNotIn("total_abonado", metricas)
        self.assertNotIn("saldo_pendiente", metricas)
        self.assertNotIn("ciudadanos_pendientes", metricas)
        self.assertEqual(metricas["conceptos_en_cobro"], 2)
        self.assertEqual(metricas["conceptos_completados"], 1)
        self.assertEqual(metricas["ciudadanos_conceptos_pendientes"], 3)
        self.assertEqual(metricas["recaudado_mes"], Decimal("240.00"))
        self.assertContains(response, "Conceptos en cobro")
        self.assertContains(response, "Conceptos completados")
        self.assertContains(response, "Recaudado este mes")
        self.assertContains(response, "Ciudadanos con conceptos pendientes")
        self.assertContains(response, "$240.00")

        filtered_response = self.client.get(reverse("tesoreria_operativa") + "?q=Feria")
        self.assertEqual(filtered_response.context["metricas"]["recaudado_mes"], Decimal("240.00"))

    def test_busqueda_detalle_y_paginacion_conserva_filtros(self):
        concepto = self.concepto(); self.generar(concepto); self.login()
        response = self.client.get(reverse("tesoreria_concepto_detalle", args=[concepto.pk]) + "?q=Ana&estado=PENDIENTE&page=1")
        self.assertContains(response, "Ana López")
        self.assertContains(response, "q=Ana")

    def test_sidebar_tesoreria_order_and_active(self):
        self.login()
        response = self.client.get(reverse("tesoreria_operativa"))
        html = response.content.decode()
        self.assertLess(html.index("Control de Asistencias"), html.index("Tesorería"))
        self.assertContains(response, "Tesorería")
        self.assertContains(response, "bg-slate-800")

    def test_usuario_sin_permisos_no_modifica_por_url_directa(self):
        concepto = self.concepto(); self.login(self.reader)
        self.client.post(reverse("generar_obligaciones_tesoreria", args=[concepto.pk]))
        self.assertEqual(concepto.obligaciones.count(), 0)
