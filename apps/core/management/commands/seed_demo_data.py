import random
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from faker import Faker

from apps.core.models import Ciudadano, Manzana


class Command(BaseCommand):
    help = "Genera ciudadanos realistas para pruebas del sistema Pueblo Digital."

    LABORES_SOCIALES = [
        "Limpieza de calles y espacios comunitarios",
        "Apoyo en faenas de mantenimiento",
        "Limpieza y conservación de áreas verdes",
        "Apoyo en actividades de la feria comunitaria",
        "Mantenimiento de caminos vecinales",
        "Apoyo en reuniones y eventos comunitarios",
        "Limpieza de la plaza principal",
        "Recolección de residuos en espacios públicos",
        "Apoyo en actividades de la clínica",
        "Mantenimiento del sistema comunitario de agua",
        "Organización de actividades culturales",
        "Apoyo en trabajos de la delegación",
    ]

    CALLES = [
        "Benito Juárez",
        "Miguel Hidalgo",
        "José María Morelos",
        "Vicente Guerrero",
        "Francisco I. Madero",
        "Emiliano Zapata",
        "Lázaro Cárdenas",
        "Niños Héroes",
        "Reforma",
        "Independencia",
        "20 de Noviembre",
        "5 de Mayo",
        "Constitución",
        "Insurgentes",
        "Allende",
        "Aldama",
    ]

    OBSERVACIONES = [
        "",
        "",
        "",
        "Información verificada durante el registro.",
        "Pendiente de actualizar documentación.",
        "Registro incorporado al padrón comunitario.",
        "Datos proporcionados directamente por el ciudadano.",
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--cantidad",
            type=int,
            default=350,
            help="Cantidad de ciudadanos que se intentarán crear. Predeterminado: 350.",
        )
        parser.add_argument(
            "--semilla",
            type=int,
            default=20260730,
            help="Semilla utilizada para generar datos reproducibles.",
        )

    def handle(self, *args, **options):
        cantidad = options["cantidad"]
        semilla = options["semilla"]

        if cantidad <= 0:
            raise CommandError("La cantidad debe ser mayor que cero.")

        random.seed(semilla)

        fake = Faker("es_MX")
        Faker.seed(semilla)

        with transaction.atomic():
            manzanas = self.obtener_manzanas()

            existentes = set(
                Ciudadano.objects.exclude(fecha_nacimiento=None).values_list(
                    "nombre",
                    "apellido_paterno",
                    "apellido_materno",
                    "fecha_nacimiento",
                )
            )

            contratos_existentes = set(
                Ciudadano.objects.exclude(numero_contrato__isnull=True)
                .exclude(numero_contrato="")
                .values_list("numero_contrato", flat=True)
            )

            ciudadanos = []
            identidades_generadas = set()
            contratos_generados = set()
            intentos = 0
            maximo_intentos = cantidad * 30

            while len(ciudadanos) < cantidad and intentos < maximo_intentos:
                intentos += 1

                motivo_alta = self.generar_motivo_alta()
                edad = self.generar_edad(motivo_alta)
                fecha_nacimiento = self.generar_fecha_nacimiento(edad)

                nombre = fake.first_name()
                apellido_paterno = fake.last_name()
                apellido_materno = (
                    fake.last_name()
                    if random.random() < 0.92
                    else ""
                )

                identidad = (
                    nombre,
                    apellido_paterno,
                    apellido_materno,
                    fecha_nacimiento,
                )

                if identidad in existentes or identidad in identidades_generadas:
                    continue

                manzana = random.choice(manzanas)

                numero_contrato = self.generar_numero_contrato(
                    manzana=manzana,
                    consecutivo=len(ciudadanos) + 1,
                    contratos_existentes=contratos_existentes,
                    contratos_generados=contratos_generados,
                )

                ciudadano = Ciudadano(
                    nombre=nombre,
                    apellido_paterno=apellido_paterno,
                    apellido_materno=apellido_materno,
                    edad=edad,
                    fecha_nacimiento=fecha_nacimiento,
                    numero_contrato=numero_contrato,
                    manzana=manzana,
                    labor_social=self.generar_labor_social(),
                    motivo_alta=motivo_alta,
                    direccion=self.generar_direccion(fake, manzana),
                    activo=random.random() < 0.88,
                    observaciones=random.choice(self.OBSERVACIONES),
                )

                ciudadanos.append(ciudadano)
                identidades_generadas.add(identidad)

                if numero_contrato:
                    contratos_generados.add(numero_contrato)

            if len(ciudadanos) < cantidad:
                raise CommandError(
                    f"Solo fue posible generar {len(ciudadanos)} "
                    f"de los {cantidad} ciudadanos solicitados."
                )

            Ciudadano.objects.bulk_create(ciudadanos, batch_size=100)

        activos = sum(ciudadano.activo for ciudadano in ciudadanos)
        inactivos = len(ciudadanos) - activos
        con_contrato = sum(
            bool(ciudadano.numero_contrato)
            for ciudadano in ciudadanos
        )
        sin_contrato = len(ciudadanos) - con_contrato

        self.stdout.write(
            self.style.SUCCESS(
                f"Se crearon {len(ciudadanos)} ciudadanos correctamente."
            )
        )
        self.stdout.write(f"Activos: {activos}")
        self.stdout.write(f"Inactivos: {inactivos}")
        self.stdout.write(f"Con contrato: {con_contrato}")
        self.stdout.write(f"Sin contrato: {sin_contrato}")
        self.stdout.write(f"Manzanas utilizadas: {len(manzanas)}")

    def obtener_manzanas(self):
        manzanas = list(Manzana.objects.filter(activa=True).order_by("nombre"))

        if manzanas:
            return manzanas

        self.stdout.write(
            self.style.WARNING(
                "No existen manzanas activas. Se crearán 12 manzanas de prueba."
            )
        )

        nuevas_manzanas = [
            Manzana(
                nombre=f"Manzana {numero:02d}",
                descripcion=f"Sector comunitario correspondiente a la manzana {numero}.",
                activa=True,
            )
            for numero in range(1, 13)
        ]

        Manzana.objects.bulk_create(nuevas_manzanas)

        return list(Manzana.objects.filter(activa=True).order_by("nombre"))

    def generar_motivo_alta(self):
        return random.choices(
            population=[
                Ciudadano.MotivosAlta.ESTUDIOS,
                Ciudadano.MotivosAlta.MAYORIA_EDAD,
                Ciudadano.MotivosAlta.INTEGRACION_COMUNIDAD,
            ],
            weights=[25, 55, 20],
            k=1,
        )[0]

    def generar_edad(self, motivo_alta):
        if motivo_alta == Ciudadano.MotivosAlta.ESTUDIOS:
            return random.randint(18, 29)

        if motivo_alta == Ciudadano.MotivosAlta.MAYORIA_EDAD:
            return random.choices(
                population=[
                    random.randint(18, 25),
                    random.randint(26, 45),
                    random.randint(46, 75),
                ],
                weights=[55, 30, 15],
                k=1,
            )[0]

        return random.randint(21, 78)

    def generar_fecha_nacimiento(self, edad):
        hoy = date.today()
        mes = random.randint(1, 12)

        dias_por_mes = {
            1: 31,
            2: 28,
            3: 31,
            4: 30,
            5: 31,
            6: 30,
            7: 31,
            8: 31,
            9: 30,
            10: 31,
            11: 30,
            12: 31,
        }

        dia = random.randint(1, dias_por_mes[mes])
        anio = hoy.year - edad

        if (mes, dia) > (hoy.month, hoy.day):
            anio -= 1

        return date(anio, mes, dia)

    def generar_numero_contrato(
        self,
        manzana,
        consecutivo,
        contratos_existentes,
        contratos_generados,
    ):
        # Aproximadamente 18 % de los ciudadanos no tendrá contrato.
        if random.random() < 0.18:
            return None

        intento = consecutivo

        while True:
            contrato = f"PD-M{manzana.pk:02d}-{intento:05d}"

            if (
                contrato not in contratos_existentes
                and contrato not in contratos_generados
            ):
                return contrato

            intento += 1

    def generar_labor_social(self):
        # Aproximadamente 35 % no tendrá labor social registrada.
        if random.random() < 0.35:
            return ""

        return random.choice(self.LABORES_SOCIALES)

    def generar_direccion(self, fake, manzana):
        calle = random.choice(self.CALLES)
        numero = random.randint(1, 250)

        if random.random() < 0.15:
            return f"Calle {calle} S/N, {manzana.nombre}"

        return f"Calle {calle} No. {numero}, {manzana.nombre}"