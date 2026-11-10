"""Frozen, read-only validation shared by the migration and preflight command."""

from collections import defaultdict


def evaluar(cargos, perfiles, manzanas):
    identidades = {p["user_id"]: p["ciudadano_id"] for p in perfiles}
    por_cuenta, por_persona, por_territorio = (
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
    )
    problemas, completar = [], []
    for cargo in cargos:
        persona = identidades.get(cargo["user_id"])
        if persona is None:
            problemas.append(
                {
                    "codigo": "cuenta_sin_vinculo",
                    "cargo": cargo["id"],
                    "cuenta": cargo["user_id"],
                }
            )
        elif cargo["ciudadano_id"] not in (None, persona):
            problemas.append(
                {
                    "codigo": "identidad_no_coincide",
                    "cargo": cargo["id"],
                    "cuenta": cargo["user_id"],
                }
            )
        elif cargo["ciudadano_id"] is None:
            completar.append((cargo["id"], persona))
        por_cuenta[cargo["user_id"]].append(cargo["id"])
        if persona is not None:
            por_persona[persona].append(cargo["id"])
    for manzana in manzanas:
        por_territorio[manzana["responsable_id"]].append(manzana["id"])
    for cuenta, ids in por_cuenta.items():
        if len(ids) > 1:
            problemas.append(
                {"codigo": "varios_cargos_cuenta", "cuenta": cuenta, "cargos": ids}
            )
    for persona, ids in por_persona.items():
        if len(ids) > 1:
            problemas.append(
                {
                    "codigo": "varios_cargos_ciudadano",
                    "ciudadano": persona,
                    "cargos": ids,
                }
            )
        if por_territorio[persona]:
            problemas.append(
                {
                    "codigo": "comite_y_manzana",
                    "ciudadano": persona,
                    "cargos": ids,
                    "manzanas": por_territorio[persona],
                }
            )
    for persona, ids in por_territorio.items():
        if len(ids) > 1:
            problemas.append(
                {"codigo": "varias_manzanas", "ciudadano": persona, "manzanas": ids}
            )
    return {"problemas": problemas, "vinculos_a_completar": completar}
