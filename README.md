# Pueblo Digital MVP v3 (Admin-first)

## Enfoque correcto del MVP
Esta versión corrige el error de la v2:
- **No hay CRUD público de ciudadanos**
- La operación principal ocurre en **Django Admin**
- El acceso se controla con **auth de Django**
- La arquitectura está preparada para **roles por comité**

## Apps incluidas
- `core` → Ciudadano y base común
- `comites` → Comite, UsuarioApp (roles)
- `agua` → Toma
- `tesoreria` → Pago, Cooperacion
- `operacion` → Junta, AsistenciaJunta, Faena, RegistroFaena, Actividad, ActividadArchivo

## Instalación
```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate

pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Migraciones
Las migraciones están versionadas. Revisa el plan y el historial de la instalación antes de aplicar `migrate`; no las borres ni regeneres y no uses `--fake` para resolver discrepancias.

## Próximo paso recomendado
Implementar en v4:
- restricciones reales por comité en admin (`get_queryset`, `save_model`, `formfield_for_foreignkey`)
- dashboards / vistas de consulta (no CRUD)
- perfil ciudadano consolidado
# puebloDigital

## Ciclo ciudadano de Dahiedhi
La atención diaria se realiza desde `/ciudadanos/`. Consulta [recorridos, permisos, pruebas y límites](docs/ciclo-ciudadano-dahiedhi.md).
