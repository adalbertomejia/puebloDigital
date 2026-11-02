# Pueblo Digital · Dahiedhi

Aplicación Django para padrón ciudadano, asistencias, agua y tesorería. El ciclo del ciudadano se atiende desde `/ciudadanos/`, con autenticación y permisos por función. Los comités y responsables conservan sus alcances autorizados.

## Desarrollo

Instala `requirements.txt` en un entorno virtual propio. No versiones entornos, archivos `.env`, bases locales ni respaldos.

```bash
pip install -r requirements.txt
python manage.py showmigrations --plan
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Las migraciones forman parte del repositorio. Revisa el historial real de la instalación antes de aplicar `migrate`; no las borres ni regeneres y no uses `--fake` para resolver discrepancias.

La configuración recibida es de desarrollo. Antes de desplegar, verifica clave, DEBUG, hosts y conexión a la base de Dahiedhi. Dahiedhi y Santa Mónica deben mantener configuración y bases independientes.

Consulta [recorridos, permisos, pruebas y límites del ciclo ciudadano](docs/ciclo-ciudadano-dahiedhi.md).
