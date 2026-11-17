"""End-to-end authorization regressions using only synthetic community data."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import Comite, PerfilAcceso
from apps.core.autorizacion import permiso_global_de_modelo
from apps.core.models import Ciudadano, Manzana
from apps.operacion.models import Faena, RegistroFaena
from apps.tesoreria.autorizacion import limitar_finanzas
from apps.tesoreria.models import Abono, ConceptoTesoreria, ObligacionCiudadano


class ConsolidacionTests(TestCase):
    def setUp(self):
        self.secretaria = self.cuenta('secretaria')
        self.secretaria.user_permissions.add(Permission.objects.get(codename='operar_secretaria_central'))
        self.responsable = self.cuenta('responsable')
        self.a = Manzana.objects.create(nombre='Centro', responsable=self.responsable.perfil_acceso.ciudadano)
        c = self.responsable.perfil_acceso.ciudadano
        c.manzana = self.a
        c.save()
        self.b = Manzana.objects.create(nombre='Norte')
        self.local = Ciudadano.objects.create(nombre='Ana', apellido_paterno='Local', manzana=self.a)
        self.ajeno = Ciudadano.objects.create(nombre='Luis', apellido_paterno='Reservado', manzana=self.b)
        self.comite = Comite.objects.create(nombre='Delegación')
        self.general = self.concepto('General')
        self.territorial = self.concepto('Centro', self.a)
        self.otro = self.concepto('Norte', self.b)
        self.obligaciones = [ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=self.local, monto_asignado=100) for concepto in (self.general, self.territorial, self.otro)]

    def cuenta(self, nombre):
        u = get_user_model().objects.create_user(nombre)
        c = Ciudadano.objects.create(nombre=nombre, apellido_paterno='Operador')
        PerfilAcceso.objects.create(user=u, ciudadano=c)
        return u

    def concepto(self, nombre, manzana=None):
        return ConceptoTesoreria.objects.create(concepto=nombre, naturaleza="PAGO", comite=self.comite, fecha=date(2026, 1, 1), monto_individual=100, alcance='MANZANA' if manzana else 'GENERAL', manzana=manzana)

    def test_secretaria_global_sin_privilegios_tecnicos_ni_financieros(self):
        self.client.force_login(self.secretaria)
        self.assertContains(self.client.get(reverse('padron_ciudadanos')), 'Luis Reservado')
        self.assertFalse(self.secretaria.is_staff)
        self.assertFalse(self.secretaria.is_superuser)
        for permiso in ('core.add_ciudadano', 'core.change_ciudadano', 'operacion.add_faena', 'operacion.change_registrofaena'):
            self.assertTrue(permiso_global_de_modelo(self.secretaria, permiso))
        for permiso in ('core.delete_ciudadano', 'auth.change_user', 'auth.change_permission'):
            self.assertFalse(permiso_global_de_modelo(self.secretaria, permiso))
        self.assertEqual(self.client.get(reverse('tesoreria_operativa')).status_code, 404)

    def test_secretaria_finanzas_requiere_concesion_explicita(self):
        self.secretaria.user_permissions.add(Permission.objects.get(codename='consultar_finanzas_centrales'))
        self.client.force_login(self.secretaria)
        self.assertEqual(self.client.get(reverse('tesoreria_operativa')).status_code, 200)
        self.assertEqual(self.client.post(reverse('acreditar_obligacion', args=[self.obligaciones[0].pk]), {'monto': 1}).status_code, 404)

    def test_secretaria_sin_identidad_o_inactiva_no_recibe_alcance(self):
        self.secretaria.perfil_acceso.delete()
        self.assertFalse(permiso_global_de_modelo(self.secretaria, 'core.view_ciudadano'))
        self.secretaria.is_active = False
        self.assertFalse(permiso_global_de_modelo(self.secretaria, 'core.view_ciudadano'))

    def test_responsable_no_hereda_permisos_globales(self):
        self.responsable.user_permissions.set(Permission.objects.all())
        for permiso in ('core.view_ciudadano', 'core.add_ciudadano', 'core.change_ciudadano', 'core.delete_ciudadano', 'operacion.change_faena'):
            self.assertFalse(permiso_global_de_modelo(self.responsable, permiso))
        self.assertEqual(list(Ciudadano.objects.visibles_para(self.responsable).filter(pk=self.ajeno.pk)), [])
        self.assertEqual(list(limitar_finanzas(ObligacionCiudadano.objects.all(), self.responsable, 'concepto__comite_id')), [self.obligaciones[1]])

    def test_responsable_no_modifica_padron_por_post(self):
        self.client.force_login(self.responsable)
        for nombre in ("editar_ciudadano_operativo", "estado_ciudadano", "eliminar_ciudadano"):
            with self.subTest(nombre=nombre):
                self.assertEqual(self.client.post(reverse(nombre, args=[self.local.pk]), {}).status_code, 404)

    def test_finanzas_territoriales_urls_post_csv_y_recibo(self):
        self.client.force_login(self.responsable)
        for i in (0, 2):
            self.assertEqual(self.client.post(reverse('acreditar_obligacion', args=[self.obligaciones[i].pk]), {'monto': 10}).status_code, 404)
            self.assertEqual(self.client.get(reverse('tesoreria_concepto_detalle', args=[self.obligaciones[i].concepto_id])).status_code, 404)
        response = self.client.post(reverse('acreditar_obligacion', args=[self.obligaciones[1].pk]), {'monto': '25', 'fecha': '2026-01-02', 'referencia': 'CENTRO-1'})
        self.assertEqual(response.status_code, 302)
        abono = Abono.objects.get()
        self.assertEqual(abono.creado_por, self.responsable)
        self.assertEqual(abono.monto, Decimal('25'))
        self.assertEqual(self.client.get(reverse('recibo_abono', args=[abono.folio_recibo])).status_code, 200)
        self.assertEqual(Abono.objects.count(), 1)
        self.assertEqual(self.client.get(reverse('exportar_obligaciones_tesoreria_csv', args=[self.territorial.pk])).status_code, 200)

    def test_servicio_denega_cobro_general_y_ajeno(self):
        for i in (0, 2):
            with self.assertRaises(ValidationError):
                self.obligaciones[i].acreditar(10, usuario=self.responsable)
        self.assertFalse(Abono.objects.exists())

    def test_mudanza_preserva_historial_y_restringe_todas_las_consultas(self):
        abono = self.obligaciones[1].acreditar(10, usuario=self.responsable)
        self.local.manzana = self.b
        self.local.save()
        with self.assertRaises(ValidationError):
            self.obligaciones[1].acreditar(10, usuario=self.responsable)
        abono.refresh_from_db()
        self.assertEqual(abono.creado_por, self.responsable)
        self.assertEqual(abono.obligacion.concepto, self.territorial)
        self.client.force_login(self.responsable)
        for nombre in ('tesoreria_concepto_detalle', 'exportar_obligaciones_tesoreria_csv'):
            respuesta = self.client.get(reverse(nombre, args=[self.territorial.pk]))
            self.assertNotContains(respuesta, 'Ana Local')
        respuesta = self.client.get(reverse('tesoreria_operativa'))
        self.assertEqual(respuesta.context['metricas']['total_asignado'], 0)
        self.assertEqual(self.client.get(reverse('recibo_abono', args=[abono.folio_recibo])).status_code, 404)

    def test_responsable_no_crea_modifica_ni_genera_conceptos(self):
        self.client.force_login(self.responsable)
        for nombre in ('editar_concepto_tesoreria', 'eliminar_concepto_tesoreria', 'generar_obligaciones_tesoreria'):
            self.assertIn(self.client.post(reverse(nombre, args=[self.territorial.pk]), {}).status_code, (302, 404))
        self.assertEqual(ConceptoTesoreria.objects.count(), 3)
        self.assertEqual(ObligacionCiudadano.objects.count(), 3)

    def enviar_ciudadano(self, nombre, datos, pk=None):
        url = reverse(nombre, args=[pk] if pk else [])
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 200)
        return self.client.post(url, dict(datos, operation_token=respuesta.context['operation_token']))

    def test_secretaria_alta_edicion_mudanza_baja_reactivacion_historial(self):
        from apps.core.models import CambioManzanaCiudadano
        self.client.force_login(self.secretaria)
        datos = {'nombre': 'Eva', 'apellido_paterno': 'Nueva', 'sexo': 'NO_ESPECIFICADO', 'edad': 30, 'manzana': self.a.pk}
        r = self.enviar_ciudadano('crear_ciudadano_operativo', datos)
        self.assertEqual(r.status_code, 302)
        c = Ciudadano.objects.get(nombre='Eva')
        obligacion = ObligacionCiudadano.objects.create(ciudadano=c, concepto=self.territorial, monto_asignado=100)
        abono = obligacion.acreditar(10, usuario=self.responsable)
        datos.update(manzana=self.b.pk)
        r = self.enviar_ciudadano('editar_ciudadano_operativo', datos, c.pk)
        self.assertEqual(r.status_code, 302)
        cambio = CambioManzanaCiudadano.objects.get(ciudadano=c)
        self.assertEqual((cambio.anterior_id, cambio.nueva_id, cambio.usuario_id), (self.a.pk, self.b.pk, self.secretaria.pk))
        obligacion.refresh_from_db()
        self.assertEqual(obligacion.concepto_id, self.territorial.pk)
        self.assertEqual(obligacion.total_abonado, 10)
        self.assertEqual(abono.creado_por, self.responsable)
        for activo in (True, False):
            r = self.enviar_ciudadano('estado_ciudadano', {'motivo': 'Solicitud documentada', 'fecha': '2026-01-01', 'activo_anterior': str(activo)}, c.pk)
            self.assertEqual(r.status_code, 302)
            c.refresh_from_db()
            self.assertEqual(c.activo, not activo)
        self.assertEqual(c.cambios_estado.count(), 2)
        r = self.client.get(reverse('perfil_ciudadano', args=[c.pk]))
        self.assertContains(r, 'Cambios de manzana')
        self.assertTrue(r.context['puede_editar'])

    def test_secretaria_crea_evento_general_y_responsable_evento_local(self):
        for usuario, alcance, manzana in ((self.secretaria, 'GENERAL', ''), (self.responsable, 'MANZANA', self.a.pk)):
            self.client.force_login(usuario)
            r = self.client.post(reverse('crear_faena_operativa'), {'comite': self.comite.pk, 'fecha': '2026-01-01', 'descripcion': 'Limpieza ' + alcance, 'alcance': alcance, 'manzana': manzana, 'motivo': 'Trabajo comunitario', 'estado': 'PROGRAMADA'})
            self.assertEqual(r.status_code, 302)
            evento = Faena.objects.get(descripcion='Limpieza ' + alcance)
            self.assertEqual(evento.manzana_id, self.a.pk if manzana else None)

    def test_flujo_integral_ciudadano_evento_asistencia_adeudo_abono_recibo(self):
        self.client.force_login(self.secretaria)
        r = self.enviar_ciudadano('crear_ciudadano_operativo', {'nombre': 'Eva', 'apellido_paterno': 'Integral', 'sexo': 'NO_ESPECIFICADO', 'edad': 30, 'manzana': self.a.pk})
        self.assertEqual(r.status_code, 302)
        ciudadano = Ciudadano.objects.get(nombre='Eva')
        self.client.force_login(self.responsable)
        self.assertContains(self.client.get(reverse('perfil_ciudadano', args=[ciudadano.pk])), 'Eva Integral')
        r = self.client.post(reverse('crear_faena_operativa'), {'comite': self.comite.pk, 'fecha': '2026-01-01', 'descripcion': 'Faena integral', 'alcance': 'MANZANA', 'manzana': self.a.pk, 'motivo': 'Trabajo comunitario', 'estado': 'PROGRAMADA'})
        self.assertEqual(r.status_code, 302)
        evento = Faena.objects.get(descripcion='Faena integral')
        self.assertEqual(self.client.post(reverse('generar_registros_faena', args=[evento.pk])).status_code, 302)
        registro = RegistroFaena.objects.get(faena=evento, ciudadano=ciudadano)
        self.assertFalse(RegistroFaena.objects.filter(faena=evento, ciudadano=self.ajeno).exists())
        r = self.client.post(reverse('captura_asistencia_faena', args=[evento.pk]), {f'registro_{registro.pk}_estatus': 'ASISTIO', f'registro_{registro.pk}_monto_adeudo': '0'})
        self.assertEqual(r.status_code, 302, r.context and r.context.get('error_captura'))
        # Territorial events without a convening committee do not create debts.
        # Use an existing, explicitly administered territorial concept instead.
        self.secretaria.user_permissions.add(Permission.objects.get(codename='operar_finanzas_centrales'))
        self.client.force_login(self.secretaria)
        self.assertEqual(self.client.post(reverse('generar_obligaciones_tesoreria', args=[self.territorial.pk])).status_code, 302)
        obligacion = ObligacionCiudadano.objects.get(concepto=self.territorial, ciudadano=ciudadano)
        self.client.force_login(self.responsable)
        self.assertEqual(obligacion.concepto.manzana_id, self.a.pk)
        r = self.client.post(reverse('acreditar_obligacion', args=[obligacion.pk]), {'monto': '20', 'fecha': '2026-01-02'})
        self.assertEqual(r.status_code, 302)
        abono = Abono.objects.get(obligacion=obligacion)
        recibo = self.client.get(reverse('recibo_abono', args=[abono.folio_recibo]))
        self.assertContains(recibo, abono.folio_recibo)
        self.assertEqual(Abono.objects.filter(obligacion=obligacion).count(), 1)
        self.secretaria.user_permissions.add(Permission.objects.get(codename='consultar_finanzas_centrales'))
        self.client.force_login(self.secretaria)
        expediente = self.client.get(reverse('perfil_ciudadano', args=[ciudadano.pk]))
        self.assertContains(expediente, 'Faena integral')
        self.assertEqual(expediente.context['obligaciones_page'].paginator.count, 1)
        self.assertEqual(expediente.context['abonos_page'].paginator.count, 1)

    def test_responsable_no_crea_ciudadano_ni_evento_de_otro_territorio(self):
        self.client.force_login(self.responsable)
        self.assertEqual(self.client.post(reverse('crear_ciudadano_operativo'), {'nombre': 'Intruso'}).status_code, 404)
        r = self.client.post(reverse('crear_faena_operativa'), {'comite': self.comite.pk, 'fecha': '2026-01-01', 'descripcion': 'Evento ajeno', 'alcance': 'MANZANA', 'manzana': self.b.pk, 'motivo': 'Trabajo', 'estado': 'PROGRAMADA'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Faena.objects.filter(descripcion='Evento ajeno').exists())

    def test_formulario_expediente_titulo_sin_historial_html(self):
        self.client.force_login(self.secretaria)
        r = self.client.get(reverse('perfil_ciudadano', args=[self.local.pk]))
        titulo = r.content.decode().split('<title>')[1].split('</title>')[0]
        self.assertNotIn('<section', titulo)
        self.assertNotIn('Bajas y reactivaciones', titulo)

    def test_responsable_inactivo_o_identidad_inactiva_no_cobra(self):
        for atributo, objeto in (('is_active', self.responsable), ('activo', self.responsable.perfil_acceso.ciudadano)):
            setattr(objeto, atributo, False)
            objeto.save()
            with self.assertRaises(ValidationError):
                self.obligaciones[1].acreditar(10, usuario=self.responsable)
            setattr(objeto, atributo, True)
            objeto.save()
