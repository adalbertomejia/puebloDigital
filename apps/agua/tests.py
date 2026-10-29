from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse
from apps.agua.models import Toma
from apps.comites.models import Comite, UsuarioApp
from apps.core.models import Ciudadano
from apps.tesoreria.models import ConceptoTesoreria, ObligacionCiudadano, RegistroFinanciero
from apps.tesoreria.services import generar_obligaciones_faltantes


class CuotasMensualesAguaTests(TestCase):
    def setUp(self):
        self.comite = Comite.objects.create(nombre="Agua", tipo="AGUA")
        self.usuario = get_user_model().objects.create_user(username="tesorero-agua-mensual")
        self.presidente = get_user_model().objects.create_user(username="presidente-agua-mensual")
        for usuario, rol in ((self.usuario,"TESORERO"),(self.presidente,"PRESIDENTE")):
            UsuarioApp.objects.create(user=usuario, comite=self.comite, rol=rol)
        self.ciudadano = Ciudadano.objects.create(nombre="Ana", apellido_paterno="Prueba", numero_contrato="C-001")
        self.toma = Toma.objects.create(ciudadano=self.ciudadano, numero_toma="T-099", costo_anual=999)
        for estado in ("SUSPENDIDA", "CANCELADA"):
            c = Ciudadano.objects.create(nombre=estado, apellido_paterno="Prueba")
            Toma.objects.create(ciudadano=c, numero_toma=estado, estado=estado)
        Ciudadano.objects.create(nombre="Sin toma", apellido_paterno="Prueba")
        self.client.force_login(self.usuario)

    def crear(self, periodo="2026-10", monto="70"):
        return self.client.post(reverse("crear_cuota_mensual_agua"), {"periodo": periodo, "monto": monto, "descripcion": "Servicio mensual"})

    def test_cuota_uniforme_solo_activas_con_referencia_y_autoria(self):
        self.assertEqual(self.crear().status_code,302)
        concepto=ConceptoTesoreria.objects.get(origen="AGUA")
        self.assertEqual(concepto.periodo_agua,date(2026,10,1))
        obligacion=concepto.obligaciones.get()
        self.assertEqual(obligacion.monto_asignado,Decimal("70"))
        self.assertEqual(obligacion.toma,self.toma)
        self.assertEqual(obligacion.numero_toma_registrado,"T-099")
        self.assertEqual(obligacion.numero_contrato_registrado,"C-001")
        self.assertEqual(obligacion.creado_por,self.usuario)
        self.assertEqual(RegistroFinanciero.objects.filter(comite=self.comite).count(),2)
        self.toma.refresh_from_db()
        self.assertEqual(self.toma.costo_anual,999)
        self.assertEqual(self.toma.numero_toma,"T-099")

    def test_presidente_puede_generar_y_periodo_repetido_no_duplica(self):
        self.client.force_login(self.presidente)
        self.assertEqual(self.crear().status_code,302)
        self.assertEqual(self.crear(monto="80").status_code,200)
        self.assertEqual(ConceptoTesoreria.objects.filter(origen="AGUA").count(),1)
        self.assertEqual(ObligacionCiudadano.objects.count(),1)
        self.assertEqual(self.crear("2026-11").status_code,302)
        self.assertEqual(ObligacionCiudadano.objects.count(),2)

    def test_suspender_no_borra_adeudos_ni_abonos_y_no_genera_mes_nuevo(self):
        self.crear()
        obligacion=ObligacionCiudadano.objects.get()
        obligacion.acreditar(20,usuario=self.usuario)
        self.toma.estado="SUSPENDIDA"
        self.toma.save()
        self.assertEqual(self.crear("2026-11").status_code,302)
        self.assertEqual(ObligacionCiudadano.objects.count(),1)
        self.assertEqual(obligacion.saldo_pendiente,Decimal("50"))
        self.assertEqual(obligacion.abonos.count(),1)
        with self.assertRaises(ProtectedError):
            self.toma.delete()

    def test_cambiar_numeros_no_reescribe_identificadores_historicos(self):
        self.crear()
        self.toma.numero_toma="T-NUEVO"
        self.toma.save()
        self.ciudadano.numero_contrato="C-NUEVO"
        self.ciudadano.save()
        o=ObligacionCiudadano.objects.get()
        self.assertEqual(o.numero_toma_registrado,"T-099")
        self.assertEqual(o.numero_contrato_registrado,"C-001")

    def test_periodo_y_monto_invalidos_no_crean_datos(self):
        for periodo,monto in (("2026-13","70"),("2026-10","0"),("2026-10","-1"),("","70")):
            self.assertEqual(self.crear(periodo,monto).status_code,200)
        self.assertFalse(ConceptoTesoreria.objects.exists())
        self.assertFalse(RegistroFinanciero.objects.exists())

    def test_otro_comite_no_ve_agua_ni_crea_cuotas(self):
        otro=Comite.objects.create(nombre="Feria",tipo="FERIA")
        u=get_user_model().objects.create_user(username="tesorero-feria-mensual")
        UsuarioApp.objects.create(user=u,comite=otro,rol="TESORERO")
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse("control_agua")).status_code,404)
        self.assertEqual(self.crear().status_code,404)
        self.assertFalse(ConceptoTesoreria.objects.exists())

    def test_configuracion_ambigua_falla_sin_asignar_tomas(self):
        Comite.objects.create(nombre="Otra Agua",tipo="AGUA")
        self.assertEqual(self.crear().status_code,404)
        self.assertFalse(ConceptoTesoreria.objects.exists())
        self.assertEqual(Toma.objects.get(pk=self.toma.pk).ciudadano_id,self.ciudadano.pk)

    def test_busqueda_por_contrato_y_canceladas(self):
        response=self.client.get(reverse("control_agua"),{"q":"C-001"})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"T-099")
        self.assertContains(response,"C-001")
        response=self.client.get(reverse("control_agua"),{"estado":"canceladas"})
        self.assertEqual(response.context["tomas"].paginator.count,1)
        self.assertEqual(response.context["tomas"][0].estado,"CANCELADA")

    def test_regeneracion_es_idempotente_y_mes_no_se_puede_cambiar(self):
        self.crear()
        c=ConceptoTesoreria.objects.get()
        self.assertEqual(generar_obligaciones_faltantes(c,usuario=self.presidente).creados,0)
        self.assertEqual(c.obligaciones.get().creado_por,self.usuario)
        c.periodo_agua=date(2026,11,1)
        with self.assertRaises(ValidationError):
            c.save()

    def test_concepto_agua_anterior_sin_periodo_no_genera_cobros(self):
        c=ConceptoTesoreria.objects.create(comite=self.comite,naturaleza="PAGO",concepto="Anterior",monto_individual=100)
        ConceptoTesoreria.objects.filter(pk=c.pk).update(origen="AGUA")
        c.refresh_from_db()
        with self.assertRaises(ValidationError):
            generar_obligaciones_faltantes(c)
        self.assertFalse(c.obligaciones.exists())

    def test_estado_de_toma_es_la_regla_de_cobro_y_no_el_estado_del_ciudadano(self):
        self.ciudadano.activo=False
        self.ciudadano.save()
        self.assertEqual(self.crear().status_code,302)
        self.assertEqual(ObligacionCiudadano.objects.get().ciudadano_id,self.ciudadano.pk)

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracionAguaExistenteTests(TransactionTestCase):
    def test_migracion_conserva_identificadores_y_relaciones_sin_backfill(self):
        executor=MigrationExecutor(connection)
        destinos=executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([("tesoreria","0002_autoria_y_actividad_financiera")])
            apps=executor.loader.project_state([("tesoreria","0002_autoria_y_actividad_financiera")]).apps
            c=apps.get_model("core","Ciudadano").objects.create(nombre="Anterior",apellido_paterno="Agua",numero_contrato="000-C-1")
            t=apps.get_model("agua","Toma").objects.create(ciudadano_id=c.pk,numero_toma="000-T-9",costo_anual=800)
            comite=apps.get_model("comites","Comite").objects.create(nombre="Agua previa",tipo="AGUA")
            concepto=apps.get_model("tesoreria","ConceptoTesoreria").objects.create(comite_id=comite.pk,concepto="Anterior",origen="AGUA",naturaleza="PAGO",monto_individual=66)
            o=apps.get_model("tesoreria","ObligacionCiudadano").objects.create(ciudadano_id=c.pk,concepto_id=concepto.pk,monto_asignado=66)
            pago=apps.get_model("tesoreria","Pago").objects.create(ciudadano_id=c.pk,toma_id=t.pk,comite_id=comite.pk,monto=20,fecha=date(2026,9,1),concepto="Anterior")
        finally:
            MigrationExecutor(connection).migrate(destinos)
        from apps.tesoreria.models import Pago
        self.assertEqual(Ciudadano.objects.get(pk=c.pk).numero_contrato,"000-C-1")
        toma=Toma.objects.get(pk=t.pk)
        self.assertEqual(toma.numero_toma,"000-T-9")
        self.assertEqual(toma.ciudadano_id,c.pk)
        self.assertEqual(toma.costo_anual,800)
        self.assertEqual(Pago.objects.get(pk=pago.pk).toma_id,t.pk)
        self.assertEqual(Pago.objects.get(pk=pago.pk).monto,Decimal("20"))
        obligacion=ObligacionCiudadano.objects.get(pk=o.pk)
        self.assertEqual(obligacion.monto_asignado,Decimal("66"))
        self.assertIsNone(obligacion.toma_id)
        self.assertEqual(obligacion.numero_toma_registrado,"")
        self.assertIsNone(ConceptoTesoreria.objects.get(pk=concepto.pk).periodo_agua)
