import json
from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from apps.agua.models import Toma
from apps.comites.models import Comite, UsuarioApp, PerfilAcceso
from apps.core.models import Ciudadano, Manzana
from apps.tesoreria.models import ConceptoTesoreria, ObligacionCiudadano, Abono


class InterfazOperativaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="cajera-ui")
        self.comite = Comite.objects.create(nombre="Comité propio", tipo="AGUA")
        self.ajeno = Comite.objects.create(nombre="Comité ajeno", tipo="FERIA")
        UsuarioApp.objects.create(user=self.usuario, comite=self.comite, rol="TESORERO")
        self.admin = get_user_model().objects.create_superuser(username="admin-ui", email="admin@example.com", password="unused")
        self.ciudadano = Ciudadano.objects.create(nombre="Ana", apellido_paterno="Propia", numero_contrato="C-UI-001", edad=30)
        self.otro = Ciudadano.objects.create(nombre="Persona", apellido_paterno="Reservada", numero_contrato="C-OCULTO")
        Toma.objects.create(ciudadano=self.ciudadano, numero_toma="T-UI-099")
        c = ConceptoTesoreria.objects.create(comite=self.comite, concepto="Cuota propia", naturaleza="PAGO", monto_individual=100)
        otro = ConceptoTesoreria.objects.create(comite=self.ajeno, concepto="Cuota reservada", naturaleza="PAGO", monto_individual=100)
        self.obligacion = ObligacionCiudadano.objects.create(concepto=c, ciudadano=self.ciudadano, monto_asignado=100)
        self.obligacion_ajena = ObligacionCiudadano.objects.create(concepto=otro, ciudadano=self.otro, monto_asignado=100)
        self.client.force_login(self.usuario)

    def test_selector_busca_por_toma_y_no_filtra_datos_ajenos(self):
        url=reverse("ciudadano_financiero_autocomplete")
        datos=self.client.get(url,{"q":"T-UI-099"}).json()
        self.assertEqual([r["id"] for r in datos["results"]],[str(self.ciudadano.pk)])
        self.assertIn("C-UI-001",datos["results"][0]["text"])
        self.assertEqual(self.client.get(url,{"q":"Reservada"}).json()["results"],[])
        self.assertEqual(self.client.get(url,{"q":""}).json()["results"],[])

    def test_obligaciones_dependen_del_ciudadano_y_del_comite_autorizado(self):
        url=reverse("obligacion_financiera_autocomplete")
        propios=self.client.get(url,{"forward":json.dumps({"ciudadano":self.ciudadano.pk})}).json()
        self.assertEqual([r["id"] for r in propios["results"]],[str(self.obligacion.pk)])
        ajenos=self.client.get(url,{"forward":json.dumps({"ciudadano":self.otro.pk})}).json()
        self.assertEqual(ajenos["results"],[])
        self.assertEqual(self.client.get(url).json()["results"],[])

    def test_selector_post_rechaza_ids_ajenos_y_no_registra_un_abono(self):
        url=reverse("seleccionar_obligacion")
        response=self.client.post(url,{"ciudadano":self.otro.pk,"obligacion":self.obligacion_ajena.pk})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Abono.objects.exists())
        response=self.client.post(url,{"ciudadano":self.ciudadano.pk,"obligacion":self.obligacion.pk})
        self.assertRedirects(response,reverse("acreditar_obligacion",args=[self.obligacion.pk]))
        self.assertFalse(Abono.objects.exists())

    def test_cambiar_ciudadano_no_admite_la_obligacion_del_anterior(self):
        otro_local=ObligacionCiudadano.objects.create(concepto=self.obligacion.concepto,ciudadano=self.otro,monto_asignado=100)
        response=self.client.post(reverse("seleccionar_obligacion"),{"ciudadano":self.otro.pk,"obligacion":self.obligacion.pk})
        self.assertEqual(response.status_code,200)
        self.assertIn("obligacion",response.context["form"].errors)

    def test_una_obligacion_pagada_no_se_ofrece_ni_se_acepta(self):
        self.obligacion.estado="PAGADO"
        self.obligacion.save()
        self.assertEqual(self.client.get(reverse("ciudadano_financiero_autocomplete"),{"q":"Ana"}).json()["results"],[])
        response=self.client.post(reverse("seleccionar_obligacion"),{"ciudadano":self.ciudadano.pk,"obligacion":self.obligacion.pk})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.context["form"].errors)

    def test_selectores_requieren_cargo_activo(self):
        for url in (reverse("ciudadano_financiero_autocomplete"),reverse("obligacion_financiera_autocomplete"),reverse("seleccionar_obligacion")):
            UsuarioApp.objects.filter(user=self.usuario).update(activo=False)
            self.assertEqual(self.client.get(url,{"q":"Ana"}).status_code,404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("ciudadano_financiero_autocomplete")).status_code,302)

    def test_selector_remoto_limita_resultados_y_no_incrusta_el_padron_en_html(self):
        ciudadanos=Ciudadano.objects.bulk_create([Ciudadano(nombre=f"Coincidencia {i}",apellido_paterno="Buscar") for i in range(25)])
        ObligacionCiudadano.objects.bulk_create([ObligacionCiudadano(concepto=self.obligacion.concepto,ciudadano=c,monto_asignado=100) for c in ciudadanos])
        response=self.client.get(reverse("ciudadano_financiero_autocomplete"),{"q":"Coincidencia"})
        self.assertEqual(len(response.json()["results"]),20)
        self.assertTrue(response.json()["pagination"]["more"])
        response=self.client.get(reverse("seleccionar_obligacion"))
        self.assertNotContains(response,"Coincidencia 24")
        self.assertContains(response,"data-autocomplete-light-url")

    def test_padron_busca_por_toma_y_mantiene_contexto_en_enlaces(self):
        self.client.force_login(self.admin)
        response=self.client.get(reverse("padron_ciudadanos"),{"q":"T-UI-099","page":"1"})
        self.assertEqual(list(response.context["ciudadanos"]),[self.ciudadano])
        self.assertContains(response,"return_to=")
        self.assertContains(response,"T-UI-099")
        columnas=list(response.context["tabla_ciudadanos"].columns.names())
        self.assertEqual(columnas,["ciudadano","manzana","activo","toma","acciones"])

    def test_atajos_datos_y_exportacion_usan_los_mismos_filtros(self):
        self.client.force_login(self.admin)
        self.ciudadano.manzana=Manzana.objects.create(nombre="Centro interfaz")
        self.ciudadano.save()
        response=self.client.get(reverse("padron_ciudadanos"),{"contrato":"sin_contrato"})
        self.assertEqual(response.context["ciudadanos"].paginator.count,0)
        response=self.client.get(reverse("padron_ciudadanos"),{"datos":"incompletos"})
        self.assertEqual(list(response.context["ciudadanos"]),[self.otro])
        exportacion=self.client.get(reverse("exportar_ciudadanos_csv"),{"datos":"incompletos"})
        self.assertNotContains(exportacion,"Ana")
        self.assertContains(exportacion,"Reservada")

    def test_tabla_ordena_antes_de_paginar_y_no_pierde_registros(self):
        self.client.force_login(self.admin)
        Ciudadano.objects.bulk_create([Ciudadano(nombre=f"Fila{i:02}",apellido_paterno=f"Apellido{i:02}") for i in range(25)])
        respuestas=[self.client.get(reverse("padron_ciudadanos"),{"orden_tabla":"-ciudadano","page":pagina}) for pagina in (1,2)]
        ids=[[c.pk for c in r.context["ciudadanos"]] for r in respuestas]
        self.assertFalse(set(ids[0]) & set(ids[1]))
        self.assertEqual(len(ids[0])+len(ids[1]),27)
        self.assertEqual(respuestas[0].context["ciudadanos"][0],self.otro)
        self.assertEqual(self.client.get(reverse("padron_ciudadanos"),{"orden_tabla":"manzana"}).status_code,200)

    def test_interfaz_dinamica_sigue_exigiendo_autorizacion(self):
        self.assertEqual(self.client.get(reverse("control_asistencias"),HTTP_X_PD_CONSULTATION="true").status_code,200)
        response=self.client.get(reverse("tesoreria_concepto_detalle",args=[self.obligacion_ajena.concepto_id]),HTTP_X_PD_CONSULTATION="true")
        self.assertEqual(response.status_code,404)

    def test_edicion_conserva_retorno_y_rechaza_destinos_externos(self):
        self.client.force_login(self.admin)
        url=reverse("editar_ciudadano_operativo",args=[self.ciudadano.pk])
        retorno=reverse("padron_ciudadanos")+"?q=Ana&page=2"
        response=self.client.get(url,{"return_to":retorno})
        self.assertEqual(response.context["return_to"],retorno)
        datos={"nombre":"Ana","apellido_paterno":"Propia","apellido_materno":"","edad":"30","fecha_nacimiento":"","sexo":"NO_ESPECIFICADO","numero_contrato":"C-UI-001","manzana":"","labor_social":"","motivo_alta":"","direccion":"","activo":"on","observaciones":"","return_to":retorno}
        response=self.client.post(url,datos)
        self.assertEqual(response.status_code,302)
        self.assertIn("return_to=",response.url)
        response=self.client.get(url,{"return_to":"https://example.com/externo"})
        self.assertEqual(response.context["return_to"],"")

    def test_identificador_malformado_no_produce_error_ni_amplia_busqueda(self):
        response=self.client.get(reverse("obligacion_financiera_autocomplete"),{"forward":json.dumps({"ciudadano":"9"*5000})})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()["results"],[])
        self.client.force_login(self.admin)
        response=self.client.get(reverse("padron_ciudadanos"),{"q":"T-UI-099","orden_tabla":"campo_inexistente"})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context["ciudadanos"].paginator.count,1)
