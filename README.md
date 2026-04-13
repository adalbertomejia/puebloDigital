# Pueblo Digital MVP v3 (Admin-first + vistas operativas)

## Enfoque del MVP
- **No hay CRUD público de ciudadanos**
- La operación principal ocurre en **Django Admin**
- El acceso se controla con **auth de Django**
- El modelo E/R base está creado y se complementa con **vistas personalizadas por rol** para tareas diarias

## Apps incluidas
- `core` → Ciudadano y base común
- `comites` → Comite, UsuarioApp (roles)
- `agua` → Toma + vista operativa de tomas (`/agua/tomas/`)
- `tesoreria` → Pago, Cooperacion
- `operacion` → Junta, AsistenciaJunta, Faena, RegistroFaena, Actividad, ActividadArchivo

## Instalación
```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Uso recomendado
1. Captura/edición completa de datos desde `/admin/`.
2. Trabajo operativo diario por rol desde vistas específicas:
   - Agua: `/agua/tomas/`
3. Escalar nuevas pantallas según necesidad de cada comité (delegado, secretaría, tesorería, etc.).

## Nota
No se incluyen migraciones generadas a propósito.
Genera las migraciones en tu entorno local para evitar inconsistencias.
