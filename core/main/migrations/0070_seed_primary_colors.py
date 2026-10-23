"""
Data migration: wipe tbl_internal_color_code, restart its IDs at 1, and load the primary colors.
 
HOW TO USE
  1. Add the new models/field, then:  python manage.py makemigrations main
     (this creates the schema migration: tbl_primary_color + primary_color_id)
  2. Create this one:                 python manage.py makemigrations main --empty -n seed_primary_colors
  3. Open the new empty file Django created, KEEP its `dependencies = [...]` line,
     and paste everything else from this file over the rest.
  4. BACK UP THE DATABASE, then:      python manage.py migrate
 
Runs once per database (Django records it), so it will not wipe the colors again later.
Going backwards does NOT restore the deleted colors.
"""
from django.db import migrations
 
# (color, code). Each of these becomes an internal color AND a primary color.
PRIMARY_COLORS = [
    ("BLUE", "B"), ("BLACK", "C"), ("BEIGE", "D"), ("GREEN", "G"), ("PEACH", "H"),
    ("BROWN", "I"), ("PINK", "K"), ("GOLD", "M"), ("ORANGE", "O"), ("BURGUNDY", "Q"),
    ("RED", "R"), ("SILVER", "S"), ("GRAY", "T"), ("VIOLET", "V"), ("WHITE", "W"),
    ("YELLOW", "Y"), ("MAGENTA", "Z"),
]
# Internal color only, NOT a primary color
NA_COLOR = ("NA", "AD")
 
# (table, id column) pairs whose counters get restarted at 1
IDENTITY_TABLES = [
    ("tbl_internal_color_code", "in_code_no"),
    ("tbl_primary_color", "id"),
]
 
 
def reset_identity(connection):
    """Make the next inserted row get ID 1 (the equivalent of TRUNCATE ... RESTART IDENTITY)."""
    vendor = connection.vendor
    with connection.cursor() as cur:
        for table, col in IDENTITY_TABLES:
            if vendor == "postgresql":
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), 1, false)")
            elif vendor == "microsoft":  # SQL Server
                cur.execute(f"DBCC CHECKIDENT ('{table}', RESEED, 0)")
            elif vendor == "mysql":
                cur.execute(f"ALTER TABLE {table} AUTO_INCREMENT = 1")
            elif vendor == "sqlite":
                cur.execute("DELETE FROM sqlite_sequence WHERE name = %s", [table])
 
 
def reset_and_seed(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor not in ("postgresql", "microsoft", "mysql", "sqlite"):
        # stop BEFORE deleting anything
        raise RuntimeError(f"Don't know how to reset identity on '{connection.vendor}'.")
 
    db = connection.alias
    Internal = apps.get_model("main", "tbl_internal_color_code")
    Primary = apps.get_model("main", "tbl_primary_color")
 
    # primary colors first (they point at internal colors), then the internal colors
    Primary.objects.using(db).all().delete()
    Internal.objects.using(db).all().delete()  # honors each FK's on_delete (e.g. SET_NULL)
    reset_identity(connection)
 
    for color, code in PRIMARY_COLORS:
        internal = Internal.objects.using(db).create(color=color, code=code, status="approved")
        primary = Primary.objects.using(db).create(in_code=internal)
        internal.primary_color = primary  # a primary color is listed under itself
        internal.save(update_fields=["primary_color"])
 
    Internal.objects.using(db).create(color=NA_COLOR[0], code=NA_COLOR[1], status="approved")
 
class Migration(migrations.Migration):

    dependencies = [
        ('main', '0069_tbl_primary_color_and_more'),
    ]

    operations = [
        # Going backwards is allowed but does not bring the old colors back.
        migrations.RunPython(reset_and_seed, migrations.RunPython.noop),
    ]
