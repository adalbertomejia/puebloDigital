import json
from django.core.management.base import BaseCommand, CommandError
from apps.comites.models import PerfilAcceso, UsuarioApp
from apps.core.models import Manzana
from apps.comites.migrations._auditoria_cargos_v1 import evaluar


class Command(BaseCommand):
    help = "Revisa identidad y cargo único sin modificar asignaciones."

    def handle(self, *args, **options):
        informe = evaluar(
            list(
                UsuarioApp.objects.filter(activo=True).values(
                    "id", "user_id", "ciudadano_id"
                )
            ),
            list(PerfilAcceso.objects.values("user_id", "ciudadano_id")),
            list(
                Manzana.objects.filter(activa=True, responsable__isnull=False).values(
                    "id", "responsable_id"
                )
            ),
        )
        self.stdout.write(json.dumps(informe, ensure_ascii=False, indent=2))
        if informe["problemas"]:
            raise CommandError(
                "Hay asignaciones por revisar. No se modificó ningún registro."
            )
