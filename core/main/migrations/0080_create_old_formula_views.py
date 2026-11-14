from django.db import migrations

CREATE_OLD_FORMULA01 = """
CREATE OR REPLACE VIEW old_formula01 AS
SELECT
    ('master_formula-' || mf.form_id)::varchar(40) AS view_id,
    'master_formula'::varchar(20) AS source,
    mf.form_id,
    mf.index_no,
    mf.date,
    mf.customer,
    mf.product_code,
    mf.prod_color,
    mf.dosage,
    mf.total_concentration,
    mf.ld,
    mf.mix_time,
    mf.resin,
    mf.application,
    mf.cm_no,
    mf.lot_no,
    mf.colormatch_date,
    mf.notes,
    mf.date_modified,
    mf.is_deleted,
    mf.is_used,
    mf.html_code_hex,
    mf.cyan,
    mf.magenta,
    mf.yellow,
    mf.black,
    mf.colorant_type,
    enc.match_by,
    enc.encoded_by,
    enc.updated_by
FROM tbl_master_formula mf
LEFT JOIN (
    SELECT DISTINCT ON (form_id) form_id, match_by, encoded_by, updated_by
    FROM tbl_master_formula_encode
    ORDER BY form_id, encode_id
) enc ON enc.form_id = mf.form_id
WHERE mf.is_deleted = false

UNION ALL

SELECT
    ('formula-' || f.form_id)::varchar(40),
    'formula'::varchar(20),
    f.form_id,
    f.index_no,
    f.date,
    f.customer,
    f.prod_code,
    f.prod_color,
    f.dosage,
    f.total_concentration,
    f.ld,
    f.mix_time,
    f.resin,
    f.application,
    f.colormatch_no,
    f.lot_no,
    f.colormatch_date,
    f.notes,
    f.date_time,
    f.is_deleted,
    f.is_used,
    NULL::varchar(10),
    NULL::numeric(12,6),
    NULL::numeric(12,6),
    NULL::numeric(12,6),
    NULL::numeric(12,6),
    NULL::varchar(5),
    enc.match_by,
    enc.encoded_by,
    enc.updated_by
FROM tbl_formula01 f
LEFT JOIN (
    SELECT DISTINCT ON (form_id) form_id, match_by, encoded_by, updated_by
    FROM tbl_formula_encode
    ORDER BY form_id, encode_id
) enc ON enc.form_id = f.form_id
WHERE f.is_deleted = false

ORDER BY colormatch_date ASC NULLS LAST, source, form_id;
"""

CREATE_OLD_FORMULA02 = """
CREATE OR REPLACE VIEW old_formula02 AS
SELECT
    ('master_formula-' || i.id)::varchar(40) AS view_id,
    'master_formula'::varchar(20) AS source,
    i.form_id,
    i.sequence_no,
    i.material_code,
    i.concentration,
    i.is_deleted
FROM tbl_master_formula_info i
WHERE i.is_deleted = false

UNION ALL

SELECT
    ('formula-' || i.id)::varchar(40),
    'formula'::varchar(20),
    i.form_id,
    i.sequence_no,
    i.material_code,
    i.concentration,
    i.is_deleted
FROM tbl_formula02 i
WHERE i.is_deleted = false;
"""

class Migration(migrations.Migration):

    dependencies = [
        ('main', '0079_old_formula01_old_formula02'),
    ]

    operations = [
        migrations.RunSQL(CREATE_OLD_FORMULA01, "DROP VIEW IF EXISTS old_formula01;"),
        migrations.RunSQL(CREATE_OLD_FORMULA02, "DROP VIEW IF EXISTS old_formula02;"),
    ]
