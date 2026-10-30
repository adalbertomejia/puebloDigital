import json
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.core.models import Ciudadano, Manzana
from apps.comites.models import Comite, UsuarioApp, PerfilAcceso
from apps.tesoreria.models import Abono, ObligacionCiudadano
from .models import Solicitud, Seguimiento, TipoSolicitud, Adjunto
from .services import crear, actualizar, token_nuevo, Conflicto
from .autorizacion import visibles
from .archivos import AlmacenPrivado


class SolicitudesTests(TestCase):
    def setUp(self):
        self.comite = Comite.objects.create(nombre='Delegación Dahiedhi')
        self.ajeno = Comite.objects.create(nombre='Comité ajeno', tipo='AGUA')
        self.tipo = TipoSolicitud.objects.create(nombre='Solicitud de prueba')
        self.ciudadano = Ciudadano.objects.create(nombre='Ana', apellido_paterno='Comunitaria')
        self.otro = Ciudadano.objects.create(nombre='Beto', apellido_paterno='Comunitario')
        self.secretaria = self.usuario('secretaria', 'SECRETARIO', self.comite)
        self.presidente = self.usuario('presidente', 'PRESIDENTE', self.comite)
        self.tesorero = self.usuario('tesorero', 'TESORERO', self.comite)
        self.foraneo = self.usuario('ajeno', 'SECRETARIO', self.ajeno)
        self.lector = self.usuario('lector', 'LECTURA', self.comite)
        self.client.force_login(self.secretaria)
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        storage = patch.object(Adjunto._meta.get_field('archivo'), 'storage', AlmacenPrivado(location=self.temporal.name))
        storage.start(); self.addCleanup(storage.stop)

    def usuario(self, nombre, rol, comite):
        user = get_user_model().objects.create_user(username=nombre)
        UsuarioApp.objects.create(user=user, comite=comite, rol=rol)
        user.user_permissions.add(Permission.objects.get(content_type__app_label='core', codename='view_ciudadano'))
        return user

    def datos(self, **kwargs):
        return {'ciudadano': self.ciudadano, 'tipo': self.tipo, 'descripcion': 'Necesita seguimiento comunitario.', 'comite': self.comite, 'responsable': None, 'fecha_compromiso': None, **kwargs}

    def solicitud(self, **kwargs):
        return crear(self.secretaria, self.datos(**kwargs), token_nuevo(self.secretaria))[0]

    def seguimiento(self, **kwargs):
        return {'estado': 'ATENCION', 'fecha_compromiso': None, 'observaciones': 'Revisión inicial', **kwargs}

    def test_cargos_comite_asignacion_y_url_directa(self):
        solicitud = self.solicitud(responsable=self.tesorero)
        url = reverse('secretaria:detalle', args=[solicitud.pk])
        for usuario in (self.secretaria, self.presidente, self.tesorero):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(url).status_code, 200)
        for usuario in (self.foraneo, self.lector):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {'version': 1, 'estado': 'CANCELADA'}).status_code, 404)
            self.assertEqual(self.client.get(reverse('secretaria:constancia', args=[solicitud.pk])).status_code, 404)
        self.client.force_login(self.tesorero)
        self.assertEqual(self.client.get(reverse('secretaria:nueva')).status_code, 404)
        otra = self.solicitud()
        self.assertEqual(self.client.get(reverse('secretaria:detalle', args=[otra.pk])).status_code, 404)

    def test_asignacion_no_concede_acceso_a_otro_comite(self):
        with self.assertRaises(ValidationError):
            self.solicitud(responsable=self.foraneo)
        self.assertFalse(Solicitud.objects.exists())
        solicitud = self.solicitud(responsable=self.tesorero)
        UsuarioApp.objects.filter(user=self.tesorero).update(activo=False)
        self.assertFalse(visibles(self.tesorero).exists())
        with self.assertRaises(ValidationError):
            actualizar(self.secretaria, solicitud.pk, 1, self.seguimiento(responsable=self.foraneo))

    def test_territorio_sigue_el_permiso_actual_del_padron(self):
        norte = Manzana.objects.create(nombre='Norte solicitudes')
        sur = Manzana.objects.create(nombre='Sur solicitudes')
        self.ciudadano.manzana = norte; self.ciudadano.save()
        self.otro.manzana = sur; self.otro.save()
        responsable = self.usuario('responsable-norte', 'SECRETARIO', self.comite)
        responsable.user_permissions.clear()
        PerfilAcceso.objects.create(user=responsable, ciudadano=self.ciudadano)
        norte.responsable = self.ciudadano; norte.save()
        self.solicitud()
        self.solicitud(ciudadano=self.otro)
        self.assertEqual(list(visibles(responsable).values_list('ciudadano_id', flat=True)), [self.ciudadano.pk])
        self.client.force_login(responsable)
        self.assertEqual(self.client.get(reverse('secretaria:nueva'), {'ciudadano': self.otro.pk}).status_code, 404)

    def test_folios_y_reenvio_idempotente_sin_impedir_otra_solicitud(self):
        token = token_nuevo(self.secretaria)
        a, creada = crear(self.secretaria, self.datos(), token)
        b, repetida = crear(self.secretaria, self.datos(), token)
        c = self.solicitud()
        self.assertTrue(creada); self.assertFalse(repetida)
        self.assertEqual(a.pk, b.pk)
        self.assertNotEqual(a.folio, c.folio)
        self.assertEqual(Solicitud.objects.count(), 2)
        self.assertEqual(Seguimiento.objects.count(), 2)
        with self.assertRaises(ValidationError):
            crear(self.presidente, self.datos(), token)
        with self.assertRaises(ValidationError):
            crear(self.secretaria, self.datos(), 'token-falso')

    def test_cierre_exige_motivo_y_confirmacion_y_no_se_reabre(self):
        solicitud = self.solicitud()
        for datos in (self.seguimiento(estado='RESUELTA'), self.seguimiento(estado='CANCELADA', motivo_cierre='Duplicado')):
            with self.assertRaises(ValidationError):
                actualizar(self.secretaria, solicitud.pk, 1, datos)
        final = actualizar(self.secretaria, solicitud.pk, 1, self.seguimiento(estado='RESUELTA', motivo_cierre='Entrega concluida', confirmar_cierre=True))
        self.assertTrue(final.cerrada)
        self.assertIsNotNone(final.fecha_cierre)
        self.assertEqual(final.motivo_cierre, 'Entrega concluida')
        with self.assertRaises(ValidationError):
            actualizar(self.secretaria, solicitud.pk, 2, self.seguimiento())
        self.assertEqual(final.historial.count(), 2)
        self.assertEqual(final.historial.last().autor, self.secretaria)

    def test_cancelacion_conserva_historial(self):
        solicitud = self.solicitud()
        final = actualizar(self.secretaria, solicitud.pk, 1, self.seguimiento(estado='CANCELADA', motivo_cierre='El ciudadano retira la solicitud', confirmar_cierre=True))
        self.assertEqual(final.estado, 'CANCELADA')
        self.assertEqual(final.historial.last().cambios['Motivo de cierre'], final.motivo_cierre)
        self.assertEqual(Solicitud.objects.count(), 1)

    def test_version_desactualizada_no_sobrescribe_y_conserva_captura(self):
        solicitud = self.solicitud()
        actualizar(self.presidente, solicitud.pk, 1, self.seguimiento(observaciones='Primera edición'))
        with self.assertRaises(Conflicto):
            actualizar(self.secretaria, solicitud.pk, 1, self.seguimiento(estado='INFORMACION'))
        response = self.client.post(reverse('secretaria:detalle', args=[solicitud.pk]), {'version': 1, 'estado': 'INFORMACION', 'observaciones': 'Mi captura pendiente'})
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, 'Mi captura pendiente', status_code=409)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, 'ATENCION')
        self.assertEqual(solicitud.historial.count(), 2)

    def test_historial_y_actualizacion_son_atomicos(self):
        solicitud = self.solicitud()
        with patch('apps.secretaria.services.Seguimiento.objects.create', side_effect=RuntimeError('Prueba de fallo')):
            with self.assertRaises(RuntimeError):
                actualizar(self.secretaria, solicitud.pk, 1, self.seguimiento())
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.version, 1)
        self.assertEqual(solicitud.estado, 'RECIBIDA')
        self.assertEqual(solicitud.historial.count(), 1)

    def test_archivos_privados_autorizados_y_sin_huerfanos_en_rollback(self):
        pdf = lambda: SimpleUploadedFile('recepcion.pdf', b'%PDF-1.4\nprueba', content_type='application/pdf')
        solicitud, _ = crear(self.secretaria, self.datos(), token_nuevo(self.secretaria), pdf())
        adjunto = Adjunto.objects.get()
        with self.assertRaises(NotImplementedError):
            _ = adjunto.archivo.url
        url = reverse('secretaria:descargar', args=[solicitud.pk, adjunto.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        response.close()
        self.client.force_login(self.foraneo)
        self.assertEqual(self.client.get(url).status_code, 404)
        cantidad = len([p for p in Path(self.temporal.name).rglob('*') if p.is_file()])
        with patch('apps.secretaria.services.Seguimiento.objects.create', side_effect=RuntimeError('Prueba')):
            with self.assertRaises(RuntimeError):
                crear(self.secretaria, self.datos(), token_nuevo(self.secretaria), pdf())
        self.assertEqual(Solicitud.objects.count(), 1)
        self.assertEqual(Adjunto.objects.count(), 1)
        self.assertEqual(len([p for p in Path(self.temporal.name).rglob('*') if p.is_file()]), cantidad)

    def test_archivos_invalidos_no_guardan_solicitud(self):
        for archivo in (SimpleUploadedFile('peligroso.html', b'<html>'), SimpleUploadedFile('falso.pdf', b'HTML'), SimpleUploadedFile('grande.pdf', b'%PDF-'+b'x'*(5*1024*1024))):
            with self.assertRaises(ValidationError):
                crear(self.secretaria, self.datos(), token_nuevo(self.secretaria), archivo)
        self.assertFalse(Solicitud.objects.exists())
        self.assertFalse(Adjunto.objects.exists())

    def test_filtros_contadores_y_expediente_respetan_alcance(self):
        hoy = timezone.localdate()
        vencida = self.solicitud(fecha_compromiso=hoy-timedelta(days=1), responsable=self.secretaria)
        proxima = self.solicitud(fecha_compromiso=hoy+timedelta(days=2))
        crear(self.foraneo, self.datos(comite=self.ajeno), token_nuevo(self.foraneo))
        response = self.client.get(reverse('secretaria:bandeja'))
        self.assertEqual(response.context['pagina'].paginator.count, 2)
        self.assertEqual(response.context['contadores'], {'mis_pendientes': 1, 'sin_asignar': 1, 'vencidas': 1, 'proximas': 1})
        for params, esperado in (({'q': vencida.folio}, vencida), ({'tarea': 'vencidas'}, vencida), ({'tarea': 'proximas'}, proxima), ({'estado': 'RECIBIDA', 'q': 'Ana'}, None)):
            response = self.client.get(reverse('secretaria:bandeja'), params)
            if esperado: self.assertEqual(list(response.context['pagina']), [esperado])
            else: self.assertEqual(response.context['pagina'].paginator.count, 2)
        perfil = self.client.get(reverse('perfil_ciudadano', args=[self.ciudadano.pk]))
        contenido = perfil.content.decode().split('<main id="contenido-principal"', 1)[1]
        self.assertIn(vencida.folio, contenido)
        self.assertContains(perfil, vencida.folio)
        self.assertContains(perfil, 'Registrar solicitud para este ciudadano')
        self.assertEqual(perfil.context['solicitudes_page'].paginator.count, 2)
        self.assertFalse(vencida.cerrada)
        self.assertTrue(vencida.vencida)

    def test_autocomplete_acotado_para_dos_mil_ciudadanos(self):
        Ciudadano.objects.bulk_create([Ciudadano(nombre=f'Persona{i:04}', apellido_paterno='Sintética') for i in range(2000)])
        response = self.client.get(reverse('secretaria:ciudadanos'), {'q': 'Sintética'})
        self.assertEqual(len(response.json()['results']), 20)
        self.assertTrue(response.json()['pagination']['more'])
        form = self.client.get(reverse('secretaria:nueva'))
        self.assertNotContains(form, 'Persona1999')
        self.assertNotContains(form, 'Persona0000')
        self.client.force_login(self.lector)
        self.assertEqual(self.client.get(reverse('secretaria:ciudadanos'), {'q': 'Persona'}).status_code, 404)

    def test_post_desde_expediente_reenvio_y_retorno(self):
        volver = reverse('perfil_ciudadano', args=[self.ciudadano.pk])+'?return_to=%2Fciudadanos%2F%3Fq%3DAna'
        response = self.client.get(reverse('secretaria:nueva'), {'ciudadano': self.ciudadano.pk, 'return_to': volver})
        self.assertEqual(response.context['form'].initial['ciudadano'], self.ciudadano.pk)
        datos = {'token': response.context['form'].initial['token'], 'ciudadano': self.ciudadano.pk, 'tipo': self.tipo.pk, 'descripcion': 'Texto capturado', 'comite': self.comite.pk, 'responsable': self.tesorero.pk, 'fecha_compromiso': '', 'return_to': volver}
        for _ in range(2):
            response = self.client.post(reverse('secretaria:nueva'), datos)
            self.assertEqual(response.status_code, 302)
        self.assertEqual(Solicitud.objects.count(), 1)
        response = self.client.get(response.url)
        self.assertEqual(response.context['return_to'], volver)
        self.assertContains(response, 'Texto capturado')
        constancia = self.client.get(reverse('secretaria:constancia', args=[Solicitud.objects.get().pk]))
        self.assertContains(constancia, Solicitud.objects.get().folio)
        self.assertContains(constancia, 'no su resolución')
        self.assertEqual(Abono.objects.count(), 0)
        self.assertEqual(ObligacionCiudadano.objects.count(), 0)

    def test_formulario_invalido_conserva_captura_y_rechaza_responsable_ajeno(self):
        response = self.client.post(reverse('secretaria:nueva'), {'token': token_nuevo(self.secretaria), 'ciudadano': self.ciudadano.pk, 'comite': self.comite.pk, 'tipo': self.tipo.pk, 'descripcion': 'Conservar este texto', 'responsable': self.foraneo.pk})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertContains(response, 'Conservar este texto')
        self.assertFalse(Solicitud.objects.exists())
        response = self.client.get(reverse('secretaria:nueva'), {'return_to': 'https://example.com'})
        self.assertEqual(response.context['return_to'], reverse('secretaria:bandeja'))

    def test_csrf_metodos_y_cierre_de_sesion_post(self):
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.secretaria)
        self.assertEqual(protegido.post(reverse('secretaria:nueva'), {}).status_code, 403)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.post(reverse('logout')).status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_responsable_no_reasigna_por_post_manipulado(self):
        solicitud = self.solicitud(responsable=self.tesorero)
        self.client.force_login(self.tesorero)
        response = self.client.post(reverse('secretaria:detalle', args=[solicitud.pk]), {'version': 1, 'estado': 'ATENCION', 'responsable': self.foraneo.pk, 'observaciones': 'Atendiendo'})
        self.assertEqual(response.status_code, 302)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.responsable, self.tesorero)
        self.assertEqual(solicitud.estado, 'ATENCION')

    def test_tipo_inactivo_y_filtros_invalidos(self):
        self.tipo.activo = False; self.tipo.save()
        with self.assertRaises(ValidationError): self.solicitud()
        for parametros in ({'estado': 'INVENTADO'}, {'tipo': '1.5'}, {'comite': '9'*100}, {'tarea': 'inventada'}):
            response = self.client.get(reverse('secretaria:bandeja'), parametros)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['pagina'].paginator.count, 0)
            self.assertTrue(response.context['filtro'].form.errors)

    def test_model_permission_no_sustituye_cargo_y_no_filtra_contadores_ajenos(self):
        self.solicitud(responsable=self.tesorero)
        self.lector.user_permissions.add(Permission.objects.get(content_type__app_label='secretaria', codename='view_solicitud'))
        self.client.force_login(self.lector)
        self.assertEqual(self.client.get(reverse('secretaria:bandeja')).status_code, 404)
        self.client.force_login(self.foraneo)
        response = self.client.get(reverse('secretaria:bandeja'))
        self.assertEqual(response.context['pagina'].paginator.count, 0)
        self.assertTrue(all(v == 0 for v in response.context['contadores'].values()))
        url = reverse('secretaria:responsables')
        self.assertEqual(self.client.get(url, {'forward': json.dumps({'comite': self.comite.pk, 'ciudadano': self.ciudadano.pk})}).status_code, 404)

    def test_archivo_en_seguimiento_se_retira_si_falla_historial(self):
        solicitud = self.solicitud()
        pdf = SimpleUploadedFile('seguimiento.pdf', b'%PDF-1.4\nprueba')
        with patch('apps.secretaria.services.Seguimiento.objects.create', side_effect=RuntimeError('Prueba')):
            with self.assertRaises(RuntimeError):
                actualizar(self.secretaria, solicitud.pk, 1, self.seguimiento(), pdf)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.version, 1)
        self.assertFalse(Adjunto.objects.exists())
        self.assertFalse(any(p.is_file() for p in Path(self.temporal.name).rglob('*')))

    def test_constancia_y_documentos_no_permiten_post(self):
        solicitud = self.solicitud()
        self.assertEqual(self.client.post(reverse('secretaria:constancia', args=[solicitud.pk])).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('secretaria:bandeja')).status_code, 302)


