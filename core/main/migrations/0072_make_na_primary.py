"""
Data migration: make NA (code AD) a primary color too.
 
HOW TO USE
  1. python manage.py makemigrations main --empty -n make_na_primary
  2. Open the new empty file, KEEP its `dependencies = [...]` line, and paste everything
     else from this file over the rest.
  3. Back up the database, then:  python manage.py migrate
 
What it does (NON-destructive, pk of NA never changes)
  - Finds the existing "NA" color and adds it to tbl_primary_color; it is then listed under
    itself (primary_color_id = its own primary id), exactly like the other primary colors.
  - If there is no NA at all, it is created (code AD) and made primary.
 
Safety checks (it stops BEFORE changing anything and tells you why):
  - "NA" exists more than once
  - "NA" has a code other than AD
  - another primary color already uses the code AD
Safe to run twice. Going backwards does nothing.
"""
from django.db import migrations
 
NA_NAME = "NA"
NA_CODE = "AD"
 
 
def norm(text):
    """Compare names/codes ignoring case and stray spaces."""
    return (text or "").strip().upper()
 
 
def make_na_primary(apps, schema_editor):
    db = schema_editor.connection.alias
    Internal = apps.get_model("main", "tbl_internal_color_code")
    Primary = apps.get_model("main", "tbl_primary_color")
 
    na_rows = [r for r in Internal.objects.using(db).filter(is_deleted=False).order_by("pk")
               if norm(r.color) == NA_NAME]
    na = na_rows[0] if len(na_rows) == 1 else None
 
    # ---------- 1. CHECK FIRST (nothing is changed yet) ----------
    problems = []
    if len(na_rows) > 1:
        problems.append(f"'{NA_NAME}' exists {len(na_rows)} times (ids "
                        f"{', '.join(str(r.pk) for r in na_rows)}). Keep one of them first.")
    if na is not None and norm(na.code) != NA_CODE:
        problems.append(f"'{NA_NAME}' (id {na.pk}) has code '{na.code}', not '{NA_CODE}'.")
 
    for p in Primary.objects.using(db).select_related("in_code"):
        other = p.in_code
        if not other.is_deleted and norm(other.code) == NA_CODE and (na is None or other.pk != na.pk):
            problems.append(f"Primary color '{other.color}' (id {other.pk}) already uses code '{NA_CODE}'.")
 
    if problems:
        raise RuntimeError("Nothing was changed. Please resolve these first:\n  " + "\n  ".join(problems))
 
    # ---------- 2. APPLY ----------
    created = False
    if na is None:
        na = Internal.objects.using(db).create(color=NA_NAME, code=NA_CODE, status="approved")
        created = True
    elif na.status != "approved":
        na.status = "approved"
        na.save(update_fields=["status"])
 
    primary, _ = Primary.objects.using(db).get_or_create(in_code=na)
    if na.primary_color_id != primary.pk:
        na.primary_color = primary                  # a primary color is listed under itself
        na.save(update_fields=["primary_color"])
 
    print(f"\n  NA (id {na.pk}) is now primary color id {primary.pk}" + (" (NA was created)" if created else ""))
 
class Migration(migrations.Migration):

    dependencies = [
        ('main', '0071_tbl_dc_extruder_formula_internal_color_and_more'),
    ]

    operations = [
        migrations.RunPython(make_na_primary, migrations.RunPython.noop),
    ]
