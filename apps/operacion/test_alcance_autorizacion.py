from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.comites.models import PerfilAcceso, Comite, UsuarioApp
from apps.core.models import Ciudadano, Manzana
from apps.operacion.models import AsistenciaJunta, Faena, Junta, RegistroFaena


class AlcanceOperacionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.responsable = User.objects.create_user(username="operacion-centro", password="test-pass")
        self.comite = Comite.objects.create(nombre="Comité de agua")
        self.ciudadano_responsable = Ciudadano.objects.create(nombre="Rosa", apellido_paterno="Responsable")
        self.manzana = Manzana.objects.create(nombre="Centro", responsable=self.ciudadano_responsable)
        self.ciudadano_responsable.manzana = self.manzana
        self.ciudadano_responsable.save(update_fields=["manzana"])
        PerfilAcceso.objects.create(user=self.responsable, ciudadano=self.ciudadano_responsable)
        self.ciudadano_local = Ciudadano.objects.create(nombre="Ana", apellido_paterno="Local", manzana=self.manzana)
        otra_manzana = Manzana.objects.create(nombre="Norte")
        self.ciudadano_ajeno = Ciudadano.objects.create(nombre="Luis", apellido_paterno="Ajeno", manzana=otra_manzana)

        self.faena_local = Faena.objects.create(
            comite=self.comite, fecha=date(2026, 10, 1), alcance=Faena.Alcances.MANZANA,
            manzana=self.manzana, descripcion="Limpieza Centro",
        )
        self.faena_ajena = Faena.objects.create(
            comite=self.comite, fecha=date(2026, 10, 2), alcance=Faena.Alcances.MANZANA,
            manzana=otra_manzana, descripcion="Limpieza Norte",
        )
        self.faena_general = Faena.objects.create(
            comite=self.comite, fecha=date(2026, 10, 3), alcance=Faena.Alcances.GENERAL,
            descripcion="Limpieza general",
        )
        self.registro_local = RegistroFaena.objects.create(faena=self.faena_general, ciudadano=self.ciudadano_local)
        self.registro_ajeno = RegistroFaena.objects.create(faena=self.faena_general, ciudadano=self.ciudadano_ajeno)
        self.junta_general = Junta.objects.create(
            comite=self.comite, fecha=date(2026, 10, 4), alcance=Junta.Alcances.GENERAL, tema="Asamblea general",
        )
        self.asistencia_local = AsistenciaJunta.objects.create(junta=self.junta_general, ciudadano=self.ciudadano_local)
        self.asistencia_ajena = AsistenciaJunta.objects.create(junta=self.junta_general, ciudadano=self.ciudadano_ajeno)

    def test_queryset_de_faenas_y_registros_deriva_el_alcance_del_responsable(self):
        self.assertQuerySetEqual(
            Faena.objects.visibles_para(self.responsable).order_by("pk"),
            [self.faena_local, self.faena_general],
        )
        self.assertQuerySetEqual(
            RegistroFaena.objects.visibles_para(self.responsable).order_by("pk"),
            [self.registro_local],
        )

    def test_queryset_de_juntas_y_asistencias_limita_participantes_en_evento_general(self):
        self.assertQuerySetEqual(
            Junta.objects.visibles_para(self.responsable).order_by("pk"),
            [self.junta_general],
        )
        self.assertQuerySetEqual(
            AsistenciaJunta.objects.visibles_para(self.responsable).order_by("pk"),
            [self.asistencia_local],
        )

    def test_detalle_y_exportacion_de_evento_general_solo_muestran_su_manzana(self):
        self.client.force_login(self.responsable)
        detalle = self.client.get(reverse("control_asistencias_faena_detalle", args=[self.faena_general.pk]))
        exportacion = self.client.get(reverse("exportar_participantes_faena_csv", args=[self.faena_general.pk]))
        texto = exportacion.content.decode("utf-8-sig")

        self.assertEqual(detalle.status_code, 200)
        self.assertContains(detalle, "Ana Local")
        self.assertNotContains(detalle, "Luis Ajeno")
        self.assertIn("Ana Local", texto)
        self.assertNotIn("Luis Ajeno", texto)

    def test_detalle_y_exportacion_de_junta_general_solo_muestran_su_manzana(self):
        self.client.force_login(self.responsable)
        detalle = self.client.get(reverse("control_asistencias_junta_detalle", args=[self.junta_general.pk]))
        exportacion = self.client.get(reverse("exportar_participantes_junta_csv", args=[self.junta_general.pk]))
        texto = exportacion.content.decode("utf-8-sig")

        self.assertEqual(detalle.status_code, 200)
        self.assertContains(detalle, "Ana Local")
        self.assertNotContains(detalle, "Luis Ajeno")
        self.assertIn("Ana Local", texto)
        self.assertNotIn("Luis Ajeno", texto)

    def test_peticion_directa_a_evento_de_otra_manzana_devuelve_404(self):
        self.client.force_login(self.responsable)
        response = self.client.get(reverse("control_asistencias_faena_detalle", args=[self.faena_ajena.pk]))
        self.assertEqual(response.status_code, 404)

    def test_lista_operativa_no_incluye_eventos_de_otra_manzana(self):
        self.client.force_login(self.responsable)
        response = self.client.get(reverse("control_asistencias"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Limpieza Centro")
        self.assertNotContains(response, "Limpieza Norte")

    def test_edicion_y_cambio_de_estado_de_evento_general_no_se_abren_al_responsable(self):
        self.client.force_login(self.responsable)
        edicion = self.client.get(reverse("editar_faena_operativa", args=[self.faena_general.pk]))
        estado = self.client.get(reverse("editar_estado_evento", args=["faena", self.faena_general.pk]))

        self.assertEqual(edicion.status_code, 404)
        self.assertEqual(estado.status_code, 404)

    def test_responsable_puede_editar_y_cambiar_estado_de_evento_de_su_manzana(self):
        self.client.force_login(self.responsable)
        edicion = self.client.get(reverse("editar_faena_operativa", args=[self.faena_local.pk]))
        estado = self.client.post(
            reverse("editar_estado_evento", args=["faena", self.faena_local.pk]),
            {"estado": Faena.Estados.CANCELADA},
        )

        self.faena_local.refresh_from_db()
        self.assertEqual(edicion.status_code, 200)
        self.assertEqual(estado.status_code, 302)
        self.assertEqual(self.faena_local.estado, Faena.Estados.CANCELADA)

    def test_tesorero_no_recibe_alcance_operativo_por_su_cargo(self):
        tesorero = get_user_model().objects.create_user(username="tesorero-sin-operacion")
        UsuarioApp.objects.create(user=tesorero, comite=self.comite, rol=UsuarioApp.Roles.TESORERO)
        self.assertFalse(Faena.objects.visibles_para(tesorero).exists())
        self.client.force_login(tesorero)
        self.assertEqual(
            self.client.get(reverse("control_asistencias_faena_detalle", args=[self.faena_local.pk])).status_code,
            404,
        )

    def test_exportacion_directa_de_evento_ajeno_devuelve_404(self):
        self.client.force_login(self.responsable)
        response = self.client.get(reverse("exportar_participantes_faena_csv", args=[self.faena_ajena.pk]))
        self.assertEqual(response.status_code, 404)

    def test_responsable_crea_faena_solo_en_su_manzana(self):
        self.client.force_login(self.responsable)
        formulario = self.client.get(reverse("crear_faena_operativa"))
        self.assertEqual(formulario.status_code, 200)
        self.assertNotIn("comite", formulario.context["form"].fields)
        self.assertIn("motivo", formulario.context["form"].fields)
        response = self.client.post(
            reverse("crear_faena_operativa"),
            {
                "fecha": "2026-10-20",
                "descripcion": "Poda Centro",
                "alcance": Faena.Alcances.MANZANA,
                "manzana": self.manzana.pk,
                "motivo": "Retirar ramas que obstruyen el paso",
                "estado": Faena.Estados.PROGRAMADA,
                "notas": "",
            },
        )

        creada = Faena.objects.get(descripcion="Poda Centro")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(creada.alcance, Faena.Alcances.MANZANA)
        self.assertEqual(creada.manzana_id, self.manzana.pk)
        self.assertIsNone(creada.comite_id)
        self.assertEqual(creada.motivo, "Retirar ramas que obstruyen el paso")

    def test_responsable_no_puede_tamperar_alcance_o_manzana_al_crear_faena(self):
        otra_manzana = self.ciudadano_ajeno.manzana
        self.client.force_login(self.responsable)
        response = self.client.post(
            reverse("crear_faena_operativa"),
            {
                "comite": self.comite.pk,
                "fecha": "2026-10-20",
                "descripcion": "Poda ajena",
                "alcance": Faena.Alcances.MANZANA,
                "manzana": otra_manzana.pk,
                "motivo": "Trabajo de prueba en otra manzana",
                "estado": Faena.Estados.PROGRAMADA,
                "notas": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Faena.objects.filter(descripcion="Poda ajena").exists())

    def test_presidente_solo_ve_y_edita_eventos_generales_de_su_comite(self):
        presidente = get_user_model().objects.create_user(username="presidente-op")
        UsuarioApp.objects.create(
            user=presidente, comite=self.comite, rol=UsuarioApp.Roles.PRESIDENTE
        )
        otro_comite = Comite.objects.create(nombre="Comité vecino")
        general_ajena = Faena.objects.create(
            comite=otro_comite,
            fecha=date(2026, 10, 5),
            alcance=Faena.Alcances.GENERAL,
            descripcion="Faena de otro comité",
        )

        self.assertQuerySetEqual(
            Faena.objects.visibles_para(presidente).order_by("pk"),
            [self.faena_general],
        )
        self.assertQuerySetEqual(
            RegistroFaena.objects.visibles_para(presidente).order_by("pk"),
            [self.registro_local, self.registro_ajeno],
        )
        self.assertQuerySetEqual(
            AsistenciaJunta.objects.visibles_para(presidente).order_by("pk"),
            [self.asistencia_local, self.asistencia_ajena],
        )
        self.client.force_login(presidente)
        self.assertEqual(
            self.client.get(reverse("editar_faena_operativa", args=[self.faena_general.pk])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("editar_faena_operativa", args=[general_ajena.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("editar_faena_operativa", args=[self.faena_local.pk])).status_code,
            404,
        )

    def test_presidente_crea_evento_general_limitado_a_su_comite(self):
        presidente = get_user_model().objects.create_user(username="presidente-crea-op")
        UsuarioApp.objects.create(
            user=presidente, comite=self.comite, rol=UsuarioApp.Roles.PRESIDENTE
        )
        otro_comite = Comite.objects.create(nombre="Comité vecino")
        self.client.force_login(presidente)

        formulario = self.client.get(reverse("crear_faena_operativa"))
        self.assertEqual(formulario.status_code, 200)
        form = formulario.context["form"]
        self.assertEqual(set(form.fields["comite"].queryset.values_list("pk", flat=True)), {self.comite.pk})
        self.assertEqual(form.fields["alcance"].choices, [(Faena.Alcances.GENERAL, "Toda la comunidad")])

        response = self.client.post(
            reverse("crear_faena_operativa"),
            {
                "comite": self.comite.pk,
                "fecha": "2026-10-20",
                "descripcion": "Faena presidencial",
                "alcance": Faena.Alcances.GENERAL,
                "manzana": "",
                "estado": Faena.Estados.PROGRAMADA,
                "notas": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Faena.objects.get(descripcion="Faena presidencial").comite_id, self.comite.pk)
        self.assertFalse(Faena.objects.filter(descripcion="Faena presidencial", comite=otro_comite).exists())

    def test_presidente_captura_y_exporta_todos_los_registros_de_su_faena_general(self):
        presidente = get_user_model().objects.create_user(username="presidente-captura-op")
        UsuarioApp.objects.create(
            user=presidente, comite=self.comite, rol=UsuarioApp.Roles.PRESIDENTE
        )
        otro_comite = Comite.objects.create(nombre="Comité ajeno")
        faena_ajena = Faena.objects.create(
            comite=otro_comite,
            fecha=date(2026, 10, 5),
            alcance=Faena.Alcances.GENERAL,
            descripcion="Faena ajena",
        )
        RegistroFaena.objects.create(faena=faena_ajena, ciudadano=self.ciudadano_local)
        self.client.force_login(presidente)

        exportacion = self.client.get(
            reverse("exportar_participantes_faena_csv", args=[self.faena_general.pk])
        )
        exportacion_ajena = self.client.get(
            reverse("exportar_participantes_faena_csv", args=[faena_ajena.pk])
        )
        captura = self.client.post(
            reverse("captura_asistencia_faena", args=[self.faena_general.pk]),
            {
                f"registro_{self.registro_local.pk}_estatus": RegistroFaena.Estatus.ASISTIO,
                f"registro_{self.registro_ajeno.pk}_estatus": RegistroFaena.Estatus.FALTO,
            },
        )

        self.registro_local.refresh_from_db()
        self.registro_ajeno.refresh_from_db()
        self.assertEqual(exportacion.status_code, 200)
        self.assertIn("Ana Local", exportacion.content.decode("utf-8-sig"))
        self.assertIn("Luis Ajeno", exportacion.content.decode("utf-8-sig"))
        self.assertEqual(exportacion_ajena.status_code, 404)
        self.assertEqual(captura.status_code, 302)
        self.assertEqual(self.registro_local.estatus, RegistroFaena.Estatus.ASISTIO)
        self.assertEqual(self.registro_ajeno.estatus, RegistroFaena.Estatus.FALTO)

    def test_control_asistencias_muestra_metricas_de_todas_las_manzanas_al_presidente(self):
        presidente = get_user_model().objects.create_user(username="presidente-metricas-op")
        UsuarioApp.objects.create(
            user=presidente, comite=self.comite, rol=UsuarioApp.Roles.PRESIDENTE
        )
        self.client.force_login(presidente)

        response = self.client.get(reverse("control_asistencias"))

        faena = next(evento for evento in response.context["faenas"] if evento.pk == self.faena_general.pk)
        self.assertEqual(faena.total_participantes, 2)
        self.assertEqual(faena.pendientes, 2)

    def test_responsable_crea_junta_de_manzana_sin_comite_y_con_motivo(self):
        self.client.force_login(self.responsable)
        formulario = self.client.get(reverse("crear_junta_operativa"))
        self.assertEqual(formulario.status_code, 200)
        self.assertNotIn("comite", formulario.context["form"].fields)
        response = self.client.post(
            reverse("crear_junta_operativa"),
            {
                "fecha": "2026-10-20",
                "tipo": Junta.Tipos.ORDINARIA,
                "lugar": "Centro de la manzana",
                "tema": "Organización vecinal",
                "alcance": Junta.Alcances.MANZANA,
                "manzana": self.manzana.pk,
                "motivo": "Coordinar la reparación del alumbrado",
                "estado": Junta.Estados.PROGRAMADA,
                "notas": "",
            },
        )

        creada = Junta.objects.get(tema="Organización vecinal")
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(creada.comite_id)
        self.assertEqual(creada.manzana_id, self.manzana.pk)
        self.assertEqual(creada.motivo, "Coordinar la reparación del alumbrado")

    def test_captura_no_actualiza_registros_de_otra_manzana(self):
        self.client.force_login(self.responsable)
        self.registro_local.estatus = RegistroFaena.Estatus.PENDIENTE
        self.registro_local.save(update_fields=["estatus", "updated_at"])
        self.registro_ajeno.estatus = RegistroFaena.Estatus.PENDIENTE
        self.registro_ajeno.save(update_fields=["estatus", "updated_at"])

        response = self.client.post(
            reverse("captura_asistencia_faena", args=[self.faena_general.pk]),
            {f"registro_{self.registro_local.pk}_estatus": RegistroFaena.Estatus.ASISTIO,
             f"registro_{self.registro_ajeno.pk}_estatus": RegistroFaena.Estatus.FALTO},
        )

        self.registro_local.refresh_from_db()
        self.registro_ajeno.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.registro_local.estatus, RegistroFaena.Estatus.ASISTIO)
        self.assertEqual(self.registro_ajeno.estatus, RegistroFaena.Estatus.PENDIENTE)

    def test_captura_secuencial_rechaza_id_de_participante_ajeno(self):
        self.client.force_login(self.responsable)
        response = self.client.post(
            reverse("captura_asistencia_secuencial_faena", args=[self.faena_general.pk]),
            {"action": "asistio", "record_id": self.registro_ajeno.pk},
        )

        self.registro_ajeno.refresh_from_db()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.registro_ajeno.estatus, RegistroFaena.Estatus.PENDIENTE)

    def test_superusuario_mantiene_acceso_global_a_eventos_y_registros(self):
        admin = get_user_model().objects.create_superuser(
            username="admin-op", password="test-pass", email="admin@example.com"
        )
        self.assertQuerySetEqual(
            Faena.objects.visibles_para(admin).order_by("pk"),
            [self.faena_local, self.faena_ajena, self.faena_general],
        )
        self.assertQuerySetEqual(
            RegistroFaena.objects.visibles_para(admin).order_by("pk"),
            [self.registro_local, self.registro_ajeno],
        )

    def _presidente(self):
        usuario = get_user_model().objects.create_user(username="presidente-politica")
        self.cargo = UsuarioApp.objects.create(user=usuario, comite=self.comite, rol=UsuarioApp.Roles.PRESIDENTE)
        return usuario

    def _eventos_generales(self):
        return (("faena", self.faena_general, self.registro_local, self.registro_ajeno),
                ("junta", self.junta_general, self.asistencia_local, self.asistencia_ajena))

    def test_presidente_genera_participantes_de_faena_y_junta_idempotentemente(self):
        self.client.force_login(self._presidente())
        for tipo, evento, _, _ in self._eventos_generales():
            with self.subTest(tipo=tipo):
                relacion = evento.registros if tipo == "faena" else evento.asistencias
                antes = dict(relacion.values_list("pk", "estatus"))
                url = reverse(f"generar_registros_{tipo}", args=[evento.pk])
                self.assertEqual(self.client.post(url).status_code, 302)
                self.assertSetEqual(set(relacion.values_list("ciudadano_id", flat=True)),
                                    set(Ciudadano.objects.filter(activo=True).values_list("pk", flat=True)))
                total = relacion.count()
                self.assertEqual(self.client.post(url).status_code, 302)
                self.assertEqual(relacion.count(), total)
                for pk, estado in antes.items():
                    self.assertEqual(relacion.get(pk=pk).estatus, estado)

    def test_lector_no_puede_capturar_generar_editar_ni_cambiar_estado(self):
        from django.contrib.auth.models import Permission
        lector = get_user_model().objects.create_user(username="lector-operacion")
        lector.user_permissions.set(Permission.objects.filter(content_type__app_label="operacion", codename__startswith="view_"))
        self.client.force_login(lector)
        for tipo, evento, local, ajeno in self._eventos_generales():
            with self.subTest(tipo=tipo):
                detalle = self.client.get(reverse(f"control_asistencias_{tipo}_detalle", args=[evento.pk]))
                self.assertEqual(detalle.status_code, 200)
                self.assertFalse(detalle.context["can_capture"])
                for ruta in (f"captura_asistencia_{tipo}", f"captura_asistencia_secuencial_{tipo}"):
                    url = reverse(ruta, args=[evento.pk])
                    self.assertEqual(self.client.get(url).status_code, 404)
                    self.assertEqual(self.client.post(url, {
                        f"registro_{ajeno.pk}_estatus": "ASISTIO", "action": "asistio", "record_id": ajeno.pk,
                    }).status_code, 404)
                self.assertEqual(self.client.post(reverse(f"generar_registros_{tipo}", args=[evento.pk])).status_code, 404)
                self.assertEqual(self.client.post(reverse(f"editar_{tipo}_operativa", args=[evento.pk]), {"estado": "CANCELADA"}).status_code, 404)
                self.assertEqual(self.client.post(reverse("editar_estado_evento", args=[tipo, evento.pk]), {"estado": "CANCELADA"}).status_code, 404)
                ajeno.refresh_from_db()
                evento.refresh_from_db()
                self.assertEqual(ajeno.estatus, "PENDIENTE")
                self.assertEqual(evento.estado, "PROGRAMADA")

    def test_permiso_de_lectura_global_no_amplia_captura_del_responsable(self):
        from django.contrib.auth.models import Permission
        self.responsable.user_permissions.set(Permission.objects.filter(content_type__app_label="operacion", codename__startswith="view_"))
        self.client.force_login(self.responsable)
        for tipo, evento, local, ajeno in self._eventos_generales():
            with self.subTest(tipo=tipo):
                response = self.client.post(reverse(f"captura_asistencia_{tipo}", args=[evento.pk]), {
                    f"registro_{local.pk}_estatus": "ASISTIO", f"registro_{ajeno.pk}_estatus": "ASISTIO",
                })
                self.assertEqual(response.status_code, 302)
                local.refresh_from_db()
                ajeno.refresh_from_db()
                self.assertEqual(local.estatus, "ASISTIO")
                self.assertEqual(ajeno.estatus, "PENDIENTE")
                self.assertEqual(self.client.post(reverse(f"captura_asistencia_secuencial_{tipo}", args=[evento.pk]), {
                    "action": "asistio", "record_id": ajeno.pk,
                }).status_code, 404)
        # Visibility alone cannot authorize generation even in a block event.
        self.assertEqual(self.client.post(reverse("generar_registros_faena", args=[self.faena_ajena.pk])).status_code, 404)
        self.assertFalse(self.faena_ajena.registros.exists())

    def test_presidente_captura_secuencial_y_cambia_estado_en_ambos_eventos(self):
        self.client.force_login(self._presidente())
        for tipo, evento, local, ajeno in self._eventos_generales():
            with self.subTest(tipo=tipo):
                response = self.client.post(reverse(f"captura_asistencia_secuencial_{tipo}", args=[evento.pk]), {
                    "action": "asistio", "record_id": ajeno.pk,
                })
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["ok"])
                ajeno.refresh_from_db()
                self.assertEqual(ajeno.estatus, "ASISTIO")
                self.assertEqual(self.client.post(reverse("editar_estado_evento", args=[tipo, evento.pk]), {"estado": "REALIZADA"}).status_code, 302)
                evento.refresh_from_db()
                self.assertEqual(evento.estado, "REALIZADA")

    def test_presidente_con_lectura_global_no_opera_eventos_de_otro_comite(self):
        from django.contrib.auth.models import Permission
        presidente = self._presidente()
        presidente.user_permissions.set(Permission.objects.filter(content_type__app_label="operacion", codename__startswith="view_"))
        self.client.force_login(presidente)
        otro = Comite.objects.create(nombre="Otro comité para denegación")
        for tipo, evento, local, ajeno in self._eventos_generales():
            with self.subTest(tipo=tipo):
                evento.comite = otro
                evento.save()
                for ruta in (f"generar_registros_{tipo}", f"editar_{tipo}_operativa", f"captura_asistencia_{tipo}", f"captura_asistencia_secuencial_{tipo}"):
                    self.assertEqual(self.client.post(reverse(ruta, args=[evento.pk]), {
                        f"registro_{ajeno.pk}_estatus": "ASISTIO", "action": "asistio", "record_id": ajeno.pk,
                    }).status_code, 404)
                self.assertEqual(self.client.post(reverse("editar_estado_evento", args=[tipo, evento.pk]), {"estado": "CANCELADA"}).status_code, 404)
                ajeno.refresh_from_db()
                evento.refresh_from_db()
                self.assertEqual(ajeno.estatus, "PENDIENTE")
                self.assertEqual(evento.estado, "PROGRAMADA")

    def test_cargo_o_comite_inactivo_revoca_operacion_del_presidente(self):
        presidente = self._presidente()
        self.client.force_login(presidente)
        for campo in ("cargo", "comite"):
            objeto = self.cargo if campo == "cargo" else self.comite
            objeto.activo = False
            objeto.save(update_fields=["activo"])
            for tipo, evento, _, _ in self._eventos_generales():
                with self.subTest(inactivo=campo, tipo=tipo):
                    self.assertEqual(self.client.post(reverse(f"generar_registros_{tipo}", args=[evento.pk])).status_code, 404)
                    self.assertEqual(self.client.post(reverse(f"captura_asistencia_{tipo}", args=[evento.pk])).status_code, 404)
            objeto.activo = True
            objeto.save(update_fields=["activo"])

    def test_presidente_responsable_conserva_ambos_ambitos_al_crear(self):
        UsuarioApp.objects.create(user=self.responsable, comite=self.comite, rol=UsuarioApp.Roles.PRESIDENTE)
        self.client.force_login(self.responsable)
        for alcance, manzana, comite in (("GENERAL", "", self.comite.pk), ("MANZANA", self.manzana.pk, "")):
            with self.subTest(alcance=alcance):
                descripcion = f"Doble responsabilidad {alcance}"
                response = self.client.post(reverse("crear_faena_operativa"), {
                    "fecha": "2026-10-29", "descripcion": descripcion,
                    "alcance": alcance, "manzana": manzana, "comite": comite,
                    "motivo": "Trabajo comunitario", "estado": "PROGRAMADA", "notas": "",
                })
                self.assertEqual(response.status_code, 302)
                creada = Faena.objects.get(descripcion=descripcion)
                self.assertEqual(creada.alcance, alcance)
                self.assertEqual(creada.manzana_id, manzana or None)
                self.assertEqual(creada.comite_id, comite or None)

    def test_presidente_sin_permisos_globales_no_recibe_tesoreria_ni_roles(self):
        presidente = self._presidente()
        self.assertFalse(presidente.is_staff)
        self.assertFalse(presidente.has_perm("tesoreria.add_conceptotesoreria"))
        self.assertFalse(presidente.has_perm("comites.change_usuarioapp"))
        self.client.force_login(presidente)
        for tipo, evento, _, _ in self._eventos_generales():
            with self.subTest(tipo=tipo):
                response = self.client.post(reverse(f"eliminar_{tipo}_operativa", args=[evento.pk]))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(type(evento).objects.filter(pk=evento.pk).exists())

    def test_presidente_crea_y_edita_junta_sin_cambiar_comite_por_post(self):
        self.client.force_login(self._presidente())
        otro = Comite.objects.create(nombre="Comité no autorizado en formulario")
        datos = {
            "fecha": "2026-10-29", "tipo": Junta.Tipos.ORDINARIA, "lugar": "Salón",
            "tema": "Nueva junta presidencial", "alcance": "GENERAL", "manzana": "",
            "comite": otro.pk, "motivo": "", "estado": "PROGRAMADA", "notas": "",
        }
        url = reverse("crear_junta_operativa")
        self.assertEqual(self.client.post(url, datos).status_code, 200)
        self.assertFalse(Junta.objects.filter(tema=datos["tema"]).exists())
        datos["comite"] = self.comite.pk
        self.assertEqual(self.client.post(url, datos).status_code, 302)
        creada = Junta.objects.get(tema=datos["tema"])
        datos.update(comite=otro.pk, tema="Junta editada")
        self.assertEqual(self.client.post(reverse("editar_junta_operativa", args=[creada.pk]), datos).status_code, 302)
        creada.refresh_from_db()
        self.assertEqual(creada.tema, "Junta editada")
        self.assertEqual(creada.comite_id, self.comite.pk)

    def test_captura_con_permiso_global_de_cambio_explicito_sigue_disponible(self):
        from django.contrib.auth.models import Permission
        operador = get_user_model().objects.create_user(username="operador-global-explicito")
        operador.user_permissions.set(Permission.objects.filter(content_type__app_label="operacion", codename__in=[
            "view_faena", "view_junta", "change_registrofaena", "change_asistenciajunta",
        ]))
        self.client.force_login(operador)
        for tipo, evento, _, ajeno in self._eventos_generales():
            with self.subTest(tipo=tipo):
                self.assertEqual(self.client.post(reverse(f"captura_asistencia_{tipo}", args=[evento.pk]), {
                    f"registro_{ajeno.pk}_estatus": "ASISTIO",
                }).status_code, 302)
                ajeno.refresh_from_db()
                self.assertEqual(ajeno.estatus, "ASISTIO")