from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracionSecretariaTests(TransactionTestCase):
    def test_actualizacion_conserva_ciudadanos_y_finanzas_sin_crear_solicitudes(self):
        from apps.tesoreria.models import ConceptoTesoreria
        executor = MigrationExecutor(connection)
        destinos = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([('secretaria', None)])
            ciudadano = Ciudadano.objects.create(nombre='Ciudadano previo', apellido_paterno='Migración', numero_contrato='PREVIO-123')
            comite = Comite.objects.create(nombre='Comité previo')
            concepto = ConceptoTesoreria.objects.create(comite=comite, concepto='Cuota previa', naturaleza='PAGO', monto_individual=100)
            obligacion = ObligacionCiudadano.objects.create(ciudadano=ciudadano, concepto=concepto, monto_asignado=100)
            abono = obligacion.acreditar(15)
        finally:
            MigrationExecutor(connection).migrate(destinos)
        self.assertEqual(Ciudadano.objects.get(pk=ciudadano.pk).numero_contrato, 'PREVIO-123')
        self.assertEqual(Abono.objects.get(pk=abono.pk).monto, 15)
        self.assertEqual(ObligacionCiudadano.objects.get(pk=obligacion.pk).saldo_pendiente, 85)
        self.assertFalse(Solicitud.objects.exists())
        self.assertFalse(TipoSolicitud.objects.exists())


