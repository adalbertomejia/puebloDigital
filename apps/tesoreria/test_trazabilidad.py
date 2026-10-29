from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import Comite, UsuarioApp
from apps.core.models import Ciudadano
from apps.tesoreria.models import Abono, ConceptoTesoreria, ObligacionCiudadano, RegistroFinanciero


class TrazabilidadFinancieraTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="tesorera-registro")
        self.presidente = get_user_model().objects.create_user(username="presidente-registro")
        self.comite = Comite.objects.create(nombre="Agua con seguimiento")
        self.ajeno = Comite.objects.create(nombre="Feria ajena")
        for usuario, rol in ((self.usuario, "TESORERO"), (self.presidente, "PRESIDENTE")):
            UsuarioApp.objects.create(user=usuario, comite=self.comite, rol=rol)
        self.ciudadano = Ciudadano.objects.create(nombre="Ana", apellido_paterno="Comunidad")
        self.concepto = ConceptoTesoreria.objects.create(comite=self.comite, concepto="Concepto anterior", naturaleza="PAGO", monto_individual=100, fecha=date(2026, 10, 1))
        self.obligacion = ObligacionCiudadano.objects.create(concepto=self.concepto, ciudadano=self.ciudadano, monto_asignado=100)
        self.client.force_login(self.usuario)

    def datos_concepto(self):
        return {"comite": self.comite.pk, "concepto": "Nuevo concepto", "naturaleza": "PAGO", "alcance": "GENERAL", "monto_individual": "100", "fecha": "2026-10-29"}

    def test_creacion_y_edicion_registran_actor_sin_suplantar_al_autor_original(self):
        datos = {**self.datos_concepto(), "creado_por": self.presidente.pk, "usuario": self.presidente.pk}
        self.assertEqual(self.client.post(reverse("crear_concepto_tesoreria"), datos).status_code, 302)
        concepto = ConceptoTesoreria.objects.get(concepto="Nuevo concepto")
        self.assertEqual(concepto.creado_por, self.usuario)
        registro = RegistroFinanciero.objects.get(accion="CREAR")
        self.assertEqual(registro.usuario, self.usuario)
        self.assertEqual(registro.concepto_id_registrado, concepto.pk)
        self.client.force_login(self.presidente)
        datos["concepto"] = "Concepto editado"
        self.assertEqual(self.client.post(reverse("editar_concepto_tesoreria", args=[concepto.pk]), datos).status_code, 302)
        concepto.refresh_from_db()
        self.assertEqual(concepto.creado_por, self.usuario)
        registro = RegistroFinanciero.objects.get(accion="EDITAR")
        self.assertEqual(registro.usuario, self.presidente)
        self.assertIn("concepto", registro.detalle["campos"])

    def test_generacion_conserva_autor_y_no_duplica_eventos_sin_cambios(self):
        concepto = ConceptoTesoreria.objects.create(comite=self.comite, concepto="Por generar", naturaleza="PAGO", monto_individual=100)
        url = reverse("generar_obligaciones_tesoreria", args=[concepto.pk])
        self.assertEqual(self.client.post(url).status_code, 302)
        obligacion = concepto.obligaciones.get()
        self.assertEqual(obligacion.creado_por, self.usuario)
        self.client.force_login(self.presidente)
        self.assertEqual(self.client.post(url).status_code, 302)
        obligacion.refresh_from_db()
        self.assertEqual(obligacion.creado_por, self.usuario)
        registro = RegistroFinanciero.objects.get(accion="GENERAR")
        self.assertEqual(registro.usuario, self.usuario)
        self.assertEqual(registro.detalle["creados"], 1)

    def test_abono_registra_usuario_real_referencia_importe_y_fecha(self):
        url = reverse("acreditar_obligacion", args=[self.obligacion.pk])
        self.assertEqual(self.client.post(url, {"monto": "25", "fecha": "2026-10-29", "referencia": "REC-001", "notas": "Efectivo", "creado_por": self.presidente.pk}).status_code, 302)
        abono = self.obligacion.abonos.get()
        self.assertEqual(abono.creado_por, self.usuario)
        self.assertEqual(abono.referencia, "REC-001")
        self.assertEqual(abono.monto, Decimal("25"))
        registro = RegistroFinanciero.objects.get(accion="ABONAR")
        self.assertEqual(registro.objeto_id, abono.pk)
        self.assertEqual(registro.usuario_nombre, "tesorera-registro")
        self.assertEqual(registro.referencia, "REC-001")
        self.assertEqual(registro.monto, Decimal("25"))
        self.assertIsNotNone(registro.fecha_registro)
        for ruta, args in (("acreditar_obligacion", [self.obligacion.pk]), ("tesoreria_concepto_detalle", [self.concepto.pk]), ("actividad_financiera", []), ("exportar_aportaciones_csv", [])):
            with self.subTest(ruta=ruta):
                response = self.client.get(reverse(ruta, args=args))
                self.assertContains(response, "REC-001")
                self.assertContains(response, "tesorera-registro")

    def test_importe_o_referencia_invalidos_no_crean_movimiento(self):
        for monto, referencia in (("101", "R-1"), ("-1", "R-2"), ("1", "X" * 101)):
            with self.subTest(monto=monto, referencia=referencia):
                response = self.client.post(reverse("acreditar_obligacion", args=[self.obligacion.pk]), {"monto": monto, "referencia": referencia, "fecha": "2026-10-29"})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(self.obligacion.abonos.exists())
                self.assertFalse(RegistroFinanciero.objects.exists())

    def test_fallo_de_bitacora_revierte_abono_y_estado(self):
        with patch("apps.tesoreria.auditoria.registrar_movimiento", side_effect=RuntimeError("No se pudo registrar")):
            response = self.client.post(reverse("acreditar_obligacion", args=[self.obligacion.pk]), {"monto": "100", "fecha": "2026-10-29"})
        self.assertEqual(response.status_code, 200)
        self.obligacion.refresh_from_db()
        self.assertEqual(self.obligacion.estado, "PENDIENTE")
        self.assertFalse(self.obligacion.abonos.exists())

    def test_fallo_de_bitacora_revierte_concepto_y_generacion(self):
        with patch("apps.core.views.registrar_movimiento", side_effect=RuntimeError("No se pudo registrar")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("crear_concepto_tesoreria"), self.datos_concepto())
        self.assertFalse(ConceptoTesoreria.objects.filter(concepto="Nuevo concepto").exists())
        nuevo = ConceptoTesoreria.objects.create(comite=self.comite, concepto="Sin participantes", naturaleza="PAGO", monto_individual=100)
        with patch("apps.tesoreria.services.registrar_movimiento", side_effect=RuntimeError("No se pudo registrar")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("generar_obligaciones_tesoreria", args=[nuevo.pk]))
        self.assertFalse(nuevo.obligaciones.exists())
        nuevo.refresh_from_db()
        self.assertFalse(nuevo.registros_generados)

    def test_eliminacion_conserva_evidencia_y_protege_la_cuenta_del_actor(self):
        self.obligacion.acreditar(10, usuario=self.usuario, referencia="ANTES-DE-BORRAR")
        pk = self.concepto.pk
        self.assertEqual(self.client.post(reverse("eliminar_concepto_tesoreria", args=[pk])).status_code, 302)
        self.assertFalse(ConceptoTesoreria.objects.filter(pk=pk).exists())
        self.assertFalse(Abono.objects.exists())
        registros = RegistroFinanciero.objects.filter(concepto_id_registrado=pk)
        self.assertEqual(registros.count(), 2)
        self.assertEqual(registros.get(accion="ELIMINAR").detalle["total_abonado"], "10")
        response = self.client.get(reverse("actividad_financiera"))
        self.assertContains(response, "Concepto anterior")
        self.assertContains(response, "ANTES-DE-BORRAR")
        with self.assertRaises(ProtectedError):
            self.usuario.delete()

    def test_bitacora_se_aisla_por_comite_y_no_inventa_autoria_historica(self):
        from apps.tesoreria.auditoria import registrar_movimiento
        concepto_ajeno = ConceptoTesoreria.objects.create(comite=self.ajeno, concepto="Registro reservado", naturaleza="PAGO", monto_individual=100)
        registrar_movimiento(self.presidente, concepto_ajeno, "CREAR")
        self.assertIsNone(self.concepto.creado_por)
        self.assertIsNone(self.obligacion.creado_por)
        self.assertContains(self.client.get(reverse("tesoreria_concepto_detalle", args=[self.concepto.pk])), "Autor no registrado")
        for params in ({}, {"comite": self.ajeno.pk}, {"concepto": concepto_ajeno.pk}):
            response = self.client.get(reverse("actividad_financiera"), params)
            self.assertNotContains(response, "Registro reservado")
            self.assertEqual(response.context["pagina"].paginator.count, 0)
        self.client.force_login(get_user_model().objects.create_user(username="sin-cargo-bitacora"))
        self.assertEqual(self.client.get(reverse("actividad_financiera")).status_code, 404)

    def test_admin_estampa_autor_y_bitacora_es_de_solo_lectura(self):
        from django.contrib import admin
        from django.test import RequestFactory
        from apps.tesoreria.forms import ConceptoTesoreriaForm
        usuario = get_user_model().objects.create_superuser(username="admin-traza", email="admin@example.com", password="unused")
        request = RequestFactory().post("/admin/")
        request.user = usuario
        form = ConceptoTesoreriaForm(self.datos_concepto(), usuario=usuario)
        self.assertTrue(form.is_valid(), form.errors)
        obj = form.save(commit=False)
        admin.site._registry[ConceptoTesoreria].save_model(request, obj, form, change=False)
        self.assertEqual(obj.creado_por, usuario)
        registro = RegistroFinanciero.objects.get()
        self.assertEqual(registro.origen, "ADMIN")
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse("admin:tesoreria_registrofinanciero_change", args=[registro.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("admin:tesoreria_registrofinanciero_change", args=[registro.pk]), {"usuario_nombre": "falso"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:tesoreria_registrofinanciero_delete", args=[registro.pk]), {"post": "yes"}).status_code, 403)
        registro.refresh_from_db()
        self.assertEqual(registro.usuario_nombre, "admin-traza")

    def test_csv_y_busqueda_incluyen_autor_y_referencia_sin_romper_columnas(self):
        import csv
        import io
        self.client.post(reverse("crear_concepto_tesoreria"), self.datos_concepto())
        concepto = ConceptoTesoreria.objects.get(concepto="Nuevo concepto")
        self.client.post(reverse("generar_obligaciones_tesoreria", args=[concepto.pk]))
        obligacion = concepto.obligaciones.get()
        obligacion.acreditar(15, usuario=self.usuario, referencia="REC-UNICO-2026")
        for ruta, args in (("exportar_tesoreria_csv", []), ("exportar_obligaciones_tesoreria_csv", [concepto.pk]), ("exportar_aportaciones_csv", [])):
            with self.subTest(ruta=ruta):
                response = self.client.get(reverse(ruta, args=args))
                filas = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
                self.assertIn("Registrado por", filas[0])
                self.assertIn("Fecha de registro", filas[0])
                self.assertTrue(any("tesorera-registro" in fila for fila in filas[1:]))
                self.assertTrue(all(len(fila) == len(filas[0]) for fila in filas[1:]))
        response = self.client.get(reverse("buscar_aportaciones"), {"q": "REC-UNICO-2026"})
        self.assertEqual(response.context["cantidad_resultados"], 1)
        self.assertContains(response, "REC-UNICO-2026")
        self.assertContains(response, "tesorera-registro")

    def test_admin_inline_atribuye_abono_al_administrador_real(self):
        administrador = get_user_model().objects.create_superuser(username="admin-inline", email="admin@example.com", password="unused")
        self.client.force_login(administrador)
        response = self.client.post(reverse("admin:tesoreria_obligacionciudadano_change", args=[self.obligacion.pk]), {
            "concepto": self.concepto.pk, "ciudadano": self.ciudadano.pk, "monto_asignado": "100", "estado": "PENDIENTE", "notas": "",
            "abonos-TOTAL_FORMS": "1", "abonos-INITIAL_FORMS": "0", "abonos-MIN_NUM_FORMS": "0", "abonos-MAX_NUM_FORMS": "1000",
            "abonos-0-obligacion": self.obligacion.pk, "abonos-0-monto": "20", "abonos-0-fecha": "2026-10-29",
            "abonos-0-referencia": "REC-ADMIN", "abonos-0-notas": "Captura administrativa", "abonos-0-creado_por": self.usuario.pk,
        })
        self.assertEqual(response.status_code, 302)
        abono = self.obligacion.abonos.get()
        self.assertEqual(abono.creado_por, administrador)
        self.assertEqual(abono.referencia, "REC-ADMIN")
        registro = RegistroFinanciero.objects.get(tipo_objeto="abono")
        self.assertEqual(registro.usuario, administrador)
        self.assertEqual(registro.origen, "ADMIN")
