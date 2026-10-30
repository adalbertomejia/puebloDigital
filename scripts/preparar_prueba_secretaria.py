#!/usr/bin/env python3
"""Rebuild an isolated SQLite test database from data, never fake migrations.

Run from a dedicated virtual environment after installing requirements.txt.
The source is opened read-only, exports remain outside Git, and no server is
started. Every exported object's fields and relationships are compared before
printing the command to start the test instance.
"""
import argparse
from collections import Counter
from contextlib import closing
import json
import os
from pathlib import Path
import secrets
import shlex
import sqlite3
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
EXCLUDED = ('contenttypes', 'auth.permission', 'sessions', 'secretaria')


def command(settings, *args, env):
    subprocess.run([sys.executable, str(REPO / 'manage.py'), *args,
                    '--settings=' + settings, '--no-color'], cwd=REPO,
                   env=env, check=True)


def canonical_objects(filename, models):
    result = {}
    for obj in json.loads(filename.read_text(encoding='utf-8')):
        label = obj['model']
        m2m = {f.name for f in models.get_model(label)._meta.many_to_many}
        fields = obj['fields']
        for name in m2m:
            if name in fields:
                fields[name] = sorted(fields[name], key=lambda v: json.dumps(v, sort_keys=True))
        key = (label, str(obj['pk']))
        if key in result:
            raise RuntimeError('La exportación contiene identificadores repetidos: ' + label)
        result[key] = fields
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origen', required=True, type=Path, help='Copia SQLite que se abrirá en modo de solo lectura.')
    parser.add_argument('--directorio', type=Path, default=REPO.parent, help='Carpeta donde crear un directorio privado NUEVO, fuera del repositorio.')
    args = parser.parse_args()
    source = args.origen.expanduser().resolve()
    parent = args.directorio.expanduser().resolve()
    if not source.is_file():
        parser.error('No existe la copia SQLite indicada.')
    if parent == REPO or REPO in parent.parents:
        parser.error('El directorio de datos debe estar fuera del repositorio.')
    if not parent.is_dir():
        parser.error('No existe el directorio de destino.')
    try:
        import django  # noqa: F401
    except ImportError:
        parser.error('Activa un entorno virtual separado e instala requirements.txt primero.')

    source_uri = source.as_uri() + '?mode=ro'
    with closing(sqlite3.connect(source_uri, uri=True)) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'core_ciudadano' not in tables:
            parser.error('La base no contiene el padrón de Pueblo Digital.')
        # Do not silently omit a previous run's actual Secretariat records.
        for table in ('secretaria_solicitud', 'secretaria_seguimiento', 'secretaria_adjunto', 'secretaria_tiposolicitud'):
            if table in tables and db.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone():
                parser.error('La copia ya contiene datos de Secretaría. Esta herramienta es para su primera preparación; no los omitirá.')
        integrity = db.execute('PRAGMA quick_check').fetchall()
        if integrity != [('ok',)]:
            parser.error('SQLite reporta problemas de integridad; se necesita revisar la copia antes de importar.')

    folder = Path(tempfile.mkdtemp(prefix='secretaria-prueba-', dir=parent))
    folder.chmod(0o700)
    target = folder / 'secretaria.sqlite3'
    export = folder / 'datos-origen.json'
    check = folder / 'datos-verificados.json'
    secret = secrets.token_hex(32)
    common = (
        'from config.settings import *\n'
        f'SECRET_KEY = {secret!r}\n'
        'DEBUG = True\n'
        "ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']\n"
        "SESSION_COOKIE_NAME = 'secretaria_prueba_sessionid'\n"
        "CSRF_COOKIE_NAME = 'secretaria_prueba_csrftoken'\n"
        f'SOLICITUDES_PRIVATE_ROOT = {str(folder / "documentos")!r}\n'
    )
    source_settings = folder / '_secretaria_origen.py'
    test_settings = folder / '_secretaria_prueba.py'
    source_settings.write_text(common + f"DATABASES = {{'default': {{'ENGINE': 'django.db.backends.sqlite3', 'NAME': {source_uri!r}, 'OPTIONS': {{'uri': True}}}}}}\n", encoding='utf-8')
    test_settings.write_text(common + f"DATABASES = {{'default': {{'ENGINE': 'django.db.backends.sqlite3', 'NAME': {str(target)!r}}}}}\n", encoding='utf-8')
    source_settings.chmod(0o600); test_settings.chmod(0o600)
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join([str(folder), str(REPO), env.get('PYTHONPATH', '')])
    exclusion_args = [arg for label in EXCLUDED for arg in ('--exclude', label)]
    print('ORIGEN (solo lectura):', source, flush=True)
    print('CARPETA PRIVADA DE PRUEBAS:', folder, flush=True)
    try:
        command('_secretaria_origen', 'dumpdata', '--all', '--natural-foreign',
                *exclusion_args, '--output', str(export), env=env)
        export.chmod(0o600)
        command('_secretaria_prueba', 'migrate', '--noinput', env=env)
        target.chmod(0o600)
        command('_secretaria_prueba', 'loaddata', str(export), env=env)
        command('_secretaria_prueba', 'dumpdata', '--all', '--natural-foreign',
                *exclusion_args, '--output', str(check), env=env)
        check.chmod(0o600)
        os.environ['DJANGO_SETTINGS_MODULE'] = '_secretaria_prueba'
        sys.path[:0] = [str(folder), str(REPO)]
        django.setup()
        from django.apps import apps
        before = canonical_objects(export, apps)
        after = canonical_objects(check, apps)
        if before != after:
            missing = len(set(before) - set(after))
            extra = len(set(after) - set(before))
            changed = sum(before[k] != after[k] for k in set(before) & set(after))
            raise RuntimeError(f'La comparación no coincide: faltantes={missing}, adicionales={extra}, modificados={changed}. No se habilita la prueba.')
        with closing(sqlite3.connect(target.as_uri() + '?mode=ro', uri=True)) as db:
            if db.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('La base nueva contiene relaciones inválidas.')
            if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise RuntimeError('Falló la comprobación SQLite de la base nueva.')
        print('\nVERIFICACIÓN CORRECTA: campos, identificadores y relaciones exportados coinciden.')
        for label, count in sorted(Counter(k[0] for k in before).items()):
            print(f'  {label}: {count}')
        mapped_tables = {m._meta.db_table for m in apps.get_models(include_auto_created=True)}
        unknown = sorted(t for t in tables - mapped_tables - {'django_migrations'} if not t.startswith('sqlite_'))
        if unknown:
            print('Tablas ajenas a los modelos actuales, no exportadas:', ', '.join(unknown))
        print('Sesiones no copiadas. Permisos y tipos de contenido se regeneraron mediante las migraciones; sus relaciones se importaron por claves naturales.')
        print('Los archivos binarios antiguos no se copiaron; sus referencias se conservan. Los adjuntos nuevos de Secretaría usan un directorio separado.')
        print('\nPara iniciar SOLO esta base de pruebas:')
        launch = [sys.executable, str(REPO / 'manage.py'), 'runserver', '127.0.0.1:8010', '--settings=_secretaria_prueba']
        print('PYTHONPATH=' + shlex.quote(str(folder) + os.pathsep + str(REPO)) + ' ' + shlex.join(launch))
        print('\nNo publiques los JSON, las bases ni los archivos de configuración generados.')
    except (subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        print('\nNO SE COMPLETÓ LA PREPARACIÓN:', exc, file=sys.stderr)
        print('El origen no se modificó. Los resultados parciales quedan en:', folder, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
