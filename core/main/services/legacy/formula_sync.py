import collections
import dbfread
from django.db import connection, transaction
from .dbf_utils import to_bool, to_float, to_int, to_str, is_valid_date, dbf_path

def sync_formula(progress_callback=None):
    def emit(msg):
        if progress_callback:
            progress_callback(msg)

    # --- STEP 1: GET LATEST ID FROM POSTGRES ---
    with connection.cursor() as cursor:
        cursor.execute("SELECT MAX(form_id) FROM tbl_formula01")
        res = cursor.fetchone()
        # If table is empty, start from 0
        max_id = res[0] if res and res[0] else 0

    emit(f"Formula: Syncing records newer than ID {max_id}...")

    # --- STEP 2: READ ITEMS (Filtering by UID) ---
    emit("Formula: reading formula items...")
    items_by_uid = collections.defaultdict(list)
    dbf_f_items = dbfread.DBF(dbf_path('formula_items'), encoding='latin1', char_decode_errors='ignore')
    
    for item in dbf_f_items:
        uid = to_int(item.get('T_UID'))
        # Skip if UID is old or invalid
        if uid is None or uid <= max_id:
            continue
            
        items_by_uid[uid].append({
            "uid": uid, 
            "seq": to_int(item.get('T_SEQ')),
            "material_code": to_str(item.get('T_MATCODE')),
            "concentration": to_float(item.get('T_CON')),
            "is_deleted": to_bool(item.get('T_DELETED')),
        })

    # --- STEP 3: READ PRIMARY (Filtering by UID) ---
    emit("Formula: reading primary records...")
    primary_recs = []
    dbf_primary = dbfread.DBF(dbf_path('formula_primary'), encoding='latin1', char_decode_errors='ignore')
    
    for r in dbf_primary:
        uid = to_int(r.get('T_UID'))
        # Skip if UID is old or invalid
        if uid is None or uid <= max_id:
            continue
            
        primary_recs.append({
            "uid": uid, 
            "index_no": to_str(r.get('T_INDEX')),
            "date": r.get('T_DATE'), 
            "customer": to_str(r.get('T_CUSTOMER')),
            "prod_code": to_str(r.get('T_PRODCODE')), 
            "prod_color": to_str(r.get('T_PRODCOLO')),
            "dosage": to_float(r.get('T_DOSAGE')), 
            "ld": to_float(r.get('T_LD')),
            "total_concentration": to_float(r.get('T_TOTALCON')), 
            "mix_time": to_str(r.get('T_MIX')),
            "resin": to_str(r.get('T_RESIN')), 
            "application": to_str(r.get('T_APP')),
            "cm_num": to_str(r.get('T_CMNUM')),
            "cm_date": r.get('T_CMDATE') if is_valid_date(r.get('T_CMDATE')) else None,
            "notes": to_str(r.get('T_REM')), 
            "date_time": to_str(r.get('T_UDATE')),
            "is_deleted": to_bool(r.get('T_DELETED')), 
            "is_used": to_bool(r.get('T_USED')),
            "matched_by": to_str(r.get('T_MATCHBY')), 
            "encoded_by": to_str(r.get('T_ENCODEDB')),
            "updated_by": to_str(r.get('T_UPDATEBY')),
        })

    if not primary_recs:
        emit("Formula: Database is already up to date.")
        return 0

    # --- STEP 4: WRITE ONLY NEW RECORDS ---
    emit(f"Formula: Writing {len(primary_recs)} new records to PostgreSQL...")
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # Simple INSERT since we filtered for NEW records only
                cursor.executemany("""
                    INSERT INTO tbl_formula01 (
                        form_id, index_no, date, customer, prod_code, prod_color, 
                        dosage, total_concentration, ld, mix_time, resin, application, 
                        colormatch_no, colormatch_date, notes, date_time, is_deleted, is_used
                    )
                    VALUES (
                        %(uid)s, %(index_no)s, %(date)s, %(customer)s, %(prod_code)s, %(prod_color)s, 
                        %(dosage)s, %(total_concentration)s, %(ld)s, %(mix_time)s, %(resin)s, %(application)s, 
                        %(cm_num)s, %(cm_date)s, %(notes)s, %(date_time)s, %(is_deleted)s, %(is_used)s
                    )
                    ON CONFLICT (form_id) DO NOTHING;
                """, primary_recs)

                # Sync Encode details
                cursor.executemany("""
                    INSERT INTO tbl_formula_encode (form_id, match_by, encoded_by, updated_by) 
                    VALUES (%(uid)s, %(matched_by)s, %(encoded_by)s, %(updated_by)s)
                    ON CONFLICT DO NOTHING;
                """, primary_recs)

                # Sync Item details
                all_f_items = [i for r in primary_recs for i in items_by_uid.get(r['uid'], [])]
                if all_f_items:
                    cursor.executemany("""
                        INSERT INTO tbl_formula02 (form_id, sequence_no, material_code, concentration, is_deleted) 
                        VALUES (%(uid)s, %(seq)s, %(material_code)s, %(concentration)s, %(is_deleted)s)
                        ON CONFLICT DO NOTHING;
                    """, all_f_items)

            emit(f"Formula: Successfully added {len(primary_recs)} new records.")
            return len(primary_recs)
    except Exception as e:
        emit(f"Critical Error during Master Formula save: {e}")
        raise e
