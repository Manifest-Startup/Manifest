"""Regression test: every top-level Query/Mutation field MUST be
declared as either PUBLIC or permission-gated.

If a new resolver is added without an entry in
``PUBLIC_FIELDS`` or ``FIELD_PERMISSIONS`` this test fails — that is
the "default-deny by RBAC, not just by auth" guarantee the security
hardening task requires.
"""
from app.graphql.schema import schema, _DefaultDenyAuthExtension


def test_every_root_field_has_explicit_authz_declaration():
    mapped = set(_DefaultDenyAuthExtension.PUBLIC_FIELDS) | set(
        _DefaultDenyAuthExtension.FIELD_PERMISSIONS
    )
    gql = schema._schema
    missing = []
    for type_name in ("Query", "Mutation"):
        gtype = gql.type_map.get(type_name)
        if gtype is None:
            continue
        for field_name in gtype.fields:
            if field_name.startswith("__"):
                continue
            if field_name not in mapped:
                missing.append(f"{type_name}.{field_name}")
    assert not missing, (
        "Every top-level GraphQL field must be in PUBLIC_FIELDS or "
        "FIELD_PERMISSIONS. Missing declarations:\n  " + "\n  ".join(sorted(missing))
    )
