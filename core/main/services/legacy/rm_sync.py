import dbfread
from django.core.cache import cache
from django.db import connection, transaction
from .dbf_utils import to_bool, to_str, to_int, is_valid_date, dbf_path

def sync_rm_list(progress_callback=None):
    """
    Syncs tbl_raw_material_list from the RM warehouse DBF.
    Uses ON CONFLICT DO NOTHING instead of TRUNCATE to avoid breaking foreign keys.
    """
    def emit(msg):
        if progress_callback: progress_callback(msg)

    emit("RM List: reading unique material codes from warehouse...")
    unique_rm_codes = set()
    dbf = dbfread.DBF(dbf_path('rm_wh'), encoding='latin1', char_decode_errors='ignore')
    
    for r in dbf:
        # Skip deleted records
        if to_bool(r.get('T_DELETED')):
            continue
            
        code = to_str(r.get('T_MATCODE'))
        if code:
            unique_rm_codes.add(code)

    if not unique_rm_codes:
        emit("RM List: No active materials found.")
        return 0

    data = [{"rm_code": code} for code in unique_rm_codes]

    emit(f"RM List: writing {len(data)} codes to PostgreSQL...")
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # We use ON CONFLICT DO NOTHING so we don't duplicate existing codes
                # This is much safer and faster than TRUNCATE
                cursor.executemany("""
                    INSERT INTO tbl_raw_material_list (rm_code) 
                    VALUES (%(rm_code)s)
                    ON CONFLICT (rm_code) DO NOTHING
                """, data)

            emit(f"RM List: Sync completed.")
            return len(data)
    except Exception as e:
            emit(f"Critical Error during Master Formula save: {e}")
            raise e
    


def sync_rm_incoming(progress_callback=None):
    """
    Mirrors the latest incoming record per material code.
    Uses incremental logic to skip old records based on a UID if available.
    """
    def emit(msg):
        if progress_callback: progress_callback(msg)

    # Note: If your tbl_rm_incoming has a 'uid' column, we can use it to skip.
    # Otherwise, we scan the DBF but use an efficient UPSERT.
    emit("RM Incoming: scanning incoming file for latest records...")
    dbf = dbfread.DBF(dbf_path('rm_incoming'), encoding='latin1', char_decode_errors='ignore')
    
    latest_by_code = {}
    
    for r in dbf:
        # Skip deleted records and records with invalid IDs (like 0)
        uid = to_int(r.get('T_UID'))
        if to_bool(r.get('T_DELETED')) or (uid is not None and uid <= 0):
            continue

        mat_code = to_str(r.get('T_MATCODE'))
        if not mat_code:
            continue

        raw_date = r.get('T_DATE')
        valid = is_valid_date(raw_date)
        
        existing = latest_by_code.get(mat_code)
        
        # If this is the first time we see this code, or this record is newer than the one we stored
        if existing is None or (valid and (not existing['date'] or raw_date > existing['date'])):
            latest_by_code[mat_code] = {
                "material_code": mat_code,
                "note": to_str(r.get('T_NOTE')),
                "date": raw_date if valid else None,
            }

    if not latest_by_code:
        emit("RM Incoming: No new records to sync.")
        return 0

    data = list(latest_by_code.values())

    emit(f"RM Incoming: Updating {len(data)} latest incoming timestamps...")
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # ON CONFLICT (material_code) ensures we only ever have ONE 'latest' record per material
                cursor.executemany("""
                    INSERT INTO tbl_rm_incoming (date, material_code, note)
                    VALUES (%(date)s, %(material_code)s, %(note)s)
                    ON CONFLICT (material_code) 
                    DO UPDATE SET 
                        note = EXCLUDED.note, 
                        date = EXCLUDED.date
                """, data)

            emit(f"RM Incoming: Successfully synced.")
            cache.delete('raw_material_codes')
            return len(data)
    except Exception as e:
        emit(f"Critical Error during Master Formula save: {e}")
        raise e
