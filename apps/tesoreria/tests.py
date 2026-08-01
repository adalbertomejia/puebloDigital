from decimal import Decimal
from datetime import date

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import Comite
from apps.core.models import Ciudadano, Manzana
from apps.tesoreria.forms import ConceptoTesoreriaForm
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

    def test_territorio_y_monto_se_validan_en_el_modelo(self):
        manzana = Manzana.objects.create(nombre="Manzana 4")
        general = self.concepto()
        self.assertEqual(general.alcance, ConceptoTesoreria.Alcances.GENERAL)
        self.assertEqual(general.alcance_legible, "Toda la comunidad")

        for alcance, bloque, monto in [
            (ConceptoTesoreria.Alcances.GENERAL, manzana, Decimal("100")),
            (ConceptoTesoreria.Alcances.MANZANA, None, Decimal("100")),
            (ConceptoTesoreria.Alcances.GENERAL, None, Decimal("0")),
            (ConceptoTesoreria.Alcances.GENERAL, None, Decimal("-1")),
        ]:
            with self.assertRaises(ValidationError):
                self.concepto(alcance=alcance, manzana=bloque, monto_individual=monto)

        territorial = self.concepto(
            alcance=ConceptoTesoreria.Alcances.MANZANA,
            manzana=manzana,
            concepto="Cuota Manzana 4",
        )
        self.assertEqual(territorial.alcance_legible, "Manzana 4")

    def test_formulario_ofrece_activas_y_manzana_historica(self):
        activa = Manzana.objects.create(nombre="Manzana activa")
        historica = Manzana.objects.create(nombre="Manzana histórica", activa=False)
        otra_inactiva = Manzana.objects.create(nombre="Otra inactiva", activa=False)
        self.assertQuerySetEqual(
            ConceptoTesoreriaForm().fields["manzana"].queryset,
            [activa],
        )
        concepto = self.concepto(alcance=ConceptoTesoreria.Alcances.MANZANA, manzana=historica)
        disponibles = ConceptoTesoreriaForm(instance=concepto).fields["manzana"].queryset
        self.assertIn(activa, disponibles)
        self.assertIn(historica, disponibles)
        self.assertNotIn(otra_inactiva, disponibles)

    def test_configuracion_financiera_se_protege_con_obligaciones(self):
        concepto = self.concepto()
        manzana = Manzana.objects.create(nombre="Manzana 2")
        concepto.naturaleza = ConceptoTesoreria.Naturalezas.COOPERACION
        concepto.alcance = ConceptoTesoreria.Alcances.MANZANA
        concepto.manzana = manzana
        concepto.monto_individual = Decimal("120.00")
        concepto.save()

        ObligacionCiudadano.objects.create(
            concepto=concepto, ciudadano=self.activo1, monto_asignado=Decimal("120.00")
        )
        self.assertFalse(concepto.registros_generados)
        cambios = {
            "naturaleza": ConceptoTesoreria.Naturalezas.PAGO,
            "alcance": ConceptoTesoreria.Alcances.GENERAL,
            "manzana": None,
            "monto_individual": Decimal("121.00"),
        }
        for campo, valor in cambios.items():
            concepto.refresh_from_db()
            setattr(concepto, campo, valor)
            with self.assertRaises(ValidationError):
                concepto.save()

        concepto.refresh_from_db()
        concepto.descripcion = "Corrección descriptiva permitida"
        concepto.save()
        self.assertEqual(concepto.descripcion, "Corrección descriptiva permitida")

    def test_tarjetas_muestran_alcance_legible(self):
        manzana = Manzana.objects.create(nombre="Manzana 7")
        self.concepto(concepto="General")
        self.concepto(
            concepto="Territorial",
            alcance=ConceptoTesoreria.Alcances.MANZANA,
            manzana=manzana,
        )
        self.login()
        response = self.client.get(reverse("tesoreria_operativa"))
        self.assertContains(response, "Toda la comunidad")
        self.assertContains(response, "Manzana 7")

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

    def test_generacion_territorial_excluye_fuera_del_alcance(self):
        manzana_4 = Manzana.objects.create(nombre="Manzana 4")
        otra = Manzana.objects.create(nombre="Manzana 2")
        self.activo1.manzana = manzana_4
        self.activo1.save()
        self.activo2.manzana = otra
        self.activo2.save()
        inactivo_local = Ciudadano.objects.create(
            nombre="Dora", apellido_paterno="Local", edad=40, activo=False, manzana=manzana_4
        )
        sin_manzana = Ciudadano.objects.create(
            nombre="Eva", apellido_paterno="Sin manzana", edad=40, activo=True
        )
        concepto = self.concepto(
            alcance=ConceptoTesoreria.Alcances.MANZANA,
            manzana=manzana_4,
            monto_individual=Decimal("500.00"),
        )

        response = self.generar(concepto)

        self.assertEqual(response.status_code, 302)
        self.assertQuerySetEqual(
            concepto.obligaciones.values_list("ciudadano_id", flat=True),
            [self.activo1.pk],
            transform=lambda value: value,
            ordered=False,
        )
        obligacion = concepto.obligaciones.get()
        self.assertEqual(obligacion.monto_asignado, Decimal("500.00"))
        self.assertEqual(obligacion.estado, ObligacionCiudadano.Estados.PENDIENTE)
        self.assertNotIn(inactivo_local.pk, [obligacion.ciudadano_id])
        self.assertNotIn(sin_manzana.pk, [obligacion.ciudadano_id])
        self.assertIn("Manzana 4", list(response.wsgi_request._messages)[0].message)

    def test_regenerar_preserva_historial_y_crea_solo_el_faltante(self):
        concepto = self.concepto()
        concepto.registros_generados = True
        concepto.save()
        self.generar(concepto)
        obligacion = concepto.obligaciones.get(ciudadano=self.activo1)
        obligacion.monto_asignado = Decimal("80.00")
        obligacion.notas = "Convenio histórico"
        obligacion.save()
        abono = obligacion.acreditar(Decimal("20.00"))
        nuevo = Ciudadano.objects.create(
            nombre="Fabián", apellido_paterno="Nuevo", edad=25, activo=True
        )

        self.generar(concepto)

        obligacion.refresh_from_db()
        self.assertEqual(concepto.obligaciones.count(), 3)
        self.assertEqual(obligacion.monto_asignado, Decimal("80.00"))
        self.assertEqual(obligacion.estado, ObligacionCiudadano.Estados.PENDIENTE)
        self.assertEqual(obligacion.notas, "Convenio histórico")
        self.assertTrue(Abono.objects.filter(pk=abono.pk).exists())
        self.assertEqual(concepto.obligaciones.get(ciudadano=nuevo).monto_asignado, Decimal("100.00"))

    def test_bandera_falsa_no_duplica_y_cambios_del_ciudadano_no_borran(self):
        manzana = Manzana.objects.create(nombre="Manzana 4")
        self.activo1.manzana = manzana
        self.activo1.save()
        concepto = self.concepto(alcance=ConceptoTesoreria.Alcances.MANZANA, manzana=manzana)
        ObligacionCiudadano.objects.create(
            concepto=concepto, ciudadano=self.activo1, monto_asignado=concepto.monto_individual
        )
        self.activo1.manzana = None
        self.activo1.activo = False
        self.activo1.save()

        self.generar(concepto)

        self.assertFalse(concepto.registros_generados)
        self.assertEqual(concepto.obligaciones.filter(ciudadano=self.activo1).count(), 1)

    def test_accion_es_post_autenticada_y_mensajes_vacios_o_existentes(self):
        concepto = self.concepto()
        url = reverse("generar_obligaciones_tesoreria", args=[concepto.pk])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(concepto.obligaciones.count(), 0)
        self.login()
        self.assertEqual(self.client.get(url).status_code, 405)
        self.generar(concepto)
        response = self.generar(concepto)
        self.assertIn("ya estaban generadas", list(response.wsgi_request._messages)[-1].message)

        Ciudadano.objects.update(activo=False)
        vacio = self.concepto(concepto="Vacío")
        response = self.generar(vacio)
        self.assertIn("No existen ciudadanos activos", list(response.wsgi_request._messages)[-1].message)

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
        self.assertContains(response, 'name="q" value="Ana"')

    def test_sidebar_tesoreria_order_and_active(self):
        self.login()
        response = self.client.get(reverse("tesoreria_operativa"))
        html = response.content.decode()
        self.assertLess(
            html.index("✓</span> Control de Asistencias"),
            html.index("$</span> Tesorería"),
        )
        self.assertContains(response, "Tesorería")
        self.assertContains(response, "bg-slate-800")

    def test_usuario_sin_permisos_no_modifica_por_url_directa(self):
        concepto = self.concepto(); self.login(self.reader)
        self.client.post(reverse("generar_obligaciones_tesoreria", args=[concepto.pk]))
        self.assertEqual(concepto.obligaciones.count(), 0)

    def test_detalle_metricas_modelo_abonos_parciales_y_estados(self):
        concepto = self.concepto(monto_individual=Decimal("100.00"))
        self.generar(concepto)
        obligacion = concepto.obligaciones.get(ciudadano=self.activo1)

        self.assertEqual(obligacion.total_abonado, Decimal("0.00"))
        self.assertEqual(obligacion.saldo_pendiente, Decimal("100.00"))

        obligacion.acreditar(Decimal("40.00"), date(2026, 7, 20), "parcial")
        obligacion.refresh_from_db()
        self.assertEqual(obligacion.total_abonado, Decimal("40.00"))
        self.assertEqual(obligacion.saldo_pendiente, Decimal("60.00"))
        self.assertEqual(obligacion.estado, ObligacionCiudadano.Estados.PENDIENTE)

        obligacion.acreditar(Decimal("30.00"), date(2026, 7, 21), "parcial repetido 1")
        with self.assertRaises(ValidationError):
            obligacion.acreditar(Decimal("31.00"), date(2026, 7, 22), "excede saldo")
        obligacion.acreditar(Decimal("30.00"), date(2026, 7, 22), "parcial repetido 2")
        obligacion.refresh_from_db()
        self.assertEqual(obligacion.abonos.count(), 3)
        self.assertEqual(obligacion.total_abonado, Decimal("100.00"))
        self.assertEqual(obligacion.saldo_pendiente, Decimal("0.00"))
        self.assertEqual(obligacion.estado, ObligacionCiudadano.Estados.PAGADO)

    def test_detalle_metricas_globales_no_duplican_obligaciones_ni_descartan_abonos_repetidos(self):
        concepto = self.concepto(monto_individual=Decimal("1000.00"))
        self.generar(concepto)
        o1 = concepto.obligaciones.get(ciudadano=self.activo1)
        o2 = concepto.obligaciones.get(ciudadano=self.activo2)
        o1.acreditar(Decimal("500.00"), date(2026, 7, 20), "1")
        o1.acreditar(Decimal("500.00"), date(2026, 7, 21), "2")
        o2.acreditar(Decimal("250.00"), date(2026, 7, 22), "parcial")

        self.login()
        response = self.client.get(reverse("tesoreria_concepto_detalle", args=[concepto.pk]))
        metricas = response.context["metricas"]

        self.assertEqual(metricas["total_generado"], Decimal("2000.00"))
        self.assertEqual(metricas["total_abonado"], Decimal("1250.00"))
        self.assertEqual(metricas["saldo_pendiente"], Decimal("750.00"))
        self.assertEqual(metricas["pendientes"], 1)
        self.assertEqual(metricas["pagadas"], 1)
        self.assertEqual(response.context["concepto"].cantidad_obligaciones, 2)
        self.assertEqual(response.context["concepto"].cantidad_pagada, 1)
        self.assertContains(response, "$500.00", count=2)

    def test_detalle_metricas_no_cambian_con_busqueda_o_filtro_estado(self):
        concepto = self.concepto(monto_individual=Decimal("1000.00"))
        self.generar(concepto)
        concepto.obligaciones.get(ciudadano=self.activo1).acreditar(Decimal("1000.00"), date(2026, 7, 20))
        expected = {
            "total_generado": Decimal("2000.00"),
            "total_abonado": Decimal("1000.00"),
            "saldo_pendiente": Decimal("1000.00"),
            "pendientes": 1,
            "pagadas": 1,
        }

        self.login()
        for querystring in ["?q=Ana", "?estado=PAGADO", "?estado=PENDIENTE"]:
            response = self.client.get(reverse("tesoreria_concepto_detalle", args=[concepto.pk]) + querystring)
            self.assertEqual(response.context["metricas"], expected)

    def test_detalle_historial_prefetch_muestra_todos_los_abonos(self):
        concepto = self.concepto(monto_individual=Decimal("1000.00"))
        self.generar(concepto)
        obligacion = concepto.obligaciones.get(ciudadano=self.activo1)
        obligacion.acreditar(Decimal("500.00"), date(2026, 7, 20), "primer abono")
        obligacion.acreditar(Decimal("500.00"), date(2026, 7, 21), "segundo abono")

        self.login()
        response = self.client.get(reverse("tesoreria_concepto_detalle", args=[concepto.pk]) + "?q=Ana")
        self.assertContains(response, "primer abono")
        self.assertContains(response, "segundo abono")
        obligacion_renderizada = response.context["obligaciones"][0]
        self.assertTrue(hasattr(obligacion_renderizada, "_prefetched_objects_cache"))
        self.assertIn("abonos", obligacion_renderizada._prefetched_objects_cache)

    def test_abono_directo_cancelado_es_rechazado_y_sin_saldo_se_actualiza_a_pagado(self):
        concepto = self.concepto(monto_individual=Decimal("100.00"))
        self.generar(concepto)
        cancelada = concepto.obligaciones.get(ciudadano=self.activo1)
        cancelada.estado = ObligacionCiudadano.Estados.CANCELADO
        cancelada.save(update_fields=["estado", "updated_at"])
        with self.assertRaises(ValidationError):
            Abono.objects.create(obligacion=cancelada, monto=Decimal("1.00"), fecha=date(2026, 7, 20))

        sin_saldo = concepto.obligaciones.get(ciudadano=self.activo2)
        sin_saldo.acreditar(Decimal("100.00"), date(2026, 7, 20))
        sin_saldo.refresh_from_db()
        self.assertEqual(sin_saldo.estado, ObligacionCiudadano.Estados.PAGADO)
        self.assertNotEqual(sin_saldo.estado, ObligacionCiudadano.Estados.PENDIENTE)

    def test_detalle_caso_real_51_obligaciones_5_abonos(self):
        concepto = self.concepto(monto_individual=Decimal("1000.00"))
        ciudadanos = [self.activo1, self.activo2]
        for i in range(49):
            ciudadanos.append(Ciudadano.objects.create(nombre=f"Ciudadano {i}", apellido_paterno="Prueba", apellido_materno=str(i), edad=20 + i, activo=True))
        for ciudadano in ciudadanos:
            ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=ciudadano, monto_asignado=Decimal("1000.00"))

        obligaciones = list(concepto.obligaciones.order_by("id")[:4])
        obligaciones[0].acreditar(Decimal("1000.00"), date(2026, 7, 20))
        obligaciones[1].acreditar(Decimal("500.00"), date(2026, 7, 20))
        obligaciones[1].acreditar(Decimal("500.00"), date(2026, 7, 21))
        obligaciones[2].acreditar(Decimal("1000.00"), date(2026, 7, 20))
        obligaciones[3].acreditar(Decimal("1000.00"), date(2026, 7, 20))

        self.login()
        response = self.client.get(reverse("tesoreria_concepto_detalle", args=[concepto.pk]))
        metricas = response.context["metricas"]
        self.assertEqual(metricas["total_generado"], Decimal("51000.00"))
        self.assertEqual(metricas["total_abonado"], Decimal("4000.00"))
        self.assertEqual(metricas["saldo_pendiente"], Decimal("47000.00"))
        self.assertEqual(metricas["pendientes"], 47)
        self.assertEqual(metricas["pagadas"], 4)
        self.assertEqual(response.context["concepto"].cantidad_pendiente + response.context["concepto"].cantidad_pagada + response.context["concepto"].cantidad_cancelada, 51)
