"""
Data migration (NON-destructive): turn the official primary colors into primary colors
WITHOUT touching existing rows or primary keys.

What it does
  - For each color in PRIMARY_COLORS: if it already exists in tbl_internal_color_code
    (same name AND same code), that row is reused: its pk stays the same and it is
    added to tbl_primary_color. If it doesn't exist, it is created (the pk just
    continues from the current sequence).
  - Removes "Natural" and "Light Blue" if they exist (REMOVE_COLORS).
  - NA (code AD): an existing "N/A" color is renamed to "NA" (same pk, code untouched).
    If there is neither, NA is created. It is a normal internal color, NOT a primary color.
  - Nothing else is changed: no truncate, no identity reset, no other rows touched.

Safety checks (it stops BEFORE changing anything and tells you why):
  - a color to remove is still referenced by another table
  - a primary color already exists with the same name but a DIFFERENT code
  - both "NA" and "N/A" exist (or several "N/A"), so it can't tell which one to keep
Runs once per database (Django records it), so it won't run twice.
Going backwards does nothing and does not restore removed rows.
"""
from django.db import migrations

# (color, code). Each becomes (or reuses) an internal color AND a primary color.
PRIMARY_COLORS = [
    ("BLUE", "B"), ("BLACK", "C"), ("BEIGE", "D"), ("GREEN", "G"), ("PEACH", "H"),
    ("BROWN", "I"), ("PINK", "K"), ("GOLD", "M"), ("ORANGE", "O"), ("BURGUNDY", "Q"),
    ("RED", "R"), ("SILVER", "S"), ("GRAY", "T"), ("VIOLET", "V"), ("WHITE", "W"),
    ("YELLOW", "Y"), ("MAGENTA", "Z"),
]
# Internal color only, NOT a primary color.
# An existing "N/A" is renamed to "NA"; if neither exists, NA is created with this code.
NA_COLOR = ("NA", "AD")
NA_OLD_NAME = "N/A"
# Removed if they exist (and are not used anywhere)
REMOVE_COLORS = ["Light Blue"]


def norm(text):
    """Compare names/codes ignoring case and stray spaces."""
    return (text or "").strip().upper()


def where_used(Internal, obj, db):
    """Names of tables that still point at this internal color (empty list = unused)."""
    used = []
    for rel in Internal._meta.related_objects:
        if rel.related_model._meta.model_name == "tbl_primary_color":
            continue
        if rel.related_model._default_manager.using(db).filter(**{rel.field.name: obj}).exists():
            used.append(rel.related_model.__name__)
    return used


def add_primary_colors(apps, schema_editor):
    db = schema_editor.connection.alias
    Internal = apps.get_model("main", "tbl_internal_color_code")
    Primary = apps.get_model("main", "tbl_primary_color")

    rows = list(Internal.objects.using(db).filter(is_deleted=False).order_by("pk"))
    by_name = {}
    for r in rows:
        by_name.setdefault(norm(r.color), []).append(r)

    # ---------- 1. CHECK FIRST (nothing is changed yet) ----------
    problems, to_remove, plan = [], [], []

    for name in REMOVE_COLORS:
        for obj in by_name.get(norm(name), []):
            used = where_used(Internal, obj, db)
            if used:
                problems.append(f"'{obj.color}' (id {obj.pk}) can't be removed, still used by: {', '.join(used)}")
            else:
                to_remove.append(obj)

    for name, code in PRIMARY_COLORS:
        same_name = by_name.get(norm(name), [])
        exact = [o for o in same_name if norm(o.code) == norm(code)]
        if exact:
            plan.append((name, code, exact[0]))     # reuse the existing row (lowest pk)
        elif same_name:
            problems.append(f"'{name}' already exists (id {same_name[0].pk}) with code "
                            f"'{same_name[0].code}', but the primary list says '{code}'")
        else:
            plan.append((name, code, None))         # will be created

    # NA: rename the existing "N/A" (keeps its pk), or create NA if there is neither
    old_na = by_name.get(norm(NA_OLD_NAME), [])
    new_na = by_name.get(norm(NA_COLOR[0]), [])
    rename_na = None
    if old_na and new_na:
        problems.append(f"Both '{new_na[0].color}' (id {new_na[0].pk}) and '{old_na[0].color}' "
                        f"(id {old_na[0].pk}) exist. Keep one of them first.")
    elif len(old_na) > 1:
        problems.append(f"'{NA_OLD_NAME}' exists {len(old_na)} times (ids "
                        f"{', '.join(str(o.pk) for o in old_na)}). Keep one of them first.")
    elif old_na:
        rename_na = old_na[0]

    if problems:
        raise RuntimeError("Nothing was changed. Please resolve these first:\n  " + "\n  ".join(problems))

    # ---------- 2. APPLY ----------
    for obj in to_remove:
        obj.delete()

    reused = created = 0
    for name, code, obj in plan:
        if obj is None:
            obj = Internal.objects.using(db).create(color=name, code=code, status="approved")
            created += 1
        else:
            reused += 1
            if obj.status != "approved":
                obj.status = "approved"
                obj.save(update_fields=["status"])

        primary, _ = Primary.objects.using(db).get_or_create(in_code=obj)
        if obj.primary_color_id != primary.pk:
            obj.primary_color = primary             # a primary color is listed under itself
            obj.save(update_fields=["primary_color"])

    if rename_na is not None:
        rename_na.color = NA_COLOR[0]               # only the name changes, pk and code stay
        rename_na.save(update_fields=["color"])
        na_note = f"'{NA_OLD_NAME}' (id {rename_na.pk}) renamed to '{NA_COLOR[0]}'"
    elif not new_na:
        Internal.objects.using(db).create(color=NA_COLOR[0], code=NA_COLOR[1], status="approved")
        na_note = f"'{NA_COLOR[0]}' created"
    else:
        na_note = f"'{NA_COLOR[0]}' already exists"

    print(f"\n  primary colors: {reused} existing rows reused, {created} created, "
          f"{len(to_remove)} removed ({', '.join(o.color for o in to_remove) or 'none'}); {na_note}")


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0069_tbl_primary_color_and_more"),
    ]

    operations = [
        migrations.RunPython(add_primary_colors, migrations.RunPython.noop),
    ]