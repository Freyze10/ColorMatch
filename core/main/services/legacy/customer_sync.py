import dbfread
from django.core.cache import cache
from django.db import connection, transaction
from .dbf_utils import to_bool, to_str, dbf_path

def sync_customer_list(progress_callback=None):
    """
    Syncs tbl_customer from the legacy customer DBF using the 't_customer' column.
    """
    def emit(msg):
        if progress_callback: progress_callback(msg)

    emit("Customer Sync: Reading unique names from legacy DBF...")
    unique_customers = set()
    
    try:
        dbf = dbfread.DBF(dbf_path('customer'), encoding='latin1', char_decode_errors='ignore')
        
        for r in dbf:
            # Skip deleted records
            if to_bool(r.get('T_DELETED')):
                continue
                
            # Using your specific column name 't_customer'
            name = to_str(r.get('T_CUSTOMER'))
            if name:
                unique_customers.add(name)

    except Exception as e:
        emit(f"Customer Sync Error: {str(e)}")
        return 0

    if not unique_customers:
        emit("Customer Sync: No active customers found.")
        return 0

    data = [{"customer": name} for name in unique_customers]

    emit(f"Customer Sync: Writing {len(data)} unique records to PostgreSQL...")
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.executemany("""
                    INSERT INTO tbl_customer (customer) 
                    VALUES (%(customer)s)
                    ON CONFLICT (customer) DO NOTHING
                """, data)

            emit(f"Customer Sync: Completed.")
            cache.delete('customer_list')
            return len(data)
    except Exception as e:
        emit(f"Critical Error during Master Formula save: {e}")
        raise e
