import unicodedata
from difflib import SequenceMatcher
from .models import Ciudadano


def normalizar_nombre(value):
    return " ".join(
        "".join(
            c
            for c in unicodedata.normalize("NFKD", value.casefold())
            if not unicodedata.combining(c)
        ).split()
    )


def posibles_duplicados(data, exclude_pk=None):
    nombre = normalizar_nombre(
        " ".join(
            data.get(k, "") for k in ("nombre", "apellido_paterno", "apellido_materno")
        )
    )
    matches = []
    for ciudadano in Ciudadano.objects.exclude(pk=exclude_pk).iterator():
        candidate = normalizar_nombre(ciudadano.nombre_completo)
        if (
            candidate == nombre
            or SequenceMatcher(None, candidate, nombre).ratio() >= 0.88
        ):
            matches.append(ciudadano)
    return matches


def relaciones_ciudadano(ciudadano):
    """Include SET_NULL relations too; deletion must never silently orphan access/history."""
    return [
        (
            rel.related_model._meta.verbose_name_plural,
            getattr(ciudadano, rel.get_accessor_name()).count(),
        )
        for rel in ciudadano._meta.related_objects
        if rel.one_to_many
    ]


def puede_eliminar_ciudadano(usuario):
    from apps.comites.models import UsuarioApp

    secretaria = UsuarioApp.objects.filter(
        user=usuario,
        activo=True,
        comite__activo=True,
        comite__tipo="DELEGACION",
        rol="SECRETARIO",
    ).exists()
    return usuario.is_superuser or (
        (usuario.is_staff or secretaria)
        and usuario.has_perm("core.view_ciudadano")
        and usuario.has_perm("core.delete_ciudadano")
    )


def retorno_ciudadano(request):
    from urllib.parse import urlsplit
    from django.urls import reverse

    value = request.POST.get("return_to", request.GET.get("return_to", ""))
    try:
        parsed = urlsplit(value)
    except ValueError:
        return reverse("padron_ciudadanos")
    allowed = [
        reverse(name)
        for name in (
            "padron_ciudadanos",
            "control_asistencias",
            "tesoreria_operativa",
            "resumen_aportaciones",
        )
    ]
    return (
        value
        if not parsed.scheme and not parsed.netloc and parsed.path in allowed
        else reverse("padron_ciudadanos")
    )


def url_expediente(pk, return_to):
    from urllib.parse import urlencode
    from django.urls import reverse

    base = reverse("perfil_ciudadano", args=[pk])
    return (
        base
        if return_to == reverse("padron_ciudadanos")
        else base + "?" + urlencode({"return_to": return_to})
    )


def token_operacion(request, key):
    import secrets

    token = secrets.token_urlsafe(24)
    tokens = request.session.get("operaciones_padron", {})
    tokens[token] = key
    request.session["operaciones_padron"] = dict(list(tokens.items())[-30:])
    return token


def consumir_token(request, key):
    from django.contrib import messages

    tokens = request.session.get("operaciones_padron", {})
    token = request.POST.get("operation_token", "")
    if tokens.get(token) != key:
        messages.warning(
            request,
            "La operación ya fue enviada o el formulario caducó. Revisa el expediente antes de repetirla.",
        )
        return False
    del tokens[token]
    request.session["operaciones_padron"] = tokens
    return True
