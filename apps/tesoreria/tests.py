from decimal import Decimal
from datetime import date

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import Comite
from apps.core.models import Ciudadano, Manzana
from apps.core.views import _resumen_territorial
from apps.tesoreria.forms import ConceptoTesoreriaForm
from apps.tesoreria.models import Abono, ConceptoTesoreria, ObligacionCiudadano
from apps.tesoreria.queries import abonos_filtrados


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
        concepto = self.concepto(concepto="Feria 2027")
        ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=self.activo1, monto_asignado=Decimal("100.00"))
        pagada = ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=self.activo2, monto_asignado=Decimal("100.00"))
        pagada.acreditar(Decimal("100.00"), date(2026, 7, 5))
        self.login()
        metricas = self.client.get(reverse("tesoreria_operativa") + "?q=Feria").context["metricas"]
        self.assertEqual(metricas["total_asignado"], Decimal("200.00"))
        self.assertEqual(metricas["total_abonado"], Decimal("100.00"))
        self.assertEqual(metricas["saldo_pendiente"], Decimal("100.00"))
        self.assertEqual(metricas["ciudadanos_pendientes"], 1)
        self.assertEqual(metricas["porcentaje_cumplimiento"], 50.0)

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
            html.index("Control de Asistencias"),
            html.index('>Tesorería</a>'),
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
            self.assertEqual({key: response.context["metricas"][key] for key in expected}, expected)

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

class TesoreriaFiltrosCsvTests(TestCase):
    """Cobertura de la experiencia filtrada y de las exportaciones de Fase 3.3."""

    def setUp(self):
        self.user = User.objects.create_user("tesorero_csv", password="pw")
        self.comite = Comite.objects.create(nombre="Comité Principal", tipo=Comite.Tipos.DELEGACION)
        self.activo1 = Ciudadano.objects.create(nombre="Ana", apellido_paterno="López", apellido_materno="A", edad=30, activo=True)
        self.activo2 = Ciudadano.objects.create(nombre="Beto", apellido_paterno="Pérez", apellido_materno="B", edad=31, activo=True)

    def login(self):
        self.client.login(username=self.user.username, password="pw")

    def concepto(self, **kwargs):
        datos = dict(naturaleza=ConceptoTesoreria.Naturalezas.PAGO, comite=self.comite, concepto="Cuota 2026", monto_individual=Decimal("100.00"), fecha=date(2026, 7, 20))
        datos.update(kwargs)
        return ConceptoTesoreria.objects.create(**datos)

    def test_cancelada_es_historica_pero_no_exigible(self):
        concepto = self.concepto()
        pendiente = ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=self.activo1, monto_asignado=Decimal("100"))
        cancelada = ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=self.activo2, monto_asignado=Decimal("80"), estado=ObligacionCiudadano.Estados.CANCELADO)
        self.login()
        response = self.client.get(reverse("tesoreria_concepto_detalle", args=[concepto.pk]))
        self.assertEqual(response.context["metricas"]["total"], 2)
        self.assertEqual(response.context["metricas"]["canceladas"], 1)
        self.assertEqual(response.context["metricas"]["total_asignado"], Decimal("100"))
        self.assertEqual(response.context["metricas"]["saldo_pendiente"], Decimal("100"))
        self.assertEqual(response.context["metricas"]["porcentaje_cumplimiento"], 0)

    def test_filtros_territoriales_y_demograficos_se_combinan(self):
        manzana = Manzana.objects.create(nombre="Manzana 4")
        self.activo1.manzana = manzana; self.activo1.sexo = Ciudadano.Sexos.MUJER
        self.activo1.motivo_alta = Ciudadano.MotivosAlta.MAYORIA_EDAD; self.activo1.edad = 70; self.activo1.save()
        concepto = self.concepto(naturaleza=ConceptoTesoreria.Naturalezas.COOPERACION, alcance=ConceptoTesoreria.Alcances.MANZANA, manzana=manzana)
        ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=self.activo1, monto_asignado=Decimal("100"))
        self.login()
        principal = self.client.get(reverse("tesoreria_operativa"), {"naturaleza":"COOPERACION", "alcance":"MANZANA", "manzana":str(manzana.pk), "mes":"7", "anio":"2026", "estado":"CON_PENDIENTES"})
        self.assertContains(principal, concepto.concepto)
        detalle = self.client.get(reverse("tesoreria_concepto_detalle", args=[concepto.pk]), {"q":"Ana López", "sexo":"MUJER", "rango_edad":"65_mas", "motivo_alta":Ciudadano.MotivosAlta.MAYORIA_EDAD, "saldo":"con_saldo"})
        self.assertEqual(len(detalle.context["obligaciones"]), 1)

    def test_csv_resumen_y_detalle_respetan_filtros_y_bom(self):
        incluido = self.concepto(concepto="Feria comunitaria", naturaleza=ConceptoTesoreria.Naturalezas.COOPERACION)
        excluido = self.concepto(concepto="Agua")
        obligacion = ObligacionCiudadano.objects.create(concepto=incluido, ciudadano=self.activo1, monto_asignado=Decimal("100"))
        obligacion.acreditar(Decimal("40"), date(2026, 7, 20), "parcial")
        self.login()
        resumen = self.client.get(reverse("exportar_tesoreria_csv"), {"naturaleza":"COOPERACION"})
        self.assertTrue(resumen.content.startswith(b"\xef\xbb\xbf"))
        texto = resumen.content.decode("utf-8-sig")
        self.assertIn("Obligaciones totales", texto); self.assertIn("Feria comunitaria", texto); self.assertNotIn("Agua", texto)
        detalle = self.client.get(reverse("exportar_obligaciones_tesoreria_csv", args=[incluido.pk]), {"q":"Ana", "saldo":"con_saldo", "page":"99"})
        texto_detalle = detalle.content.decode("utf-8-sig")
        self.assertIn("Edad actual", texto_detalle); self.assertIn("Ana López", texto_detalle); self.assertIn("60", texto_detalle)

    def test_exportaciones_requieren_autenticacion(self):
        concepto = self.concepto()
        self.assertEqual(self.client.get(reverse("exportar_tesoreria_csv")).status_code, 302)
        self.assertEqual(self.client.get(reverse("exportar_obligaciones_tesoreria_csv", args=[concepto.pk])).status_code, 302)


class ResumenAportacionesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("consulta", password="pw")
        self.comite = Comite.objects.create(nombre="Comité comunitario", tipo=Comite.Tipos.DELEGACION)
        self.otro_comite = Comite.objects.create(nombre="Comité feria", tipo=Comite.Tipos.FERIA)
        self.manzana_historica = Manzana.objects.create(nombre="Manzana 4")
        self.manzana_actual = Manzana.objects.create(nombre="Manzana 2")
        self.ana = Ciudadano.objects.create(nombre="Ana", apellido_paterno="López", apellido_materno="Ríos", numero_contrato="C-10", manzana=self.manzana_actual)
        self.beto = Ciudadano.objects.create(nombre="Beto", apellido_paterno="Pérez", manzana=self.manzana_historica)
        self.pago = ConceptoTesoreria.objects.create(naturaleza="PAGO", alcance="GENERAL", comite=self.comite, concepto="Cuota general", monto_individual=Decimal("1000"), fecha=date(2026, 7, 1))
        self.cooperacion = ConceptoTesoreria.objects.create(naturaleza="COOPERACION", alcance="MANZANA", manzana=self.manzana_historica, comite=self.otro_comite, concepto="Feria de manzana", monto_individual=Decimal("1000"), fecha=date(2026, 8, 1))
        op = ObligacionCiudadano.objects.create(concepto=self.pago, ciudadano=self.ana, monto_asignado=Decimal("1000"))
        oc1 = ObligacionCiudadano.objects.create(concepto=self.cooperacion, ciudadano=self.ana, monto_asignado=Decimal("1000"))
        oc2 = ObligacionCiudadano.objects.create(concepto=self.cooperacion, ciudadano=self.beto, monto_asignado=Decimal("1000"))
        self.a1 = Abono.objects.create(obligacion=op, monto=Decimal("25"), fecha=date(2026, 7, 20))
        self.a2 = Abono.objects.create(obligacion=oc1, monto=Decimal("40"), fecha=date(2026, 8, 1))
        self.a3 = Abono.objects.create(obligacion=oc2, monto=Decimal("35"), fecha=date(2026, 8, 2))

    def get(self, params=None):
        self.client.login(username="consulta", password="pw")
        return self.client.get(reverse("resumen_aportaciones"), params or {})

    def test_vista_y_csv_requieren_autenticacion(self):
        self.assertEqual(self.client.get(reverse("resumen_aportaciones")).status_code, 302)
        self.assertEqual(self.client.get(reverse("exportar_aportaciones_csv")).status_code, 302)

    def test_metricas_parten_de_abonos_y_ciudadanos_distintos(self):
        metricas = self.get().context["metricas"]
        self.assertEqual(metricas["total_recibido"], Decimal("100"))
        self.assertEqual(metricas["pagos_recibidos"], Decimal("25"))
        self.assertEqual(metricas["cooperaciones_recibidas"], Decimal("75"))
        self.assertEqual(metricas["ciudadanos_con_aportaciones"], 2)

    def test_filtros_individuales_y_combinados(self):
        casos = [
            ({"mes": "7"}, Decimal("25")), ({"anio": "2026"}, Decimal("100")),
            ({"naturaleza": "COOPERACION"}, Decimal("75")), ({"alcance": "GENERAL"}, Decimal("25")),
            ({"manzana": str(self.manzana_historica.pk)}, Decimal("75")),
            ({"comite": str(self.otro_comite.pk)}, Decimal("75")), ({"concepto": "Cuota"}, Decimal("25")),
            ({"ciudadano": "López C-10"}, Decimal("65")),
            ({"mes": "8", "naturaleza": "COOPERACION", "manzana": str(self.manzana_historica.pk), "ciudadano": "Ana"}, Decimal("40")),
        ]
        for params, esperado in casos:
            with self.subTest(params=params):
                self.assertEqual(self.get(params).context["metricas"]["total_recibido"], esperado)

    def test_resumenes_y_territorio_historico(self):
        response = self.get()
        conceptos = list(response.context["conceptos_page"].object_list)
        territorial = next(c for c in conceptos if c["obligacion__concepto_id"] == self.cooperacion.pk)
        self.assertEqual(territorial["total_recibido"], Decimal("75"))
        self.assertEqual(territorial["ciudadanos_distintos"], 2)
        manzanas = list(response.context["manzanas_resumen"])
        self.assertEqual(len(manzanas), 2)
        historica = next(m for m in manzanas if m["manzana_id"] == self.manzana_historica.pk)
        actual_sin_movimientos = next(m for m in manzanas if m["manzana_id"] == self.manzana_actual.pk)
        self.assertEqual(historica["manzana_id"], self.manzana_historica.pk)
        self.assertEqual(historica["promedio_participante"], Decimal("37.5"))
        self.assertEqual(actual_sin_movimientos["total_recibido"], Decimal("0.00"))
        self.assertEqual(actual_sin_movimientos["cantidad_abonos"], 0)
        self.assertEqual(response.context["fila_general"]["total_recibido"], Decimal("25"))
        self.assertEqual(response.context["fila_general"]["ciudadanos_distintos"], 1)
        self.assertNotEqual(historica["manzana_id"], self.ana.manzana_id)

    def test_alcance_y_manzana_global_controlan_las_filas(self):
        general = self.get({"alcance": "GENERAL"}).context
        self.assertIsNotNone(general["fila_general"])
        self.assertEqual(general["manzanas_resumen"], [])
        territorial = self.get({"alcance": "MANZANA"}).context
        self.assertIsNone(territorial["fila_general"])
        self.assertEqual(len(territorial["manzanas_resumen"]), 2)
        seleccionada = self.get({"manzana": str(self.manzana_historica.pk)}).context
        self.assertIsNone(seleccionada["fila_general"])
        self.assertEqual([m["manzana_id"] for m in seleccionada["manzanas_resumen"]], [self.manzana_historica.pk])

    def test_inactivas_validacion_metricas_y_estado_sin_movimientos(self):
        inactiva = Manzana.objects.create(nombre="Manzana antigua", activa=False)
        contexto = self.get().context
        self.assertNotIn(inactiva.pk, [m["manzana_id"] for m in contexto["manzanas_resumen"]])
        contexto = self.get({"incluir_manzanas_inactivas": "1"}).context
        fila = next(m for m in contexto["manzanas_resumen"] if m["manzana_id"] == inactiva.pk)
        self.assertFalse(fila["activa"])
        self.assertEqual(fila["promedio_participante"], Decimal("0.00"))
        self.assertEqual(contexto["manzanas_mostradas"], 3)
        self.assertEqual(contexto["manzanas_sin_movimientos"], 2)
        self.assertEqual(contexto["total_territorial_recibido"], Decimal("75"))
        self.assertFalse(self.get({"incluir_manzanas_inactivas": "tal-vez"}).context["incluir_manzanas_inactivas"])

    def test_ordenamientos_territoriales(self):
        tercera = Manzana.objects.create(nombre="A primera")
        concepto = ConceptoTesoreria.objects.create(
            naturaleza="PAGO", alcance="MANZANA", manzana=tercera, comite=self.comite,
            concepto="Obra", monto_individual=Decimal("100"), fecha=date(2026, 8, 3),
        )
        obligacion = ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=self.ana, monto_asignado=Decimal("100"))
        Abono.objects.create(obligacion=obligacion, monto=Decimal("80"), fecha=date(2026, 8, 4))
        esperados = {
            "monto": [tercera.pk, self.manzana_historica.pk, self.manzana_actual.pk],
            "ciudadanos": [self.manzana_historica.pk, tercera.pk, self.manzana_actual.pk],
            "movimientos": [self.manzana_historica.pk, tercera.pk, self.manzana_actual.pk],
            "nombre": [tercera.pk, self.manzana_actual.pk, self.manzana_historica.pk],
        }
        for orden, ids in esperados.items():
            with self.subTest(orden=orden):
                filas = self.get({"orden_manzanas": orden}).context["manzanas_resumen"]
                self.assertEqual([fila["manzana_id"] for fila in filas], ids)
        self.assertEqual(self.get({"orden_manzanas": "invalido"}).context["orden_manzanas_actual"], "monto")

    def test_agregacion_territorial_mantiene_tres_consultas(self):
        filtros = {
            "mes": "todos", "anio": "todos", "naturaleza": "todos", "alcance": "todos",
            "manzana": "todas", "comite": "todos", "concepto": "", "ciudadano": "",
        }
        with self.assertNumQueries(3):
            filas, general = _resumen_territorial(abonos_filtrados({}), filtros, False, "monto")
        self.assertEqual(len(filas), 2)
        self.assertEqual(general["total_recibido"], Decimal("25"))
        Manzana.objects.bulk_create([Manzana(nombre=f"Extra {i}") for i in range(20)])
        with self.assertNumQueries(3):
            filas, general = _resumen_territorial(abonos_filtrados({}), filtros, False, "monto")
        self.assertEqual(len(filas), 22)

    def test_movimientos_y_mayores_estan_ordenados_y_filtrados(self):
        response = self.get({"naturaleza": "COOPERACION"})
        self.assertEqual([a.pk for a in response.context["movimientos_page"]], [self.a3.pk, self.a2.pk])
        mayores = list(response.context["mayores_aportaciones"])
        self.assertEqual(mayores[0]["obligacion__ciudadano_id"], self.ana.pk)
        self.assertEqual(mayores[0]["total_abonado"], Decimal("40"))

    def test_csv_columnas_etiquetas_filtros_y_todas_las_paginas(self):
        obligacion = self.a1.obligacion
        for i in range(30):
            Abono.objects.create(obligacion=obligacion, monto=Decimal("1"), fecha=date(2026, 7, 21))
        self.client.login(username="consulta", password="pw")
        response = self.client.get(reverse("exportar_aportaciones_csv"), {"naturaleza": "PAGO", "page": "2"})
        texto = response.content.decode("utf-8-sig")
        self.assertIn("ID de abono,Fecha,Ciudadano,Nombre,Apellido paterno", texto)
        self.assertIn("Toda la comunidad", texto)
        self.assertIn(",Pago,Cuota general,", texto)
        self.assertEqual(len(texto.splitlines()), 32)

    def test_renderiza_cuatro_tarjetas_con_jerarquia_y_datos(self):
        response = self.get()
        self.assertContains(response, 'data-analytics-card=', count=4)
        textos = (
            ("Aportaciones por concepto", "Agrupa el dinero recibido por concepto, naturaleza y territorio."),
            ("Resumen por manzana", "Consulta las aportaciones registradas para cada territorio."),
            ("Movimientos recientes", "Consulta los últimos abonos registrados en Tesorería."),
            ("Mayores aportaciones registradas", "Consulta los ciudadanos con mayor monto abonado dentro de los filtros seleccionados."),
        )
        for titulo, descripcion in textos:
            self.assertContains(response, titulo)
            self.assertContains(response, descripcion)
        self.assertContains(response, "Cuota general")
        self.assertContains(response, "Ana López Ríos")
        self.assertContains(response, "Toda la comunidad")
        self.assertContains(response, reverse("tesoreria_concepto_detalle", args=[self.pago.pk]))
        self.assertContains(response, reverse("perfil_ciudadano", args=[self.ana.pk]))
        self.assertContains(response, reverse("exportar_aportaciones_csv"))
        self.assertContains(response, 'name="naturaleza"')
        self.assertNotContains(response, "Generar obligaciones")
        self.assertNotContains(response, "Acreditar abono")

    def test_estados_vacios_son_especificos(self):
        Abono.objects.all().delete()
        response = self.get()
        for mensaje in (
            "No hay aportaciones agrupadas por concepto para los filtros seleccionados.",
            "Sin movimientos registrados",
            "No hay movimientos recientes con los filtros seleccionados.",
            "No se encontraron ciudadanos con aportaciones para los filtros seleccionados.",
        ):
            self.assertContains(response, mensaje)

    def test_componentes_analiticos_admiten_opcionales_ausentes(self):
        from django.template.loader import render_to_string

        header = render_to_string("dashboard/components/analytics/section_header.html", {
            "section_id": "demo", "title": "Demo", "description": "Descripción",
        })
        metrics = render_to_string("dashboard/components/analytics/section_metrics.html", {"title": "Demo"})
        self.assertIn("Demo", header)
        self.assertNotIn("analytics-card__controls", header)
        self.assertNotIn("analytics-card__metrics", metrics)

    def test_controles_locales_validan_limites_y_son_independientes(self):
        for limite in (5, 10, 20, 50, 100):
            with self.subTest(limite=limite):
                self.assertEqual(self.get({"limite_ciudadanos": str(limite)}).context["limite_ciudadanos_actual"], limite)
        for invalido in ("7", "-5", "texto"):
            with self.subTest(invalido=invalido):
                self.assertEqual(self.get({"limite_ciudadanos": invalido}).context["limite_ciudadanos_actual"], 10)
        for limite in (10, 25, 50, 100):
            with self.subTest(limite=limite):
                self.assertEqual(self.get({"limite_movimientos": str(limite)}).context["limite_movimientos_actual"], limite)
        contexto = self.get({"limite_ciudadanos": "20", "orden_ciudadanos": "reciente", "limite_movimientos": "50"}).context
        self.assertEqual(contexto["limite_ciudadanos_actual"], 20)
        self.assertEqual(contexto["orden_ciudadanos_actual"], "reciente")
        self.assertEqual(contexto["limite_movimientos_actual"], 50)

    def test_totales_visibles_y_contexto_seguro_de_formularios(self):
        response = self.get({
            "naturaleza": "COOPERACION", "limite_ciudadanos": "5",
            "orden_ciudadanos": "movimientos", "limite_movimientos": "10", "desconocido": "no reenviar",
        })
        self.assertEqual(response.context["monto_ciudadanos_visible"], Decimal("75"))
        self.assertEqual(response.context["aportaciones_ciudadanos_visibles"], 2)
        self.assertEqual(response.context["monto_movimientos_visible"], Decimal("75"))
        nombres = {campo["name"] for campo in response.context["campos_control_movimientos"]}
        self.assertIn("limite_ciudadanos", nombres)
        self.assertIn("orden_ciudadanos", nombres)
        self.assertNotIn("desconocido", nombres)

    def test_csv_no_se_limita_por_controles_locales(self):
        self.client.login(username="consulta", password="pw")
        response = self.client.get(reverse("exportar_aportaciones_csv"), {
            "limite_ciudadanos": "5", "orden_ciudadanos": "reciente", "limite_movimientos": "10",
            "orden_manzanas": "nombre", "incluir_manzanas_inactivas": "1",
        })
        self.assertEqual(len(response.content.decode("utf-8-sig").splitlines()), 4)
