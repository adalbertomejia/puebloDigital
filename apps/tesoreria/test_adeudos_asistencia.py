from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import Comite, UsuarioApp
from apps.core.models import Ciudadano, Manzana
from apps.operacion.models import Faena, Junta, RegistroFaena, AsistenciaJunta
from apps.tesoreria.models import Abono, ConceptoTesoreria, ObligacionCiudadano, RegistroFinanciero
from apps.tesoreria.services import generar_obligaciones_faltantes


class AdeudosAsistenciaTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='presidente-adeudos')
        self.comite = Comite.objects.create(nombre='Faenas comunidad', tipo='OBRAS')
        UsuarioApp.objects.create(user=self.user, comite=self.comite, rol='PRESIDENTE')
        self.ciudadano = Ciudadano.objects.create(nombre='Ana', apellido_paterno='Captura')
        self.otro = Ciudadano.objects.create(nombre='Beto', apellido_paterno='Captura')
        self.faena = Faena.objects.create(comite=self.comite, descripcion='Limpieza', fecha=date(2026, 10, 29))
        self.registro = RegistroFaena.objects.create(faena=self.faena, ciudadano=self.ciudadano)
        self.client.force_login(self.user)

    def guardar(self, monto, *, registro=None, tipo='faena', extra=None, ajax=False):
        registro = registro or self.registro
        evento = registro.faena if tipo == 'faena' else registro.junta
        datos = {f'registro_{registro.pk}_estatus': 'FALTO', f'registro_{registro.pk}_monto_adeudo': monto}
        datos.update(extra or {})
        return self.client.post(reverse(f'captura_asistencia_{tipo}', args=[evento.pk]), datos,
                                **({'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'} if ajax else {}))

    def test_importe_activa_adeudo_y_crea_obligacion_en_su_comite(self):
        respuesta = self.guardar('125.50', ajax=True)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['metrics']['cantidad_adeudos'], 1)
        self.assertEqual(respuesta.json()['metrics']['monto_total_adeudos'], '125.50')
        self.registro.refresh_from_db()
        self.assertTrue(self.registro.genera_adeudo)
        obligacion = ObligacionCiudadano.objects.get()
        self.assertEqual(obligacion.monto_asignado, Decimal('125.50'))
        self.assertEqual(obligacion.concepto.comite, self.comite)
        self.assertEqual(obligacion.concepto.faena, self.faena)
        self.assertEqual(obligacion.creado_por, self.user)
        tesoreria = self.client.get(reverse('tesoreria_operativa'))
        self.assertContains(tesoreria, 'Limpieza')
        self.assertNotContains(tesoreria, reverse('generar_obligaciones_tesoreria', args=[obligacion.concepto_id]))

    def test_repetir_modificar_cancelar_y_reactivar_no_duplica(self):
        self.guardar('50')
        evidencia = RegistroFinanciero.objects.count()
        self.guardar('50')
        self.assertEqual(RegistroFinanciero.objects.count(), evidencia)
        self.guardar('75')
        obligacion = ObligacionCiudadano.objects.get()
        self.assertEqual(obligacion.monto_asignado, 75)
        self.guardar('0')
        self.registro.refresh_from_db()
        obligacion.refresh_from_db()
        self.assertFalse(self.registro.genera_adeudo)
        self.assertEqual(obligacion.estado, 'CANCELADO')
        self.guardar('25')
        obligacion.refresh_from_db()
        self.assertEqual(obligacion.estado, 'PENDIENTE')
        self.assertEqual(obligacion.monto_asignado, 25)
        self.assertEqual(ConceptoTesoreria.objects.count(), 1)
        self.assertEqual(ObligacionCiudadano.objects.count(), 1)

    def test_abonos_impiden_retirar_o_reducir_adeudo_y_se_conserva_recibo(self):
        self.guardar('100')
        obligacion = ObligacionCiudadano.objects.get()
        abono = obligacion.acreditar(40, usuario=self.user)
        for monto in ('0', '39'):
            self.assertEqual(self.guardar(monto, ajax=True).status_code, 400)
            self.registro.refresh_from_db()
            obligacion.refresh_from_db()
            self.assertEqual(self.registro.monto_adeudo, 100)
            self.assertEqual(obligacion.monto_asignado, 100)
        self.assertEqual(self.guardar('40').status_code, 302)
        obligacion.refresh_from_db()
        self.assertEqual(obligacion.estado, 'PAGADO')
        self.assertEqual(Abono.objects.get().pk, abono.pk)
        self.assertContains(self.client.get(reverse('recibo_abono', args=[abono.folio_recibo])), abono.folio_recibo)

    def test_datos_invalidos_no_guardan_asistencia_ni_finanzas(self):
        for monto in ('-1', 'abc', 'NaN', '1.999', '9999999999999999999999'):
            with self.subTest(monto=monto):
                self.assertEqual(self.guardar(monto, ajax=True).status_code, 400)
                self.registro.refresh_from_db()
                self.assertEqual(self.registro.estatus, 'PENDIENTE')
                self.assertFalse(ConceptoTesoreria.objects.exists())
        self.assertEqual(self.guardar('0', extra={f'registro_{self.registro.pk}_genera_adeudo': 'on'}).status_code, 400)

    def test_error_en_segunda_fila_revierte_toda_la_captura(self):
        segundo = RegistroFaena.objects.create(faena=self.faena, ciudadano=self.otro)
        self.assertEqual(self.guardar('25', extra={f'registro_{segundo.pk}_estatus': 'FALTO', f'registro_{segundo.pk}_monto_adeudo': '-2'}, ajax=True).status_code, 400)
        self.registro.refresh_from_db()
        self.assertEqual(self.registro.estatus, 'PENDIENTE')
        self.assertFalse(ObligacionCiudadano.objects.exists())
        self.assertFalse(RegistroFinanciero.objects.exists())

    def test_juntas_comparten_integracion_y_solo_cobran_a_quien_tiene_adeudo(self):
        junta = Junta.objects.create(comite=self.comite, tema='Acuerdos', fecha=date(2026, 10, 29))
        registro = AsistenciaJunta.objects.create(junta=junta, ciudadano=self.ciudadano)
        AsistenciaJunta.objects.create(junta=junta, ciudadano=self.otro)
        self.assertEqual(self.guardar('30', registro=registro, tipo='junta').status_code, 302)
        concepto = ConceptoTesoreria.objects.get()
        self.assertEqual(concepto.junta, junta)
        self.assertEqual(concepto.obligaciones.count(), 1)
        with self.assertRaises(ValidationError):
            generar_obligaciones_faltantes(concepto, usuario=self.user)
        self.assertEqual(concepto.obligaciones.count(), 1)

    def test_guardar_registro_preexistente_repara_vinculo_sin_migrar_datos(self):
        RegistroFaena.objects.filter(pk=self.registro.pk).update(genera_adeudo=True, monto_adeudo=60)
        self.assertEqual(self.guardar('60').status_code, 302)
        self.assertEqual(ObligacionCiudadano.objects.get().monto_asignado, 60)

    def test_evento_sin_comite_rechaza_adeudo_con_mensaje(self):
        admin = get_user_model().objects.create_superuser(username='admin-adeudos', password='temporal')
        self.client.force_login(admin)
        manzana = Manzana.objects.create(nombre='Norte adeudos')
        evento = Faena.objects.create(alcance='MANZANA', manzana=manzana, motivo='Vecinal', descripcion='Sin comité', fecha=date(2026, 10, 29))
        registro = RegistroFaena.objects.create(faena=evento, ciudadano=self.ciudadano)
        response = self.guardar('10', registro=registro, ajax=True)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Asigna un comité', response.json()['error'])
        registro.refresh_from_db()
        self.assertFalse(registro.genera_adeudo)

    def test_comite_ajeno_no_puede_capturar_ni_consultar_adeudo(self):
        self.guardar('25')
        otro = Comite.objects.create(nombre='Otro comité', tipo='AGUA')
        UsuarioApp.objects.filter(user=self.user).update(comite=otro)
        self.assertEqual(self.guardar('90', ajax=True).status_code, 404)
        concepto = ConceptoTesoreria.objects.get()
        self.assertEqual(self.client.get(reverse('tesoreria_concepto_detalle', args=[concepto.pk])).status_code, 404)
        self.assertEqual(ObligacionCiudadano.objects.get().monto_asignado, 25)

    def test_guardar_fila_convencional_no_modifica_otras_filas(self):
        segundo = RegistroFaena.objects.create(faena=self.faena, ciudadano=self.otro)
        response = self.guardar('25', extra={
            'registro_fila': str(self.registro.pk),
            f'registro_{segundo.pk}_estatus': 'FALTO',
            f'registro_{segundo.pk}_monto_adeudo': '90',
        })
        self.assertEqual(response.status_code, 302)
        segundo.refresh_from_db()
        self.assertEqual(segundo.estatus, 'PENDIENTE')
        self.assertFalse(segundo.genera_adeudo)
        self.assertEqual(ObligacionCiudadano.objects.count(), 1)
