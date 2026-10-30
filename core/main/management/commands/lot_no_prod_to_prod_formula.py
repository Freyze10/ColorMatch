from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from main.models import tbl_formula01, tbl_production01

def format_and_sync_production_lots():
    """
    Checks if formula_01's form_id is used in tbl_production01.form_id.
    Formats the production lot_no based on year and prod_code type (MB vs DC),
    then updates tbl_formula01.lot_no.
    """
    updated_count = 0
    
    # Fetch formulas that have a matching production record
    formulas = tbl_formula01.objects.filter(is_deleted=False)

    with transaction.atomic():
        for formula in formulas:
            # Find matching production record by form_id
            prod = tbl_production01.objects.filter(form_id=formula.form_id, is_deleted=False).first()
            if not prod or not prod.lot_no:
                continue

            raw_lot = str(prod.lot_no).strip()
            if not raw_lot or raw_lot.upper() in ('NA', 'NONE', '---'):
                continue

            # Determine product type: contains '-' = DC, else = MB
            prod_code = str(formula.prod_code or '').strip()
            is_dc = '-' in prod_code

            # Extract Year from prod_date (e.g., 2026 -> "26")
            year_str = ""
            if prod.prod_date:
                year_str = prod.prod_date.strftime('%y') # 2-digit year like '26'

            formatted_lot = ""

            if is_dc:
                # DC Format: Year is ignored. Split ranges if they exist (e.g. "1547Y-1572Y")
                parts = [p.strip() for p in raw_lot.split('-') if p.strip()]
                
                if len(parts) > 1:
                    formatted_parts = [f"95-{p}" for p in parts]
                    formatted_lot = " - ".join(formatted_parts)
                else:
                    formatted_lot = f"95-{raw_lot}"
            else:
                # MB Format: Include year-digit (e.g., MB-26-1409AP or ranges)
                prefix = f"MB-{year_str}-" if year_str else "MB-"
                
                parts = [p.strip() for p in raw_lot.split('-') if p.strip()]
                
                if len(parts) > 1 and not raw_lot.upper().startswith('MB-'):
                    formatted_parts = [f"{prefix}{p}" for p in parts]
                    formatted_lot = " - ".join(formatted_parts)
                elif raw_lot.upper().startswith('MB-'):
                    formatted_lot = raw_lot
                else:
                    formatted_lot = f"{prefix}{raw_lot}"

            # Update tbl_formula01 if the formatted lot is different
            if formula.lot_no != formatted_lot:
                formula.lot_no = formatted_lot
                formula.save(update_fields=['lot_no'])
                updated_count += 1

    return updated_count


class Command(BaseCommand):
    help = 'Formats and syncs production lot numbers into tbl_formula01 based on production data.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting standalone lot number formatting..."))
        
        try:
            updated_count = format_and_sync_production_lots()
            self.stdout.write(self.style.SUCCESS(f"Successfully updated lot numbers for {updated_count} formula records!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error occurred during lot formatting: {str(e)}"))


# to run this. type this in the terminal: python manage.py lot_no_prod_to_prod_formula