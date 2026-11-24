from datetime import timedelta
from decimal import Decimal
import uuid
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, IntegrityError
from django.db.models.deletion import ProtectedError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.comites.models import Comite, PerfilAcceso
from apps.comites.test_helpers import asignar_cargo
from apps.core.models import Ciudadano, Manzana
from .models import ConceptoTesoreria, ObligacionCiudadano, Abono, FondoRecurso, MovimientoRecurso, CorteRecurso, EventoCorteRecurso
from . import balances, recursos
from .balance_autorizacion import fondos_visibles


class BalanceRecursosTests(TestCase):
    def setUp(self):
        self.hoy=timezone.localdate()
        self.a=Comite.objects.create(nombre="Delegación local",tipo="DELEGACION")
        self.b=Comite.objects.create(nombre="Comité privado",tipo="AGUA")
        self.pres=self.cuenta("presidente", "PRESIDENTE")
        self.teso=self.cuenta("tesorero", "TESORERO")
        self.lect=self.cuenta("lectura", "LECTURA")
        self.deleg=self.cuenta("delegado", "DELEGADO")
        self.secret=self.cuenta("secretaria")
        self.secret.user_permissions.add(Permission.objects.get(codename="operar_secretaria_central"),Permission.objects.get(codename="operar_finanzas_centrales"))
        self.agregada=self.cuenta("agregada")
        self.agregada.user_permissions.add(Permission.objects.get(codename="operar_secretaria_central"),Permission.objects.get(codename="consultar_balance"))
        self.resp=self.cuenta("responsable")
        self.m=Manzana.objects.create(nombre="Centro",responsable=self.resp.perfil_acceso.ciudadano)
        self.n=Manzana.objects.create(nombre="Norte")
        c=self.resp.perfil_acceso.ciudadano;c.manzana=self.m;c.save()
        self.c=Ciudadano.objects.create(nombre="Ana personal",apellido_paterno="Reservado",manzana=self.m)
        self.concepto=self.concepto_nuevo("Cuota local")
        self.territorial=self.concepto_nuevo("Junta Centro",manzana=self.m,origen="JUNTA")
        self.ajeno=self.concepto_nuevo("Finanzas ajenas",comite=self.b)
        self.o=ObligacionCiudadano.objects.create(concepto=self.concepto,ciudadano=self.c,monto_asignado=100)
        self.ot=ObligacionCiudadano.objects.create(concepto=self.territorial,ciudadano=self.c,monto_asignado=100)
        self.oa=ObligacionCiudadano.objects.create(concepto=self.ajeno,ciudadano=self.c,monto_asignado=100)
        self.fondo=self.fondo_nuevo()
        self.fondot=self.fondo_nuevo(nombre="Recursos Centro",manzana=self.m,usuario=self.resp)

    def cuenta(self,nombre,rol=None,comite=None):
        user=get_user_model().objects.create_user(nombre,password="pw")
        if rol:
            asignar_cargo(user=user,comite=comite or self.a,rol=rol)
        else:
            PerfilAcceso.objects.create(user=user,ciudadano=Ciudadano.objects.create(nombre=nombre,apellido_paterno="Operador"))
        return user

    def concepto_nuevo(self,nombre,manzana=None,comite=None,origen="TESORERIA"):
        return ConceptoTesoreria.objects.create(concepto=nombre,comite=comite or self.a,alcance="MANZANA" if manzana else "GENERAL",manzana=manzana,origen=origen,naturaleza="PAGO",monto_individual=100,fecha=self.hoy)

    def fondo_nuevo(self,nombre="Operación local",manzana=None,usuario=None,comite=None):
        return recursos.abrir_fondo(usuario=usuario or self.teso,nombre=nombre,categoria="OPERACION",comite=comite or self.a,manzana=manzana,fecha_apertura=self.hoy,inicial_efectivo=500,inicial_transferencia=200,evidencia_apertura="Acta de apertura A-1")

    def salida(self,**kwargs):
        datos=dict(usuario=self.teso,fondo=self.fondo,monto=50,medio="EFECTIVO",fecha=self.hoy,categoria_salida="PAPELERIA",descripcion="Papel y tinta",beneficiario="Proveedor privado",evidencia="Factura referencia F-1",clave_operacion=uuid.uuid4())
        datos.update(kwargs)
        return recursos.registrar_salida(**datos)

    def enviar(self,**kwargs):
        datos=dict(usuario=self.teso,fondo=self.fondo,contado=recursos.resumen_fondo(self.fondo)["efectivo"],aclaracion="",evidencia_conteo="Acta de conteo C-1",clave_operacion=uuid.uuid4(),version=recursos.version_corte(self.fondo))
        datos.update(kwargs)
        return recursos.enviar_corte(**datos)

    def get(self,user,nombre,pk=None,**query):
        self.client.force_login(user)
        return self.client.get(reverse(nombre,args=[pk] if pk else []),query)

    def test_resumen_no_suma_apertura_ni_adeudos_como_recaudacion(self):
        self.o.acreditar(25,usuario=self.teso)
        r=self.get(self.teso,"balance_recaudacion")
        self.assertEqual(r.status_code,200)
        self.assertContains(r, timezone.localdate().strftime("%Y-%m-%d"))
        self.assertEqual(r.context["datos"]["recaudacion"]["valor"],25)
        self.assertEqual(r.context["datos"]["cartera"]["asignado"]["valor"],200)
        self.assertEqual(r.context["datos"]["cartera"]["saldo"],175)
        self.assertEqual(recursos.resumen_fondo(self.fondo)["total"],700)
        filtrado = self.get(self.teso, "balance_recaudacion", q="concepto inexistente inequívoco")
        self.assertEqual(filtrado.context["datos"]["recaudacion"]["valor"], 0)

    def test_cobro_fondo_y_salida_evidencia_y_reimpresion(self):
        a=self.o.acreditar(40,usuario=self.teso,fondo=self.fondo,medio="EFECTIVO",clave_operacion=uuid.uuid4())
        m=self.salida(monto=30)
        self.assertEqual(recursos.resumen_fondo(self.fondo)["efectivo"],510)
        self.assertEqual(a.movimiento_recurso.monto,40)
        self.assertEqual(self.get(self.lect,"comprobante_recurso",m.pk).status_code,200)
        self.assertEqual(self.get(self.lect,"comprobante_recurso",m.pk).status_code,200)
        self.assertEqual(MovimientoRecurso.objects.count(),2)
        self.assertEqual(Abono.objects.count(),1)

    def test_salida_repetida_es_idempotente_y_no_acepta_cambios(self):
        clave=uuid.uuid4()
        a=self.salida(clave_operacion=clave)
        self.assertEqual(a.pk,self.salida(clave_operacion=clave).pk)
        self.assertEqual(MovimientoRecurso.objects.count(),1)
        with self.assertRaises(ValidationError):self.salida(clave_operacion=clave,monto=51)

    def test_cobro_repetido_idempotente_aun_si_obligacion_pagada(self):
        clave=uuid.uuid4()
        a=self.o.acreditar(100,usuario=self.teso,fondo=self.fondo,medio="EFECTIVO",clave_operacion=clave)
        b=self.o.acreditar(100,usuario=self.teso,fondo=self.fondo,medio="EFECTIVO",clave_operacion=clave)
        self.assertEqual(a.pk,b.pk)
        self.assertEqual(Abono.objects.count(),1)
        self.assertEqual(MovimientoRecurso.objects.count(),1)
        with self.assertRaises(ValidationError):self.o.acreditar(99,usuario=self.teso,fondo=self.fondo,medio="EFECTIVO",clave_operacion=clave)

    def test_no_sobre_giro_y_no_dinero_negativo_no_finito(self):
        for monto in (501,0,-1,"NaN","Infinity","1.001"):
            with self.subTest(monto=monto),self.assertRaises(ValidationError):self.salida(monto=monto)
        self.assertFalse(MovimientoRecurso.objects.exists())

    def test_transferencia_no_aumenta_efectivo_y_exige_referencia(self):
        with self.assertRaises(ValidationError):self.o.acreditar(20,usuario=self.teso,fondo=self.fondo,medio="TRANSFERENCIA",clave_operacion=uuid.uuid4())
        self.assertFalse(Abono.objects.exists())
        self.o.acreditar(20,usuario=self.teso,referencia="TRANS-001",fondo=self.fondo,medio="TRANSFERENCIA",clave_operacion=uuid.uuid4())
        saldo=recursos.resumen_fondo(self.fondo)
        self.assertEqual(saldo["efectivo"],500)
        self.assertEqual(saldo["transferencia"],220)

    def test_lector_sin_escrituras_por_post_ni_servicio(self):
        for ruta,pk in (("fondo_recurso_salida",self.fondo.pk),("preparar_corte_recurso",self.fondo.pk),("fondo_recurso_crear",None)):
            self.client.force_login(self.lect)
            self.assertEqual(self.client.post(reverse(ruta,args=[pk] if pk else [])).status_code,404)
        with self.assertRaises(PermissionDenied):self.salida(usuario=self.lect)

    def test_territorial_no_general_ni_otros_fondos_con_permisos_heredados(self):
        self.resp.user_permissions.set(Permission.objects.all())
        self.assertEqual(list(fondos_visibles(self.resp)),[self.fondot])
        with self.assertRaises(ValidationError):self.o.acreditar(10,usuario=self.resp,fondo=self.fondot,medio="EFECTIVO",clave_operacion=uuid.uuid4())
        self.ot.acreditar(10,usuario=self.resp,fondo=self.fondot,medio="EFECTIVO",clave_operacion=uuid.uuid4())
        self.assertEqual(self.get(self.resp,"fondo_recurso_detalle",self.fondo.pk).status_code,404)
        self.assertEqual(self.get(self.resp,"balance_concepto_detalle",self.concepto.pk).status_code,404)
        self.assertEqual(self.get(self.resp,"balance_concepto_detalle",self.ajeno.pk).status_code,404)

    def test_comite_ajeno_no_fuga_en_consultas_csv_o_filtros(self):
        self.oa.acreditar(17)
        for ruta in ("balance_recaudacion","balance_conceptos","balance_transparencia"):
            r=self.get(self.teso,ruta)
            self.assertEqual(r.status_code,200)
            self.assertNotContains(r,"Finanzas ajenas")
            self.assertNotContains(r,"Comité privado")
        r=self.get(self.teso,"balance_transparencia",exportar="csv",comite=self.b.pk)
        self.assertEqual(r.status_code,400)

    def test_transparencia_no_personas_beneficiarios_ni_contratos(self):
        self.o.acreditar(20,usuario=self.teso)
        self.salida()
        r=self.get(self.lect,"balance_transparencia")
        self.assertNotContains(r,"Ana personal")
        self.assertNotContains(r,"Proveedor privado")
        csv=self.get(self.lect,"balance_transparencia",exportar="csv")
        self.assertEqual(csv.status_code,200)
        self.assertNotContains(csv,"Ana personal")
        self.assertContains(csv,"Metodología")

    def test_secretaria_agregada_no_tesoreria_individual_recursos_o_padron_tecnico(self):
        self.assertEqual(self.get(self.agregada,"balance_recaudacion").status_code,200)
        r=self.get(self.agregada,"balance_concepto_detalle",self.concepto.pk)
        self.assertEqual(r.status_code,200)
        self.assertNotContains(r,"Ana personal")
        self.assertEqual(self.get(self.agregada,"fondo_recurso_detalle",self.fondo.pk).status_code,404)
        self.assertEqual(self.get(self.agregada,"tesoreria_operativa").status_code,404)

    def test_origen_se_conserva_y_cancelacion_no_desaparece_ingreso(self):
        self.ot.acreditar(25,usuario=self.teso)
        ObligacionCiudadano.objects.filter(pk=self.ot.pk).update(estado="CANCELADO")
        r=self.get(self.teso,"balance_recaudacion")
        d=r.context["datos"]
        self.assertEqual(d["recaudacion"]["valor"],25)
        self.assertEqual(d["cantidad_cobros_canceladas"],1)
        self.assertEqual(d["origenes"][0]["etiqueta"],"Junta")
        self.assertEqual(d["cartera"]["asignado"]["valor"],100)

    def test_cartera_parciales_no_multiplican_asignado(self):
        self.o.acreditar(10,usuario=self.teso)
        self.o.acreditar(15,usuario=self.teso)
        r=self.get(self.teso,"balance_concepto_detalle",self.concepto.pk)
        self.assertEqual(r.context["cartera"]["asignado"]["valor"],100)
        self.assertEqual(r.context["cartera"]["saldo"],75)

    def test_fechas_de_pago_y_cohorte_no_se_confunden(self):
        self.o.acreditar(20,fecha=self.hoy-timedelta(days=40),usuario=self.teso)
        r=self.get(self.teso,"balance_recaudacion")
        self.assertEqual(r.context["datos"]["recaudacion"]["valor"],0)
        self.assertEqual(r.context["datos"]["cartera"]["saldo"],180)
        self.assertEqual(self.get(self.teso,"balance_recaudacion",desde="invalid").status_code,200)
        self.assertEqual(self.get(self.teso,"balance_transparencia",exportar="csv",desde="invalid").status_code,400)

    def test_envio_lectura_revisor_distinto_confirmacion_y_copia_estable(self):
        self.salida(monto=20)
        c=self.enviar()
        original=c.manifiesto.copy()
        self.assertEqual(self.get(self.lect,"corte_recurso_detalle",c.pk).status_code,200)
        self.assertContains(self.get(self.lect,"corte_recurso_detalle",c.pk),"En revisión")
        with self.assertRaises(PermissionDenied):recursos.revisar_corte(usuario=self.teso,corte=c,accion="CONFIRMAR",motivo="Revisión")
        self.salida(monto=10)
        c.refresh_from_db()
        self.assertEqual(c.manifiesto,original)
        recursos.revisar_corte(usuario=self.pres,corte=c,accion="CONFIRMAR",motivo="Acta cotejada")
        c.refresh_from_db()
        self.assertEqual(c.estado,"CONFIRMADO")
        self.assertEqual(c.esperado,480)
        self.assertEqual(recursos.resumen_fondo(self.fondo)["efectivo"],470)

    def test_diferencia_solicitud_aclaracion_nuevo_envio_sin_editar_original(self):
        with self.assertRaises(ValidationError):self.enviar(contado=490)
        c=self.enviar(contado=490,aclaracion="Faltante por revisar")
        with self.assertRaises(ValidationError):recursos.revisar_corte(usuario=self.pres,corte=c,accion="CONFIRMAR",motivo="Visto")
        recursos.revisar_corte(usuario=self.pres,corte=c,accion="DEVOLVER",motivo="Recontar efectivo")
        nuevo=self.enviar()
        self.assertNotEqual(c.pk,nuevo.pk)
        c.refresh_from_db()
        self.assertEqual(c.contado,490)
        self.assertEqual(c.estado,"DEVUELTO")
        self.assertEqual(c.eventos.count(),2)

    def test_envio_repetido_idempotente_y_un_corte_abierto(self):
        clave=uuid.uuid4(); version=recursos.version_corte(self.fondo)
        c=self.enviar(clave_operacion=clave,version=version)
        self.assertEqual(c.pk,self.enviar(clave_operacion=clave,version=version).pk)
        self.assertEqual(c.eventos.count(),1)
        with self.assertRaises(ValidationError):self.enviar()

    def test_movimiento_entre_conteo_y_envio_exige_revisar(self):
        version=recursos.version_corte(self.fondo)
        self.salida()
        with self.assertRaises(ValidationError):self.enviar(version=version)
        self.assertFalse(CorteRecurso.objects.exists())

    def test_segundo_corte_no_suma_apertura_o_cobros_dos_veces(self):
        self.o.acreditar(20,usuario=self.teso,fondo=self.fondo,medio="EFECTIVO",clave_operacion=uuid.uuid4())
        c=self.enviar();recursos.revisar_corte(usuario=self.pres,corte=c,accion="CONFIRMAR",motivo="Conteo revisado")
        self.salida(monto=10)
        d=recursos.manifiesto_corte(self.fondo)
        self.assertEqual(Decimal(d["inicial_efectivo"]),520)
        self.assertEqual(Decimal(d["cobros_efectivo"]),0)
        self.assertEqual(Decimal(d["esperado"]),510)

    def test_delegado_revisa_delegacion_secretaria_no_se_autoaprueba(self):
        c=self.enviar(usuario=self.secret)
        recursos.revisar_corte(usuario=self.deleg,corte=c,accion="CONFIRMAR",motivo="Visto por Delegación")
        c.refresh_from_db();self.assertEqual(c.revisado_por,self.deleg)
        with self.assertRaises(PermissionDenied):self.enviar(usuario=self.pres)

    def test_superusuario_tecnico_no_se_convierte_en_revisor(self):
        u=get_user_model().objects.create_superuser("root",password="pw")
        c=self.enviar()
        with self.assertRaises(PermissionDenied):recursos.revisar_corte(usuario=u,corte=c,accion="CONFIRMAR",motivo="Admin")
        with self.assertRaises(PermissionDenied):self.salida(usuario=u)

    def test_lector_post_revision_y_csrf_denegados(self):
        c=self.enviar()
        self.client.force_login(self.lect)
        self.assertEqual(self.client.post(reverse("corte_recurso_revisar",args=[c.pk]),{"accion":"CONFIRMAR","motivo":"Manipulado"}).status_code,404)
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.teso)
        self.assertEqual(csrf.post(reverse("fondo_recurso_salida",args=[self.fondo.pk]),{}).status_code,403)

    def test_estado_inactivo_o_identidad_inconsistente_no_concede_acceso(self):
        self.teso.perfiles_app.update(activo=False)
        self.assertEqual(self.get(self.teso,"balance_recaudacion").status_code,404)
        self.assertEqual(self.get(self.teso,"fondo_recurso_detalle",self.fondo.pk).status_code,404)
        with self.assertRaises(PermissionDenied):self.salida()

    def test_fuentes_documentadas_no_se_editan_ni_eliminan(self):
        a=self.o.acreditar(20,usuario=self.teso,fondo=self.fondo,medio="EFECTIVO",clave_operacion=uuid.uuid4())
        a.notas="Cambio posterior"
        with self.assertRaises(ValidationError):a.save()
        with self.assertRaises(ProtectedError):self.concepto.delete()
        m=self.salida()
        with self.assertRaises(ValidationError):m.delete()
        with self.assertRaises(ValidationError):MovimientoRecurso.objects.filter(pk=m.pk).update(monto=10)
        c=self.enviar()
        c.esperado=1
        with self.assertRaises(ValidationError):c.save()

    def test_post_abono_fondo_incluye_medios_y_reintento(self):
        self.client.force_login(self.teso)
        url=reverse("acreditar_obligacion",args=[self.o.pk])
        datos={"monto":"100","fecha":str(self.hoy),"fondo_recurso":self.fondo.pk,"medio_recurso":"EFECTIVO","clave_recurso":str(uuid.uuid4())}
        self.assertEqual(self.client.post(url,datos).status_code,302)
        self.assertEqual(self.client.post(url,datos).status_code,302)
        self.assertEqual(Abono.objects.count(),1)
        self.assertEqual(MovimientoRecurso.objects.count(),1)

    def test_cobro_fondo_ajeno_no_guarda_abono(self):
        with self.assertRaises(ValidationError):self.oa.acreditar(20,usuario=self.secret,fondo=self.fondo,medio="EFECTIVO",clave_operacion=uuid.uuid4())
        self.assertFalse(Abono.objects.exists())

    def test_todas_las_pantallas_y_metodos_son_operativos(self):
        c=self.enviar()
        m=self.salida()
        rutas=[("balance_recaudacion",None),("balance_conceptos",None),("balance_concepto_detalle",self.concepto.pk),("balance_transparencia",None),("fondos_recursos",None),("fondo_recurso_crear",None),("fondo_recurso_detalle",self.fondo.pk),("fondo_recurso_salida",self.fondo.pk),("comprobante_recurso",m.pk),("preparar_corte_recurso",self.fondo.pk),("cortes_recursos",None),("corte_recurso_detalle",c.pk)]
        for ruta,pk in rutas:
            with self.subTest(ruta=ruta):self.assertEqual(self.get(self.teso,ruta,pk).status_code,200)
        self.assertEqual(self.get(self.pres,"corte_recurso_revisar",c.pk).status_code,405)

    def test_apertura_recursos_inactivos_fechas_y_ambito(self):
        with self.assertRaises(PermissionDenied):self.fondo_nuevo(usuario=self.lect)
        with self.assertRaises(PermissionDenied):self.fondo_nuevo(usuario=self.resp)
        with self.assertRaises(PermissionDenied):self.fondo_nuevo(comite=self.b)
        with self.assertRaises(ValidationError):self.salida(fecha=self.hoy+timedelta(days=1))
        self.fondo.activo=False;self.fondo.save()
        with self.assertRaises(PermissionDenied):self.salida()

    def test_base_protege_ledger_fuente_apertura_y_corte_por_sql(self):
        from django.db import connection, DatabaseError
        a=self.o.acreditar(20,usuario=self.teso,fondo=self.fondo,medio="EFECTIVO",clave_operacion=uuid.uuid4())
        c=self.enviar()
        sentencias=[
            ("UPDATE tesoreria_abono SET monto = %s WHERE id = %s",[19,a.pk]),
            ("UPDATE tesoreria_fondorecurso SET inicial_efectivo = %s WHERE id = %s",[1000,self.fondo.pk]),
            ("UPDATE tesoreria_corterecurso SET esperado = %s WHERE id = %s",[1,c.pk.hex if connection.vendor=="sqlite" else c.pk]),
        ]
        for sql,params in sentencias:
            with self.subTest(sql=sql),self.assertRaises(DatabaseError),transaction.atomic():
                with connection.cursor() as cursor:cursor.execute(sql,params)
        a.refresh_from_db();self.assertEqual(a.monto,20)
        self.fondo.refresh_from_db();self.assertEqual(self.fondo.inicial_efectivo,500)

    def test_reenvio_apertura_no_duplica_el_recurso(self):
        clave=uuid.uuid4()
        datos=dict(usuario=self.teso,nombre="Reserva con referencia única",categoria="RESERVA",comite=self.a,manzana=None,fecha_apertura=self.hoy,inicial_efectivo=300,inicial_transferencia=0,evidencia_apertura="Acta repetida",clave_apertura=clave)
        f=recursos.abrir_fondo(**datos)
        self.assertEqual(recursos.abrir_fondo(**datos).pk,f.pk)
        with self.assertRaises(ValidationError):recursos.abrir_fondo(**{**datos,"inicial_efectivo":301})
