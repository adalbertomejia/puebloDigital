from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import Comite, UsuarioApp
from apps.core.models import Ciudadano
from .models import Abono, ConceptoTesoreria, ObligacionCiudadano


class RecibosTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username='tesorero-recibos')
        self.comite = Comite.objects.create(nombre='Agua recibos', tipo='AGUA')
        UsuarioApp.objects.create(user=self.usuario, comite=self.comite, rol='TESORERO')
        ciudadano = Ciudadano.objects.create(nombre='Ana', apellido_paterno='Recibos', numero_contrato='C-123')
        concepto = ConceptoTesoreria.objects.create(comite=self.comite, concepto='Cuota agua recibos', naturaleza='PAGO', monto_individual=100)
        self.obligacion = ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=ciudadano, monto_asignado=100)
        self.abono = self.obligacion.acreditar(25, usuario=self.usuario)
        self.url = reverse('recibo_abono', args=[self.abono.folio_recibo])
        self.client.force_login(self.usuario)

    def test_recibo_existente_y_reimpresion_no_crean_movimientos(self):
        cantidad = Abono.objects.count()
        for _ in range(2):
            respuesta = self.client.get(self.url)
            self.assertEqual(respuesta.status_code, 200)
            for texto in ('Ana Recibos', 'C-123', 'Cuota agua recibos', 'Agua recibos', '25', self.abono.folio_recibo, 'Conserve este recibo', 'recibo-80mm.css'):
                self.assertContains(respuesta, texto)
        self.assertEqual(Abono.objects.count(), cantidad)
        segundo = self.obligacion.acreditar(10, usuario=self.usuario)
        self.assertNotEqual(self.abono.folio_recibo, segundo.folio_recibo)

    def test_busqueda_por_folio_y_folios_invalidos(self):
        url = reverse('buscar_recibo')
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get(url, {'folio': self.abono.folio_recibo.lower()}), 'Conserve este recibo')
        for folio in ('desconocido', 'PD-A-9999999999999999999', 'PD-A-' + '9' * 5000):
            self.assertEqual(self.client.get(url, {'folio': folio}).status_code, 404)

    def test_recibo_ajeno_y_cargo_inactivo_no_autorizan_acceso(self):
        otro = Comite.objects.create(nombre='Comité ajeno', tipo='FERIA')
        concepto = ConceptoTesoreria.objects.create(comite=otro, concepto='Privado', naturaleza='PAGO', monto_individual=100)
        obligacion = ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=self.obligacion.ciudadano, monto_asignado=100)
        ajeno = obligacion.acreditar(15)
        self.assertEqual(self.client.get(reverse('recibo_abono', args=[ajeno.folio_recibo])).status_code, 404)
        self.assertEqual(self.client.get(reverse('buscar_recibo'), {'folio': ajeno.folio_recibo}).status_code, 404)
        UsuarioApp.objects.filter(user=self.usuario).update(activo=False)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_anonimo_requiere_login_y_presidente_puede_reimprimir(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        UsuarioApp.objects.filter(user=self.usuario).update(rol='PRESIDENTE')
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_abono_nuevo_ofrece_recibo_sin_cambiar_redireccion(self):
        respuesta = self.client.post(reverse('acreditar_obligacion', args=[self.obligacion.pk]), {'monto': '10', 'fecha': '2026-10-29', 'notas': '', 'referencia': ''}, follow=True)
        nuevo = Abono.objects.latest('pk')
        self.assertEqual(Abono.objects.count(), 2)
        self.assertContains(respuesta, reverse('recibo_abono', args=[nuevo.folio_recibo]))
        self.assertContains(respuesta, 'Imprimir recibo')
