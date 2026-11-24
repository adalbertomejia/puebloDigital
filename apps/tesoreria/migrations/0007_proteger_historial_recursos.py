"""Protect the new custody evidence, including writes bypassing Model.save."""
from django.db import migrations

FONDO = ["clave_apertura", "nombre", "categoria", "comite_id", "manzana_id", "fecha_apertura", "inicial_efectivo", "inicial_transferencia", "evidencia_apertura", "creado_por_id", "created_at"]
CORTE = ["id", "fondo_id", "desde", "hasta", "preparado_por_id", "contado", "esperado", "diferencia", "aclaracion", "evidencia_conteo", "manifiesto", "huella", "clave_operacion", "created_at"]
ABONO = ["monto", "fecha", "obligacion_id", "referencia", "notas", "creado_por_id", "created_at"]


def instalar(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor not in ("sqlite", "postgresql"):
        raise RuntimeError("La protección de recursos requiere PostgreSQL o SQLite.")
    q=schema_editor.quote_name
    tablas={n:apps.get_model("tesoreria",n)._meta.db_table for n in ("FondoRecurso","MovimientoRecurso","CorteRecurso","EventoCorteRecurso","Abono")}
    def cambios(campos):
        operador = "IS NOT" if vendor == "sqlite" else "IS DISTINCT FROM"
        return " OR ".join(f"NEW.{q(c)} {operador} OLD.{q(c)}" for c in campos)
    reglas=[
        ("recurso_fondo_delete",tablas["FondoRecurso"],"DELETE","TRUE"),
        ("recurso_movimiento_update",tablas["MovimientoRecurso"],"UPDATE","TRUE"),
        ("recurso_movimiento_delete",tablas["MovimientoRecurso"],"DELETE","TRUE"),
        ("recurso_evento_update",tablas["EventoCorteRecurso"],"UPDATE","TRUE"),
        ("recurso_evento_delete",tablas["EventoCorteRecurso"],"DELETE","TRUE"),
        ("recurso_corte_delete",tablas["CorteRecurso"],"DELETE","TRUE"),
        ("recurso_fondo_apertura",tablas["FondoRecurso"],"UPDATE",cambios(FONDO)),
        ("recurso_corte_fijo",tablas["CorteRecurso"],"UPDATE","OLD.estado <> 'EN_REVISION' OR NEW.estado NOT IN ('DEVUELTO','CONFIRMADO') OR NEW.revisado_por_id IS NULL OR NEW.revisado_en IS NULL OR ("+cambios(CORTE)+")"),
        ("recurso_abono_fuente",tablas["Abono"],"UPDATE",f"EXISTS (SELECT 1 FROM {q(tablas['MovimientoRecurso'])} m WHERE m.abono_id = OLD.id) AND ("+cambios(ABONO)+")"),
    ]
    for nombre,tabla,evento,condicion in reglas:
        if vendor=="sqlite":
            schema_editor.execute(f"CREATE TRIGGER {q(nombre)} BEFORE {evento} ON {q(tabla)} WHEN {condicion} BEGIN SELECT RAISE(ABORT, 'Historial de recursos protegido'); END")
        else:
            funcion=q(nombre+"_fn")
            schema_editor.execute(f"CREATE FUNCTION {funcion}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF {condicion} THEN RAISE EXCEPTION 'Historial de recursos protegido' USING ERRCODE = '23514'; END IF; RETURN NEW; END; $$")
            schema_editor.execute(f"CREATE TRIGGER {q(nombre)} BEFORE {evento} ON {q(tabla)} FOR EACH ROW EXECUTE FUNCTION {funcion}()")


def retirar(apps, schema_editor):
    vendor=schema_editor.connection.vendor
    tablas={
        "recurso_fondo_delete":"FondoRecurso",
        "recurso_movimiento_update":"MovimientoRecurso", "recurso_movimiento_delete":"MovimientoRecurso",
        "recurso_evento_update":"EventoCorteRecurso", "recurso_evento_delete":"EventoCorteRecurso",
        "recurso_corte_delete":"CorteRecurso", "recurso_fondo_apertura":"FondoRecurso",
        "recurso_corte_fijo":"CorteRecurso", "recurso_abono_fuente":"Abono",
    }
    q=schema_editor.quote_name
    for nombre,modelo in tablas.items():
        if vendor=="sqlite":
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {q(nombre)}")
        elif vendor=="postgresql":
            tabla=apps.get_model("tesoreria",modelo)._meta.db_table
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {q(nombre)} ON {q(tabla)}")
            schema_editor.execute(f"DROP FUNCTION IF EXISTS {q(nombre+'_fn')}()")


class Migration(migrations.Migration):
    dependencies=[("tesoreria","0006_corterecurso_eventocorterecurso_fondorecurso_and_more")]
    operations=[migrations.RunPython(instalar,retirar)]
