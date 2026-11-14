from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction

from main.models import (
    tbl_master_formula, tbl_master_formula_info, tbl_master_formula_encode,
    tbl_cmf, tbl_generated_prod_code, tbl_user,
    tbl_mb_extruder_formula, tbl_mb_extruder_formula02,
    tbl_dc_extruder_formula, tbl_dc_extruder_materials, tbl_dc_extruder_version,
)

QUANT = Decimal("0.000001")


def to_dec(value):
    """Normalize any numeric value to a 6-decimal Decimal (None -> 0)."""
    try:
        return Decimal(str(value if value is not None else 0)).quantize(QUANT, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0").quantize(QUANT)


def to_int(value):
    """Master formula stores CMYK as Decimal, extruder tables use Integer."""
    if value is None:
        return None
    try:
        return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return None


def norm_ings(pairs):
    """pairs: iterable of (material, value) -> sorted list of normalized tuples."""
    out = []
    for material, value in pairs:
        m = (material or "").strip().lower()
        v = to_dec(value)
        if m and v != 0:
            out.append((m, v))
    return sorted(out)


def resolve_matcher(raw):
    """
    Returns (matched_by_text, username).
    matched_by_text -> canonical full name (or the original text if no rule matches)
    username        -> tbl_user.username (or None if no rule matches)
    """
    text = (raw or "").strip()
    clean = text.lower()
    if not clean:
        return "", None

    if "ann" in clean or "ana" in clean or "anna" in clean:
        return "ana solomon", "ana"
    if "ernie" in clean:
        return "ernie pio", "polycolor"
    if clean == "geelyn rellin":
        return "geelyn rellin", "geelyn"
    if clean == "jinky":
        return "jinky villacampa", "Jinky"
    if clean == "esa":
        return "esa", "Elton"
    if clean == "linzy jam bautista":
        return "linzy jam bautista", "Jam"
    return text, None


class Command(BaseCommand):
    help = (
        "Migrates tbl_master_formula records into MB (no '-' in product code) or "
        "DC (has '-') extruder formulas, only when cm_no exists in tbl_cmf."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Show what would happen without saving anything.",
        )
        parser.add_argument(
            "--cm-no", type=str, default=None,
            help="Only process master formulas with this CM number.",
        )

    # ------------------------------------------------------------------
    # Duplicate checks
    # ------------------------------------------------------------------
    def _mb_duplicate_exists(self, prod_code_obj, cmf_obj, target):
        qs = tbl_mb_extruder_formula.objects.filter(code=prod_code_obj, cm_no=cmf_obj)
        for mb in qs:
            existing = norm_ings(
                (d.material, d.value) for d in mb.tbl_mb_extruder_formula02_set.all()
            )
            if existing == target:
                return True
        return False

    def _dc_duplicate_exists(self, prod_code_obj, cmf_obj, target):
        qs = tbl_dc_extruder_formula.objects.filter(
            code=prod_code_obj, cm_no=cmf_obj
        ).prefetch_related("dc_materials__versions")
        for dc in qs:
            # Compare version by version (v1, v2, ...) so versions don't get mixed together
            by_version = {}
            for mat in dc.dc_materials.all():
                for ver in mat.versions.all():
                    by_version.setdefault(ver.version_no, []).append((mat.material, ver.value))
            for pairs in by_version.values():
                if norm_ings(pairs) == target:
                    return True
        return False

    # ------------------------------------------------------------------
    # Main
    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        only_cm_no = (options.get("cm_no") or "").strip()
        self.stdout.write(self.style.NOTICE(
            f"Starting Master Formula migration{' (DRY RUN)' if dry_run else ''}..."
        ))

        # Cache CMF numbers (case-insensitive) and users
        cmf_map = {c.cm_no.strip().lower(): c for c in tbl_cmf.objects.all() if c.cm_no}
        user_cache = {}

        def get_user(username):
            if not username:
                return None
            key = username.lower()
            if key not in user_cache:
                user_cache[key] = tbl_user.objects.filter(username__iexact=username).first()
            return user_cache[key]

        stats = {
            "migrated_mb": 0,
            "migrated_dc": 0,
            "duplicates": 0,
            "no_cmf": 0,
            "no_prod_code": 0,
            "no_materials": 0,
            "errors": 0,
        }

        master_formulas = tbl_master_formula.objects.filter(is_deleted=False).order_by("form_id")
        if only_cm_no:
            master_formulas = master_formulas.filter(cm_no__iexact=only_cm_no)

        for mf in master_formulas:
            try:
                with transaction.atomic():
                    result = self._process(mf, cmf_map, get_user, dry_run)
                stats[result] += 1
            except Exception as e:
                stats["errors"] += 1
                self.stdout.write(self.style.ERROR(f"Error on master formula #{mf.form_id}: {e}"))

        self.stdout.write(self.style.SUCCESS(
            "Sync complete!\n"
            f" - Migrated to MB extruder: {stats['migrated_mb']}\n"
            f" - Migrated to DC extruder: {stats['migrated_dc']}\n"
            f" - Already existing (marked deleted only): {stats['duplicates']}\n"
            f" - Skipped (CMF not in tbl_cmf): {stats['no_cmf']}\n"
            f" - Skipped (no product code): {stats['no_prod_code']}\n"
            f" - Skipped (no materials): {stats['no_materials']}\n"
            f" - Errors: {stats['errors']}"
        ))

    def _process(self, mf, cmf_map, get_user, dry_run):
        # 1. CMF must exist in tbl_cmf, otherwise do nothing
        raw_cm = (mf.cm_no or "").strip()
        cmf_obj = cmf_map.get(raw_cm.lower()) if raw_cm else None
        if not cmf_obj:
            return "no_cmf"

        # 2. Product code
        prod_code_str = (mf.product_code or "").strip()
        if not prod_code_str:
            return "no_prod_code"

        # 3. Master formula ingredients (only non-deleted)
        mf_infos = list(
            tbl_master_formula_info.objects.filter(form=mf, is_deleted=False).order_by("sequence_no")
        )
        target = norm_ings((mi.material_code, mi.concentration) for mi in mf_infos)
        if not target:
            return "no_materials"

        is_dc = "-" in prod_code_str

        # 4. Get / create the generated product code
        prod_code_obj = tbl_generated_prod_code.objects.filter(
            product_code__iexact=prod_code_str
        ).first()
        if not prod_code_obj:
            if dry_run:
                prod_code_obj = None  # nothing can exist for a new code -> not a duplicate
            else:
                prod_code_obj = tbl_generated_prod_code.objects.create(product_code=prod_code_str)

        # 5. Duplicate check against existing extruder records (same CM + same code + same formula)
        if prod_code_obj is not None:
            if is_dc:
                duplicate = self._dc_duplicate_exists(prod_code_obj, cmf_obj, target)
            else:
                duplicate = self._mb_duplicate_exists(prod_code_obj, cmf_obj, target)

            if duplicate:
                if not dry_run:
                    mf.is_deleted = True
                    mf.save(update_fields=["is_deleted"])
                return "duplicates"

        # 6. Encoding info
        encode_info = tbl_master_formula_encode.objects.filter(form=mf).first()
        matched_by_text, username = resolve_matcher(encode_info.match_by if encode_info else "")
        matcher_user = get_user(username)
        encoded_by = encode_info.encoded_by if encode_info else None
        updated_by = encode_info.updated_by if encode_info else None

        if dry_run:
            self.stdout.write(
                f"[DRY RUN] #{mf.form_id} cm={cmf_obj.cm_no} code={prod_code_str} -> {'DC' if is_dc else 'MB'}"
            )
            return "migrated_dc" if is_dc else "migrated_mb"

        # 7. Insert
        common = dict(
            index_no=mf.index_no,
            date=mf.colormatch_date,
            code=prod_code_obj,
            customer_color=mf.prod_color,
            mixing_time=mf.mix_time,
            notes=mf.notes,
            matched_by=matched_by_text,
            encoded_by=encoded_by,
            updated_by=updated_by,
            cm_no=cmf_obj,
            html=mf.html_code_hex,
            c=to_int(mf.cyan),
            m=to_int(mf.magenta),
            y=to_int(mf.yellow),
            k=to_int(mf.black),
            matcher=matcher_user,
        )

        if is_dc:
            # DC model has no lot_no field
            dc_header = tbl_dc_extruder_formula.objects.create(**common)
            for mi in mf_infos:
                mat = tbl_dc_extruder_materials.objects.create(dc=dc_header, material=mi.material_code)
                tbl_dc_extruder_version.objects.create(
                    material=mat, version_no=1, value=mi.concentration
                )
            result = "migrated_dc"
        else:
            mb_header = tbl_mb_extruder_formula.objects.create(lot_no=mf.lot_no, **common)
            for mi in mf_infos:
                tbl_mb_extruder_formula02.objects.create(
                    mb=mb_header, material=mi.material_code, value=mi.concentration, weight=None
                )
            result = "migrated_mb"

        # 8. Transferred -> mark master formula as deleted
        mf.is_deleted = True
        mf.save(update_fields=["is_deleted"])
        return result

    # python manage.py migrate_oldmaster_to_newformula
    # get all master formulas, check if cm_no exists in tbl_cmf, 
    # check if product code exists in tbl_generated_prod_code, 
    # check if ingredients exist, check if duplicate exists in MB or DC extruder tables, 
    # if not, create new MB or DC extruder formula and mark master formula as deleted.