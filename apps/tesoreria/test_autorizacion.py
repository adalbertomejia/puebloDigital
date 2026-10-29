from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import Comite, UsuarioApp
from apps.core.models import Ciudadano
from apps.operacion.models import Faena
from apps.tesoreria.autorizacion import limitar_finanzas
from apps.tesoreria.models import Abono, ConceptoTesoreria, Cooperacion, ObligacionCiudadano, Pago
from apps.tesoreria.queries import anotar_conceptos


class AislamientoFinancieroTests(TestCase):
    def setUp(self):
        self.agua = Comite.objects.create(nombre="Comité Agua autorizado", tipo="AGUA")
        self.feria = Comite.objects.create(nombre="Comité Feria ajeno", tipo="FERIA")
        self.presidente = get_user_model().objects.create_user(username="presidente-agua")
        self.tesorero = get_user_model().objects.create_user(username="tesorero-agua")
        self.cargos = []
        for usuario, rol in ((self.presidente, "PRESIDENTE"), (self.tesorero, "TESORERO")):
            self.cargos.append(UsuarioApp.objects.create(user=usuario, comite=self.agua, rol=rol))
        self.ciudadano = Ciudadano.objects.create(nombre="Ana", apellido_paterno="Comunitaria")
        self.otro = Ciudadano.objects.create(nombre="Beto", apellido_paterno="Comunitario")
        self.concepto = self.crear_concepto(self.agua, "Cuota propia")
        self.ajeno = self.crear_concepto(self.feria, "Concepto financiero reservado")
        self.obligacion = ObligacionCiudadano.objects.create(concepto=self.concepto, ciudadano=self.ciudadano, monto_asignado=100)
        self.obligacion_ajena = ObligacionCiudadano.objects.create(concepto=self.ajeno, ciudadano=self.ciudadano, monto_asignado=100)
        self.abono = Abono.objects.create(obligacion=self.obligacion, monto=11, fecha=date(2026, 10, 1))
        self.abono_ajeno = Abono.objects.create(obligacion=self.obligacion_ajena, monto=29, fecha=date(2025, 1, 1))

    def crear_concepto(self, comite, nombre):
        return ConceptoTesoreria.objects.create(comite=comite, concepto=nombre, naturaleza="PAGO", monto_individual=100, fecha=date(2026, 10, 1))

    def datos_concepto(self, comite):
        return {"comite": comite.pk, "concepto": "Concepto desde formulario", "naturaleza": "PAGO",
                "monto_individual": "100", "fecha": "2026-10-29", "alcance": "GENERAL", "manzana": ""}

    def urls_lectura(self):
        return [reverse(nombre) for nombre in ("tesoreria_operativa", "exportar_tesoreria_csv",
                "resumen_aportaciones", "buscar_aportaciones", "exportar_aportaciones_csv")]

    def test_presidente_y_tesorero_consultan_solo_su_comite_en_vistas_y_csv(self):
        for usuario in (self.presidente, self.tesorero):
            self.client.force_login(usuario)
            for url in self.urls_lectura():
                with self.subTest(usuario=usuario.username, url=url):
                    respuesta = self.client.get(url)
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertContains(respuesta, "Cuota propia")
                    self.assertNotContains(respuesta, "Concepto financiero reservado")
                    self.assertNotContains(respuesta, "Comité Feria ajeno")
            for ruta in ("tesoreria_concepto_detalle", "exportar_obligaciones_tesoreria_csv"):
                self.assertEqual(self.client.get(reverse(ruta, args=[self.concepto.pk])).status_code, 200)
                self.assertEqual(self.client.get(reverse(ruta, args=[self.ajeno.pk])).status_code, 404)

    def test_filtros_y_respuestas_parciales_no_amplian_el_ambito(self):
        self.client.force_login(self.presidente)
        for url in self.urls_lectura():
            for parametros in ({"comite": self.feria.pk}, {"comite": "todos", "q": "reservado"}):
                with self.subTest(url=url, parametros=parametros):
                    respuesta = self.client.get(url, parametros)
                    self.assertEqual(respuesta.status_code, 200)
                    self.assertNotContains(respuesta, "Concepto financiero reservado")
                    self.assertNotContains(respuesta, "Comité Feria ajeno")
        respuesta = self.client.get(reverse("tesoreria_operativa"), {"comite": self.feria.pk}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, "Concepto financiero reservado")
        respuesta = self.client.get(reverse("buscar_aportaciones"), {"q": "reservado"}, HTTP_HX_REQUEST="true")
        self.assertEqual(respuesta.context["cantidad_resultados"], 0)

    def test_metricas_fechas_y_graficas_excluyen_importes_ajenos(self):
        self.client.force_login(self.tesorero)
        lista = self.client.get(reverse("tesoreria_operativa"))
        resumen = self.client.get(reverse("resumen_aportaciones"))
        self.assertEqual(lista.context["metricas"]["total_asignado"], Decimal("100"))
        self.assertEqual(lista.context["metricas"]["total_abonado"], Decimal("11"))
        self.assertEqual(resumen.context["metricas"]["total_recibido"], Decimal("11"))
        self.assertEqual([d.year for d in resumen.context["anios"]], [2026])
        self.assertEqual([c["nombre"] for c in resumen.context["datos_grafica"]["conceptos"]], ["Cuota propia"])

    def test_comite_sin_datos_no_recae_en_consulta_global(self):
        self.concepto.delete()
        self.assertFalse(anotar_conceptos(ConceptoTesoreria.objects.none()).exists())
        self.client.force_login(self.presidente)
        respuesta = self.client.get(reverse("tesoreria_operativa"))
        self.assertFalse(respuesta.context["hay_conceptos"])
        self.assertEqual(respuesta.context["metricas"]["total_asignado"], 0)
        respuesta = self.client.get(reverse("resumen_aportaciones"))
        self.assertFalse(respuesta.context["hay_abonos"])
        self.assertEqual(respuesta.context["metricas"]["total_recibido"], 0)

    def test_ambos_roles_crean_generan_idempotentemente_y_abonan_sin_permisos_globales(self):
        for usuario in (self.presidente, self.tesorero):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                datos = self.datos_concepto(self.agua)
                datos["concepto"] = usuario.username
                respuesta = self.client.post(reverse("crear_concepto_tesoreria"), datos)
                self.assertEqual(respuesta.status_code, 302)
                concepto = ConceptoTesoreria.objects.get(concepto=usuario.username)
                url = reverse("generar_obligaciones_tesoreria", args=[concepto.pk])
                self.assertEqual(self.client.post(url).status_code, 302)
                self.assertEqual(self.client.post(url).status_code, 302)
                self.assertEqual(concepto.obligaciones.count(), 2)
                obligacion = concepto.obligaciones.get(ciudadano=self.ciudadano)
                self.assertEqual(self.client.post(reverse("acreditar_obligacion", args=[obligacion.pk]), {
                    "monto": "25", "fecha": "2026-10-29", "notas": "Recibo comunitario",
                }).status_code, 302)
                self.assertEqual(obligacion.total_abonado, Decimal("25"))
                self.assertEqual(obligacion.saldo_pendiente, Decimal("75"))

    def test_post_ajeno_no_edita_genera_abona_ni_elimina(self):
        for usuario in (self.presidente, self.tesorero):
            self.client.force_login(usuario)
            for ruta in ("editar_concepto_tesoreria", "generar_obligaciones_tesoreria", "eliminar_concepto_tesoreria"):
                with self.subTest(usuario=usuario.username, ruta=ruta):
                    self.assertEqual(self.client.post(reverse(ruta, args=[self.ajeno.pk]), self.datos_concepto(self.agua)).status_code, 404)
            self.assertEqual(self.client.post(reverse("acreditar_obligacion", args=[self.obligacion_ajena.pk]), {"monto": "1", "fecha": "2026-10-29"}).status_code, 404)
        self.ajeno.refresh_from_db()
        self.assertEqual(self.ajeno.concepto, "Concepto financiero reservado")
        self.assertEqual(self.ajeno.obligaciones.count(), 1)
        self.assertEqual(self.obligacion_ajena.total_abonado, Decimal("29"))

    def test_formulario_no_admite_comite_ajeno_y_no_transfiere_concepto_con_obligaciones(self):
        self.client.force_login(self.presidente)
        respuesta = self.client.get(reverse("crear_concepto_tesoreria"))
        self.assertEqual(list(respuesta.context["form"].fields["comite"].queryset), [self.agua])
        self.assertEqual(self.client.post(reverse("crear_concepto_tesoreria"), self.datos_concepto(self.feria)).status_code, 200)
        self.assertFalse(ConceptoTesoreria.objects.filter(concepto="Concepto desde formulario").exists())
        UsuarioApp.objects.create(user=self.presidente, comite=self.feria, rol="TESORERO")
        respuesta = self.client.post(reverse("editar_concepto_tesoreria", args=[self.concepto.pk]), self.datos_concepto(self.feria))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("comite", respuesta.context["form"].errors)
        self.concepto.refresh_from_db()
        self.assertEqual(self.concepto.comite_id, self.agua.pk)

    def test_cargos_no_financieros_y_permisos_django_sin_cargo_no_conceden_acceso(self):
        for rol in (None, "LECTURA", "SECRETARIO", "CAPTURISTA", "DELEGADO"):
            usuario = get_user_model().objects.create_user(username=f"sin-finanzas-{rol}")
            usuario.user_permissions.set(Permission.objects.all())
            if rol:
                UsuarioApp.objects.create(user=usuario, comite=self.agua, rol=rol)
            self.client.force_login(usuario)
            for url in self.urls_lectura() + [reverse("crear_concepto_tesoreria"), reverse("tesoreria_concepto_detalle", args=[self.concepto.pk])]:
                with self.subTest(rol=rol, url=url):
                    self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(reverse("generar_obligaciones_tesoreria", args=[self.concepto.pk])).status_code, 404)

    def test_cargo_comite_y_cuenta_inactivos_revocan_acceso(self):
        self.client.force_login(self.presidente)
        for objeto, campo in ((self.cargos[0], "activo"), (self.agua, "activo")):
            setattr(objeto, campo, False)
            objeto.save(update_fields=[campo])
            self.assertEqual(self.client.get(reverse("tesoreria_operativa")).status_code, 404)
            self.assertEqual(self.client.post(reverse("acreditar_obligacion", args=[self.obligacion.pk]), {"monto": "1"}).status_code, 404)
            setattr(objeto, campo, True)
            objeto.save(update_fields=[campo])
        self.presidente.is_active = False
        self.assertFalse(limitar_finanzas(ConceptoTesoreria.objects.all(), self.presidente).exists())

    def test_presidente_agua_tesorero_feria_no_se_convierte_en_presidente_feria(self):
        UsuarioApp.objects.create(user=self.presidente, comite=self.feria, rol="TESORERO")
        evento = Faena.objects.create(comite=self.feria, descripcion="Evento ajeno al cargo presidencial", fecha=date(2026, 10, 29))
        self.client.force_login(self.presidente)
        self.assertEqual(self.client.get(reverse("tesoreria_concepto_detalle", args=[self.ajeno.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("generar_registros_faena", args=[evento.pk])).status_code, 404)

    def test_borrado_propio_requiere_post_y_elimina_la_cascada(self):
        for usuario in (self.presidente, self.tesorero):
            with self.subTest(usuario=usuario.username):
                concepto = self.crear_concepto(self.agua, f"Eliminar {usuario.username}")
                obligacion = ObligacionCiudadano.objects.create(concepto=concepto, ciudadano=self.ciudadano, monto_asignado=100)
                abono = Abono.objects.create(obligacion=obligacion, monto=5)
                self.client.force_login(usuario)
                url = reverse("eliminar_concepto_tesoreria", args=[concepto.pk])
                self.assertContains(self.client.get(url), "todos los abonos")
                self.assertTrue(ConceptoTesoreria.objects.filter(pk=concepto.pk).exists())
                self.assertEqual(self.client.post(url).status_code, 302)
                self.assertFalse(ConceptoTesoreria.objects.filter(pk=concepto.pk).exists())
                self.assertFalse(ObligacionCiudadano.objects.filter(pk=obligacion.pk).exists())
                self.assertFalse(Abono.objects.filter(pk=abono.pk).exists())

    def test_expediente_filtra_historial_y_totales_aunque_tenga_permiso_de_padron(self):
        self.presidente.user_permissions.add(Permission.objects.get(content_type__app_label="core", codename="view_ciudadano"))
        self.client.force_login(self.presidente)
        respuesta = self.client.get(reverse("perfil_ciudadano", args=[self.ciudadano.pk]))
        self.assertContains(respuesta, "Cuota propia")
        self.assertNotContains(respuesta, "Concepto financiero reservado")
        self.assertEqual(respuesta.context["resumen"]["total_abonado"], Decimal("11"))
        self.assertEqual(respuesta.context["resumen"]["conceptos"], 1)

    def test_inicio_filtra_movimientos_heredados(self):
        for comite, texto in ((self.agua, "Movimiento propio"), (self.feria, "Movimiento reservado")):
            Pago.objects.create(comite=comite, ciudadano=self.ciudadano, concepto=texto, monto=17, fecha=date(2026, 10, 29))
            Cooperacion.objects.create(comite=comite, ciudadano=self.ciudadano, concepto=texto, monto=19, fecha=date(2026, 10, 29))
        self.client.force_login(self.tesorero)
        respuesta = self.client.get(reverse("dashboard_operativo"))
        financieros = [fila for fila in respuesta.context["actividad_reciente"] if fila["tipo"] in ("Pago", "Cooperación")]
        self.assertEqual(len(financieros), 2)
        self.assertEqual(respuesta.context["metricas"]["pagos_mes"], 1)
        self.assertEqual(list(respuesta.context["ciudadanos"])[0].total_pagos, 1)

    def test_admin_financiero_y_asignaciones_reservados_al_superusuario(self):
        self.presidente.is_staff = True
        self.presidente.save(update_fields=["is_staff"])
        self.presidente.user_permissions.set(Permission.objects.all())
        self.client.force_login(self.presidente)
        for modelo in ("conceptotesoreria", "obligacionciudadano", "abono", "pago", "cooperacion"):
            with self.subTest(modelo=modelo):
                self.assertEqual(self.client.get(reverse(f"admin:tesoreria_{modelo}_changelist")).status_code, 403)
                self.assertEqual(self.client.get(reverse(f"admin:tesoreria_{modelo}_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:tesoreria_conceptotesoreria_change", args=[self.ajeno.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:comites_usuarioapp_changelist")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:auth_user_change", args=[self.presidente.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:auth_group_changelist")).status_code, 403)
        respuesta = self.client.get(reverse("admin:core_ciudadano_change", args=[self.ciudadano.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'id="pagos-group"')
        self.assertNotContains(respuesta, 'id="cooperaciones-group"')
        self.assertEqual(self.client.get(reverse("admin:autocomplete"), {"app_label": "tesoreria", "model_name": "obligacionciudadano", "field_name": "concepto", "term": "reservado"}).status_code, 403)

    def test_superusuario_conserva_acceso_global_y_comites_inactivos(self):
        administrador = get_user_model().objects.create_superuser(username="administrador-financiero", email="admin@example.com", password="unused")
        self.feria.activo = False
        self.feria.save(update_fields=["activo"])
        self.client.force_login(administrador)
        self.assertContains(self.client.get(reverse("tesoreria_operativa")), "Concepto financiero reservado")
        self.assertEqual(self.client.get(reverse("admin:tesoreria_conceptotesoreria_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("tesoreria_concepto_detalle", args=[self.ajeno.pk])).status_code, 200)

    def test_generacion_para_dos_mil_ciudadanos_sigue_aislada_e_idempotente(self):
        Ciudadano.objects.bulk_create([
            Ciudadano(nombre=f"Ciudadano {numero}", apellido_paterno="Padrón")
            for numero in range(1998)
        ], batch_size=500)
        Ciudadano.objects.create(nombre="Inactivo", apellido_paterno="Excluido", activo=False)
        concepto = self.crear_concepto(self.agua, "Obligaciones de dos mil ciudadanos")
        self.client.force_login(self.tesorero)
        url = reverse("generar_obligaciones_tesoreria", args=[concepto.pk])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(concepto.obligaciones.count(), 2000)
        self.assertFalse(concepto.obligaciones.filter(ciudadano__activo=False).exists())
        self.assertEqual(self.ajeno.obligaciones.count(), 1)
        respuesta = self.client.get(reverse("tesoreria_concepto_detalle", args=[concepto.pk]))
        self.assertEqual(respuesta.context["page_obj"].paginator.count, 2000)
        self.assertEqual(len(respuesta.context["page_obj"].object_list), 25)

    def test_padron_no_expone_fecha_de_pago_de_otro_comite(self):
        self.presidente.user_permissions.add(Permission.objects.get(content_type__app_label="core", codename="view_ciudadano"))
        Pago.objects.create(comite=self.feria, ciudadano=self.ciudadano, concepto="Pago ajeno", monto=7, fecha=date(2025, 3, 5))
        self.client.force_login(self.presidente)
        respuesta = self.client.get(reverse("padron_ciudadanos"))
        ciudadano = next(c for c in respuesta.context["ciudadanos"] if c.pk == self.ciudadano.pk)
        self.assertIsNone(ciudadano.ultimo_pago_fecha)

    def test_permisos_globales_no_amplian_el_comite_de_un_cargo_financiero(self):
        self.presidente.user_permissions.set(Permission.objects.filter(content_type__app_label="tesoreria"))
        self.client.force_login(self.presidente)
        self.assertEqual(self.client.get(reverse("tesoreria_concepto_detalle", args=[self.ajeno.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("acreditar_obligacion", args=[self.obligacion_ajena.pk]), {"monto": "1", "fecha": "2026-10-29"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("eliminar_concepto_tesoreria", args=[self.ajeno.pk])).status_code, 404)
        self.assertTrue(ConceptoTesoreria.objects.filter(pk=self.ajeno.pk).exists())
        self.assertEqual(self.obligacion_ajena.total_abonado, Decimal("29"))

    def test_tesorero_inicia_sesion_en_el_panel_sin_necesitar_staff(self):
        self.tesorero.set_password("prueba-solo-local")
        self.tesorero.save(update_fields=["password"])
        respuesta = self.client.post(reverse("login"), {"username": self.tesorero.username, "password": "prueba-solo-local"})
        self.assertRedirects(respuesta, reverse("dashboard_operativo"))
        self.assertFalse(self.tesorero.is_staff)
        respuesta = self.client.get(reverse("tesoreria_operativa"))
        self.assertContains(respuesta, "Cuota propia")
        self.assertNotContains(respuesta, "Concepto financiero reservado")
