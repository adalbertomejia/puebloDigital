from django.core.management.base import BaseCommand

from faker import Faker

import random

from apps.core.models import Ciudadano


fake = Faker('es_MX')


class Command(BaseCommand):

    help = 'Genera ciudadanos demo'

    def handle(self, *args, **kwargs):

        ciudadanos = []

        for _ in range(50):

            ciudadano = Ciudadano(
                nombre=fake.first_name(),
                apellido_paterno=fake.last_name(),
                apellido_materno=fake.last_name(),
                edad=random.randint(18, 90),
                activo=True
            )

            ciudadanos.append(ciudadano)

        Ciudadano.objects.bulk_create(ciudadanos)

        self.stdout.write(
            self.style.SUCCESS(
                '50 ciudadanos demo creados correctamente'
            )
        )