class ConcurrenciaSolicitudTests(TransactionTestCase):
    def test_dos_envios_simultaneos_no_duplican_y_permiten_reintento(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections
        usuario = get_user_model().objects.create_superuser(username='qa-concurrencia', password='temporal')
        comite = Comite.objects.create(nombre='Comité concurrencia')
        ciudadano = Ciudadano.objects.create(nombre='Persona', apellido_paterno='Concurrencia')
        tipo = TipoSolicitud.objects.create(nombre='Prueba simultánea')
        token = token_nuevo(usuario)
        datos = {'ciudadano': ciudadano, 'comite': comite, 'tipo': tipo, 'descripcion': 'Una sola solicitud', 'responsable': None, 'fecha_compromiso': None}
        barrera = Barrier(2)

        def enviar():
            try:
                actor = get_user_model().objects.get(pk=usuario.pk)
                barrera.wait(timeout=10)
                try:
                    solicitud, _ = crear(actor, datos, token)
                    return solicitud.pk
                except Conflicto:
                    return None
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as grupo:
            resultados = list(grupo.map(lambda _: enviar(), range(2)))
        # SQLite can reject both lock upgrades. Reusing the same submission key
        # retries safely, whether neither or one request committed first.
        solicitud, _ = crear(usuario, datos, token)
        self.assertEqual(Solicitud.objects.count(), 1)
        self.assertEqual(Seguimiento.objects.count(), 1)
        self.assertTrue(all(pk is None or pk == solicitud.pk for pk in resultados))
