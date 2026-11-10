"""Shared, read-only derivation of the user's current access responsibilities."""

from dataclasses import dataclass

from django.db.models import F


@dataclass(frozen=True)
class ResponsabilidadActiva:
    tipo: str
    rol: str
    etiqueta_rol: str
    manzana: object = None
    comite: object = None

    @property
    def funciones(self):
        """Describe this assignment, without granting additional permissions."""
        finanzas = (
            "Consultar finanzas, actividad y exportar reportes de este comité",
            "Crear y editar conceptos de este comité",
            "Generar obligaciones y registrar abonos de este comité",
            "Eliminar conceptos de este comité con confirmación",
        )
        if self.tipo == "GLOBAL":
            return (
                "Administrar cuentas, vínculos y cargos",
                "Gestionar eventos y finanzas de todos los comités",
            )
        if self.tipo == "MANZANA":
            return (
                "Consultar el padrón de mi manzana",
                "Crear y gestionar eventos de mi manzana",
                "Capturar y exportar participantes de mi manzana en eventos generales",
            )
        if self.tipo == "COMITE" and self.rol in ("PRESIDENTE", "TESORERO"):
            return ("Crear y gestionar eventos generales de este comité", "Capturar asistencias de este comité") + finanzas
        if self.tipo == "COMITE" and self.rol == "LECTURA":
            return (
                "Consultar asistencias y aportaciones de este comité",
                "Imprimir consultas y recibos autorizados",
                "Compartir enlaces de consulta que requieren una cuenta autorizada",
                "Sin captura, edición, generación de obligaciones ni eliminación",
            )
        return ()


def responsabilidades_activas(usuario):
    """Return current block and committee assignments for an authenticated user.

    Block responsibility is derived from the user's one-to-one PerfilAcceso and
    the citizen currently assigned to their own active block. Committee roles
    remain sourced from active UsuarioApp rows and active committees.
    """
    if not getattr(usuario, "is_authenticated", False) or not getattr(
        usuario, "is_active", False
    ):
        return []

    from apps.comites.models import Comite, PerfilAcceso, UsuarioApp

    responsabilidades = []

    if usuario.is_superuser:
        responsabilidades.append(
            ResponsabilidadActiva(
                tipo="GLOBAL",
                rol="ADMINISTRADOR",
                etiqueta_rol="Administrador general",
            )
        )

    # Invalid legacy combinations fail closed until an administrator reconciles them.
    from apps.core.models import Manzana
    vinculo = PerfilAcceso.objects.select_related('ciudadano').filter(user_id=usuario.pk).first()
    if vinculo is None or not vinculo.ciudadano.activo:
        return responsabilidades
    cargos_vigentes = UsuarioApp.objects.filter(user_id=usuario.pk, activo=True)
    if cargos_vigentes.count() > 1 or cargos_vigentes.exclude(ciudadano_id=vinculo.ciudadano_id).exists():
        return responsabilidades
    territorios = Manzana.objects.filter(activa=True, responsable_id=vinculo.ciudadano_id)
    if territorios.count() > 1 or (territorios.exists() and cargos_vigentes.exists()):
        return responsabilidades

    perfil = (
        PerfilAcceso.objects.select_related("ciudadano__manzana")
        .filter(
            user_id=usuario.pk,
            ciudadano__activo=True,
            ciudadano__manzana__isnull=False,
            ciudadano__manzana__activa=True,
            ciudadano__manzana__responsable_id=F("ciudadano_id"),
        )
        .first()
    )
    if perfil:
        responsabilidades.append(
            ResponsabilidadActiva(
                tipo="MANZANA",
                rol="RESPONSABLE_MANZANA",
                etiqueta_rol="Responsable de manzana",
                manzana=perfil.ciudadano.manzana,
            )
        )

    cargos = (
        UsuarioApp.objects.select_related("comite")
        .filter(user_id=usuario.pk, activo=True, comite__activo=True)
        .order_by("comite__nombre", "rol")
    )
    responsabilidades.extend(
        ResponsabilidadActiva(
            tipo="COMITE",
            rol=cargo.rol,
            etiqueta_rol=cargo.get_rol_display(),
            comite=cargo.comite,
        )
        for cargo in cargos
    )

    return responsabilidades


def permiso_global_de_modelo(usuario, permiso):
    """Committee accounts use contextual roles, never a global permission bypass."""
    if not getattr(usuario, 'is_authenticated', False) or not getattr(usuario, 'is_active', False):
        return False
    return usuario.is_superuser or (
        usuario.has_perm(permiso) and not usuario.perfiles_app.exists()
    )
