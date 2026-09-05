import collections
import dbfread
from django.db import connection, transaction
from .dbf_utils import to_bool, to_float, to_int, to_str, dbf_path

def sync_production(progress_callback=None):
    def emit(msg):
        if progress_callback: progress_callback(msg)

    # 1. Get High-Water Mark
    with connection.cursor() as cursor:
        cursor.execute("SELECT MAX(prod_id) FROM tbl_production01")
        res = cursor.fetchone()
        max_id = res[0] if res and res[0] is not None else 0

    emit(f"Production: Syncing records newer than ID {max_id}...")

    # 2. Read Items (Skip PID 0 and Old)
    items_by_prod_id = collections.defaultdict(list)
    dbf_p_items = dbfread.DBF(dbf_path('production_items'), encoding='latin1', char_decode_errors='ignore')
    for item in dbf_p_items:
        pid = to_int(item.get('T_PRODID'))
        if pid is None or pid <= 0 or pid <= max_id:
            continue
        items_by_prod_id[pid].append({
            "prod_id": pid, "seq": to_int(item.get('T_SEQ')),
            "material_code": to_str(item.get('T_MATCODE')),
            "large_scale": to_float(item.get('T_PRODA')),
            "small_scale": to_float(item.get('T_LABA')),
            "total_weight": to_float(item.get('T_WT')),
            "total_loss": to_float(item.get('T_LOSS')),
            "total_consumption": to_float(item.get('T_CONS')),
            "is_deleted": to_bool(item.get('T_DELETED')),
        })

    # 3. Read Primary (Skip PID 0 and Old)
    prod_recs = []
    dbf_prod = dbfread.DBF(dbf_path('production_primary'), encoding='latin1', char_decode_errors='ignore')
    for r in dbf_prod:
        pid = to_int(r.get('T_PRODID'))
        if pid is None or pid <= 0 or pid <= max_id:
            continue

        rem = to_str(r.get('T_REMARKS'))
        note_raw = to_str(r.get('T_NOTE'))
        note = f"{note_raw}\n{rem}".strip() if rem else note_raw
        is_printed = (to_str(r.get('T_JDONE')).upper() == "PRINTED")

        prod_recs.append({
            "prod_id": pid, "prod_date": r.get('T_PRODDATE'),
            "customer": to_str(r.get('T_CUSTOMER')), "form_id": to_int(r.get('T_FID')),
            "index_no": to_str(r.get('T_INDEX')), "prod_code": to_str(r.get('T_PRODCODE')),
            "prod_color": to_str(r.get('T_PRODCOLO')), "dosage": to_float(r.get('T_DOSAGE')),
            "ld": to_float(r.get('T_LD')), "lot_no": to_str(r.get('T_LOTNUM')),
            "order_no": to_str(r.get('T_ORDERNUM')), "colormatch_no": to_str(r.get('T_CMNUM')),
            "colormatch_date": r.get('T_CMDATE'), "mix_time": to_str(r.get('T_MIXTIME')),
            "machine_no": to_str(r.get('T_MACHINE')), "note": note,
            "user_id": to_str(r.get('T_USERID')), "form_type": to_str(r.get('T_FTYPE')),
            "inventory_c_date": r.get('T_CDATE'),
            "is_deleted": to_bool(r.get('T_DELETED')), "is_printed": is_printed,
            "prepared_by": to_str(r.get('T_PREPARED')), "encoded_by": to_str(r.get('T_ENCODEDB')),
            "encoded_on": r.get('T_ENCODEDO'), "conf_encoded_on": r.get('T_SDATE'),
            "qty_req": to_float(r.get('T_QTYREQ')), "qty_batch": to_float(r.get('T_QTYBATCH')),
            "qty_prod": to_float(r.get('T_QTYPROD')),
        })

    if not prod_recs:
        emit("Production: Already up to date.")
        return 0

    emit(f"Production: Found {len(prod_recs)} new records to sync.")
    # 4. Write to Postgres
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.executemany("""
                    INSERT INTO tbl_production01 (prod_id, prod_date, customer, form_id, index_no, prod_code, prod_color, dosage, ld, lot_no, order_no, colormatch_no, colormatch_date, mix_time, machine_no, note, user_id, is_deleted, is_printed, inventory_c_date, form_type)
                    VALUES (%(prod_id)s, %(prod_date)s, %(customer)s, %(form_id)s, %(index_no)s, %(prod_code)s, %(prod_color)s, %(dosage)s, %(ld)s, %(lot_no)s, %(order_no)s, %(colormatch_no)s, %(colormatch_date)s, %(mix_time)s, %(machine_no)s, %(note)s, %(user_id)s, %(is_deleted)s, %(is_printed)s, %(inventory_c_date)s, %(form_type)s)
                    ON CONFLICT (prod_id) DO NOTHING;
                """, prod_recs)

                cursor.executemany("""
                    INSERT INTO tbl_production_encode (prod_id, prepared_by, encoded_by, encoded_on, confirmation_encoded_on) 
                    VALUES (%(prod_id)s, %(prepared_by)s, %(encoded_by)s, %(encoded_on)s, %(conf_encoded_on)s)
                    ON CONFLICT DO NOTHING;
                """, prod_recs)

                cursor.executemany("""
                    INSERT INTO tbl_production_quantity (prod_id, quantity_req, quantity_batch, quantity_prod) 
                    VALUES (%(prod_id)s, %(qty_req)s, %(qty_batch)s, %(qty_prod)s)
                    ON CONFLICT DO NOTHING;
                """, prod_recs)

                all_items = [i for r in prod_recs for i in items_by_prod_id.get(r['prod_id'], [])]
                if all_items:
                    cursor.executemany("""
                        INSERT INTO tbl_production02 (prod_id, sequence_no, material_code, large_scale, small_scale, total_weight, is_deleted, total_loss, total_consumption)
                        VALUES (%(prod_id)s, %(seq)s, %(material_code)s, %(large_scale)s, %(small_scale)s, %(total_weight)s, %(is_deleted)s, %(total_loss)s, %(total_consumption)s)
                        ON CONFLICT DO NOTHING;
                    """, all_items)

            emit(f"Production: synced {len(prod_recs)} new records.")
            return len(prod_recs)
    except Exception as e:
        emit(f"Critical Error during Master Formula save: {e}")
        raise e
