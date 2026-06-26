from django.db import models


# ==========================================
# 1. USER & ACCESS CONTROL MODULE
# ==========================================

class tbl_role(models.Model):
    role_id = models.AutoField(primary_key=True)
    department = models.CharField(max_length=100)
    role = models.CharField(max_length=50)

    class Meta:
        db_table = "tbl_role"
        unique_together = ("department", "role")

    def __str__(self):
        return f"{self.department} - {self.role}"


class tbl_user(models.Model):
    user_id = models.AutoField(primary_key=True)
    hostname = models.CharField(max_length=100, blank=True, null=True)
    ip_address = models.CharField(max_length=50, blank=True, null=True)
    mac_address = models.CharField(max_length=50, unique=True, blank=True, null=True)
    username = models.CharField(max_length=50)
    password = models.CharField(max_length=100)
    role = models.ForeignKey(tbl_role, on_delete=models.SET_NULL, null=True, blank=True, db_column="role_id")

    class Meta:
        db_table = "tbl_user"

    def __str__(self):
        return self.username


class tbl_access_point(models.Model):
    access_id = models.AutoField(primary_key=True)
    access_name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "tbl_access_point"

    def __str__(self):
        return self.access_name


class tbl_role_permissions(models.Model):
    permission_id = models.AutoField(primary_key=True)
    access = models.ForeignKey(tbl_access_point, on_delete=models.CASCADE, db_column="access_id")
    is_enabled = models.BooleanField(default=False)
    role = models.ForeignKey(tbl_role, on_delete=models.CASCADE, db_column="role_id")

    class Meta:
        db_table = "tbl_role_permissions"
        unique_together = ("role", "access")

    def __str__(self):
        return f"{self.role} - {self.access} ({'enabled' if self.is_enabled else 'disabled'})"


class tbl_audit_trail(models.Model):
    id = models.AutoField(primary_key=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(tbl_user, on_delete=models.SET_NULL, null=True, blank=True, db_column="user_id")
    action_type = models.CharField(max_length=50, blank=True, null=True)
    details = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "tbl_audit_trail"

    def __str__(self):
        return f"{self.timestamp} - {self.action_type}"


# ==========================================
# 2. PRODUCT CODES
# ==========================================

class tbl_internal_color_code(models.Model):
    in_code_no = models.AutoField(primary_key=True)
    color = models.CharField(max_length=100, blank=True, null=True)
    code = models.CharField(max_length=100, unique=True, blank=True, null=True)

    class Meta:
        db_table = "tbl_internal_color_code"

    def __str__(self):
        return f"{self.code} - {self.color}"


class tbl_generated_prod_code(models.Model):
    code_no = models.AutoField(primary_key=True)
    product_code = models.CharField(max_length=100, unique=True, blank=True, null=True)
    in_code = models.ForeignKey(tbl_internal_color_code, on_delete=models.SET_NULL, null=True, blank=True, db_column="in_code_no")

    class Meta:
        db_table = "tbl_generated_prod_code"

    def __str__(self):
        return self.product_code or str(self.code_no)


# ==========================================
# 3. CMF (COLOR MATCHING) MODULE
# ==========================================

class tbl_cmf_salesman(models.Model):
    sm_no = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = "tbl_cmf_salesman"

    def __str__(self):
        return self.name or str(self.sm_no)


class tbl_cmf_process(models.Model):
    process_no = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = "tbl_cmf_process"

    def __str__(self):
        return self.name or str(self.process_no)


class tbl_cmf_specification(models.Model):
    spec_no = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = "tbl_cmf_specification"

    def __str__(self):
        return self.name or str(self.spec_no)


class tbl_cmf_add_info(models.Model):
    info_no = models.AutoField(primary_key=True)
    information_details = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "tbl_cmf_add_info"

    def __str__(self):
        return str(self.info_no)


class tbl_cmf(models.Model):
    id = models.AutoField(primary_key=True)
    cm_no = models.CharField(max_length=50, unique=True)
    matching_type = models.CharField(max_length=50, blank=True, null=True)
    sm = models.ForeignKey(tbl_cmf_salesman, on_delete=models.SET_NULL, null=True, blank=True, db_column="sm_no")
    primary_color = models.CharField(max_length=100, blank=True, null=True)
    color_desc = models.TextField(blank=True, null=True)
    qty_resin_testing = models.CharField(max_length=100, blank=True, null=True)
    is_resin_provided = models.BooleanField(null=True, blank=True)
    mi_c_resin = models.CharField(max_length=100, blank=True, null=True)
    is_sample_available = models.BooleanField(null=True, blank=True)
    colorant_type = models.CharField(max_length=100, blank=True, null=True)
    is_guide_to_return = models.BooleanField(null=True, blank=True)
    temperature = models.CharField(max_length=50, blank=True, null=True)
    is_low_cost = models.BooleanField(null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)
    info = models.ForeignKey(tbl_cmf_add_info, on_delete=models.SET_NULL, null=True, blank=True, db_column="info_no")
    user = models.ForeignKey(tbl_user, on_delete=models.SET_NULL, null=True, blank=True, db_column="user_id")

    class Meta:
        db_table = "tbl_cmf"

    def __str__(self):
        return self.cm_no


class tbl_cmf_color_req(models.Model):
    color_req_no = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    cm = models.ForeignKey(tbl_cmf, to_field="cm_no", on_delete=models.CASCADE, null=True, blank=True, db_column="cm_no")

    class Meta:
        db_table = "tbl_cmf_color_req"

    def __str__(self):
        return self.name or str(self.color_req_no)


class tbl_cmf_scanned(models.Model):
    file_id = models.AutoField(primary_key=True)
    cm = models.ForeignKey(tbl_cmf, to_field="cm_no", on_delete=models.CASCADE, db_column="cm_no")
    file_name = models.CharField(max_length=255, blank=True, null=True)
    file_type = models.CharField(max_length=50, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(tbl_user, on_delete=models.SET_NULL, null=True, blank=True, db_column="user_id")

    class Meta:
        db_table = "tbl_cmf_scanned"

    def __str__(self):
        return self.file_name or str(self.file_id)


class tbl_cmf_dates(models.Model):
    cm_dates_no = models.AutoField(primary_key=True)
    form_made = models.DateField(blank=True, null=True)
    date_required = models.CharField(max_length=36, blank=True, null=True)
    date_received_lab = models.CharField(max_length=36, blank=True, null=True)
    due_date_lab = models.DateField(blank=True, null=True)
    cm = models.ForeignKey(tbl_cmf, to_field="cm_no", on_delete=models.CASCADE, db_column="cm_no")

    class Meta:
        db_table = "tbl_cmf_dates"

    def __str__(self):
        return f"Dates for {self.cm_id}"


class tbl_cmf_formula(models.Model):
    cmf_formula_no = models.AutoField(primary_key=True)
    customer = models.CharField(max_length=150, blank=True, null=True)
    finished_product = models.CharField(max_length=150, blank=True, null=True)
    resin = models.CharField(max_length=100, blank=True, null=True)
    dosage = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    cm = models.ForeignKey(tbl_cmf, to_field="cm_no", on_delete=models.CASCADE, db_column="cm_no")

    class Meta:
        db_table = "tbl_cmf_formula"

    def __str__(self):
        return f"{self.customer} - {self.finished_product}"


class tbl_cmf_process02(models.Model):
    chosen_process_no = models.AutoField(primary_key=True)
    cmf_formula = models.ForeignKey(tbl_cmf_formula, on_delete=models.CASCADE, db_column="cmf_formula_no")
    process = models.ForeignKey(tbl_cmf_process, on_delete=models.SET_NULL, null=True, blank=True, db_column="process_no")

    class Meta:
        db_table = "tbl_cmf_process02"


class tbl_cmf_specification02(models.Model):
    chosen_spec_no = models.AutoField(primary_key=True)
    cm = models.ForeignKey(tbl_cmf, to_field="cm_no", on_delete=models.CASCADE, db_column="cm_no")
    spec = models.ForeignKey(tbl_cmf_specification, on_delete=models.SET_NULL, null=True, blank=True, db_column="spec_no")

    class Meta:
        db_table = "tbl_cmf_specification02"


class tbl_cmf_pending_completed(models.Model):
    id = models.AutoField(primary_key=True)
    cm_no = models.CharField(max_length=50, blank=True, null=True)
    matching_type = models.CharField(max_length=50, blank=True, null=True)
    reason = models.TextField(blank=True, null=True)
    prod_code = models.CharField(max_length=100, blank=True, null=True)
    code_details = models.TextField(blank=True, null=True)
    date_submitted = models.DateField(blank=True, null=True)
    ar_no = models.CharField(max_length=50, blank=True, null=True)
    ar_date = models.DateField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)

    class Meta:
        db_table = "tbl_cmf_pending_completed"

    def __str__(self):
        return f"{self.cm_no} - {'Completed' if self.is_completed else 'Pending'}"


# ==========================================
# 4. RS & FEEDBACK
# ==========================================

class tbl_rs(models.Model):
    id = models.AutoField(primary_key=True)
    rs_no = models.CharField(max_length=50, unique=True, blank=True, null=True)
    customer = models.CharField(max_length=150, blank=True, null=True)
    pieces = models.IntegerField(blank=True, null=True)
    quantity_given = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    date_form_made = models.DateField(blank=True, null=True)
    date_lab_received = models.CharField(max_length=36, blank=True, null=True)
    date_required = models.CharField(max_length=36, blank=True, null=True)
    due_date = models.DateField(blank=True, null=True)
    color_description = models.TextField(blank=True, null=True)
    finished_product = models.CharField(max_length=150, blank=True, null=True)
    matching_type = models.CharField(max_length=50, blank=True, null=True)
    lot_no = models.CharField(max_length=100, blank=True, null=True)
    ar_no = models.CharField(max_length=50, blank=True, null=True)
    date_sample_received = models.DateField(blank=True, null=True)
    primary_color = models.CharField(max_length=100, blank=True, null=True)
    color_desc = models.TextField(blank=True, null=True)
    resin = models.CharField(max_length=100, blank=True, null=True)
    chosen_process_no = models.IntegerField(blank=True, null=True)
    colorant_type = models.CharField(max_length=50, blank=True, null=True)
    date_submitted = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    user = models.ForeignKey(tbl_user, on_delete=models.SET_NULL, null=True, blank=True, db_column="user_id")
    cm = models.ForeignKey(tbl_cmf, to_field="cm_no", on_delete=models.SET_NULL, null=True, blank=True, db_column="cm_no")

    class Meta:
        db_table = "tbl_rs"

    def __str__(self):
        return self.rs_no or str(self.id)


class tbl_rs_prod_codes(models.Model):
    rs_code_no = models.AutoField(primary_key=True)
    code = models.ForeignKey(tbl_generated_prod_code, on_delete=models.SET_NULL, null=True, blank=True, db_column="code_no")
    rs = models.ForeignKey(tbl_rs, to_field="rs_no", on_delete=models.SET_NULL, null=True, blank=True, db_column="rs_no")

    class Meta:
        db_table = "tbl_rs_prod_codes"


class tbl_feedback_details(models.Model):
    feedback_no = models.AutoField(primary_key=True)
    rm_feedback_no = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    comment = models.TextField(blank=True, null=True)
    storage_details = models.CharField(max_length=100, blank=True, null=True)
    cm_rs_no = models.CharField(max_length=14, blank=True, null=True)

    class Meta:
        db_table = "tbl_feedback_details"

    def __str__(self):
        return str(self.feedback_no)


# ==========================================
# 5. EXTRUDER FORMULAS
# ==========================================

class tbl_mb_extruder_formula(models.Model):
    mb_no = models.AutoField(primary_key=True)
    date = models.DateField(blank=True, null=True)
    code = models.ForeignKey(tbl_generated_prod_code, on_delete=models.SET_NULL, null=True, blank=True, db_column="code_no")
    lot_no = models.CharField(max_length=100, blank=True, null=True)
    mixing_time = models.CharField(max_length=50, blank=True, null=True)
    matched_by = models.CharField(max_length=100, blank=True, null=True)
    weighted_by = models.CharField(max_length=100, blank=True, null=True)
    encoded_by = models.CharField(max_length=100, blank=True, null=True)
    total_weight = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    cm = models.ForeignKey(tbl_cmf, to_field="cm_no", on_delete=models.SET_NULL, null=True, blank=True, db_column="cm_no")

    class Meta:
        db_table = "tbl_mb_extruder_formula"

    def __str__(self):
        return f"MB Formula #{self.mb_no}"


class tbl_mb_extruder_formula02(models.Model):
    id = models.AutoField(primary_key=True)
    mb = models.ForeignKey(tbl_mb_extruder_formula, on_delete=models.CASCADE, db_column="mb_no")
    material = models.CharField(max_length=150, blank=True, null=True)
    value = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    weight = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)

    class Meta:
        db_table = "tbl_mb_extruder_formula02"


class tbl_dc_extruder_formula(models.Model):
    dc_no = models.AutoField(primary_key=True)
    code = models.ForeignKey(tbl_generated_prod_code, on_delete=models.SET_NULL, null=True, blank=True, db_column="code_no")
    date = models.DateField(blank=True, null=True)
    sample_size = models.CharField(max_length=100, blank=True, null=True)
    mixing_time = models.CharField(max_length=50, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    matched_by = models.CharField(max_length=100, blank=True, null=True)
    weighted_by = models.CharField(max_length=100, blank=True, null=True)
    encoded_by = models.CharField(max_length=100, blank=True, null=True)
    total_weight = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    cm = models.ForeignKey(tbl_cmf, to_field="cm_no", on_delete=models.SET_NULL, null=True, blank=True, db_column="cm_no")

    class Meta:
        db_table = "tbl_dc_extruder_formula"

    def __str__(self):
        return f"DC Formula #{self.dc_no}"


class tbl_dc_extruder_formula02(models.Model):
    id = models.AutoField(primary_key=True)
    dc = models.ForeignKey(tbl_dc_extruder_formula, on_delete=models.CASCADE, db_column="dc_no")
    material = models.CharField(max_length=150, blank=True, null=True)
    value = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    weight = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)

    class Meta:
        db_table = "tbl_dc_extruder_formula02"


# ==========================================
# 6. MASTER & DAILY FORMULAS
# ==========================================

class tbl_master_formula(models.Model):
    form_id = models.AutoField(primary_key=True)
    index_no = models.CharField(max_length=100, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    customer = models.CharField(max_length=150, blank=True, null=True)
    product_code = models.ForeignKey(
        tbl_generated_prod_code,
        to_field="product_code",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="product_code"
    )
    prod_color = models.CharField(max_length=150, blank=True, null=True)
    dosage = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    total_concentration = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    ld = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    mix_time = models.CharField(max_length=100, blank=True, null=True)
    resin = models.CharField(max_length=150, blank=True, null=True)
    application = models.CharField(max_length=150, blank=True, null=True)
    cm_no = models.CharField(max_length=50, blank=True, null=True)
    colormatch_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    date_time = models.DateTimeField(blank=True, null=True)
    is_deleted = models.BooleanField(default=False)
    is_used = models.BooleanField(default=False)
    html_code_hex = models.CharField(max_length=10, blank=True, null=True)
    cyan = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    magenta = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    yellow = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    black = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)

    class Meta:
        db_table = "tbl_master_formula"

    def __str__(self):
        return f"Master Formula #{self.form_id}"


class tbl_master_formula_info(models.Model):
    id = models.AutoField(primary_key=True)
    sequence_no = models.IntegerField(blank=True, null=True)
    material_code = models.CharField(max_length=100, blank=True, null=True)
    concentration = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    form = models.ForeignKey(tbl_master_formula, on_delete=models.CASCADE, db_column="form_id")

    class Meta:
        db_table = "tbl_master_formula_info"


class tbl_master_formula_encode(models.Model):
    encode_id = models.AutoField(primary_key=True)
    form = models.ForeignKey(tbl_master_formula, on_delete=models.CASCADE, db_column="form_id")
    match_by = models.CharField(max_length=100, blank=True, null=True)
    encoded_by = models.CharField(max_length=100, blank=True, null=True)
    updated_by = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = "tbl_master_formula_encode"


class tbl_formula01(models.Model):
    form_id = models.AutoField(primary_key=True)
    index_no = models.CharField(max_length=22, blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    customer = models.CharField(max_length=62, blank=True, null=True)
    prod_code = models.CharField(max_length=22)
    prod_color = models.CharField(max_length=62, blank=True, null=True)
    dosage = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    total_concentration = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    ld = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    mix_time = models.CharField(max_length=22, blank=True, null=True)
    resin = models.CharField(max_length=36, blank=True, null=True)
    application = models.CharField(max_length=36, blank=True, null=True)
    colormatch_no = models.CharField(max_length=8, blank=True, null=True)
    colormatch_date = models.DateField(blank=True, null=True)
    notes = models.CharField(max_length=256, blank=True, null=True)
    date_time = models.CharField(max_length=32, blank=True, null=True)
    is_deleted = models.BooleanField(default=False)
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = "tbl_formula01"

    def __str__(self):
        return f"{self.prod_code} - {self.prod_color}"


class tbl_formula02(models.Model):
    id = models.AutoField(primary_key=True)
    form = models.ForeignKey(tbl_formula01, on_delete=models.CASCADE, db_column="form_id")
    sequence_no = models.IntegerField(blank=True, null=True)
    material_code = models.CharField(max_length=32, blank=True, null=True)
    concentration = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = "tbl_formula02"


class tbl_formula_encode(models.Model):
    encode_id = models.AutoField(primary_key=True)
    form = models.ForeignKey(tbl_formula01, on_delete=models.CASCADE, db_column="form_id")
    match_by = models.CharField(max_length=128, blank=True, null=True)
    encoded_by = models.CharField(max_length=128, blank=True, null=True)
    updated_by = models.CharField(max_length=128, blank=True, null=True)

    class Meta:
        db_table = "tbl_formula_encode"


# ==========================================
# 7. DAILY PRODUCTION
# ==========================================

class tbl_production01(models.Model):
    prod_id = models.AutoField(primary_key=True)
    prod_date = models.DateField(blank=True, null=True)
    customer = models.CharField(max_length=62, blank=True, null=True)
    form_id = models.IntegerField(blank=True, null=True)
    index_no = models.CharField(max_length=32, blank=True, null=True)
    prod_code = models.CharField(max_length=32, blank=True, null=True)
    prod_color = models.CharField(max_length=62, blank=True, null=True)
    dosage = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    ld = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    lot_no = models.CharField(max_length=128, blank=True, null=True)
    order_no = models.CharField(max_length=36, blank=True, null=True)
    colormatch_no = models.CharField(max_length=8, blank=True, null=True)
    colormatch_date = models.DateField(blank=True, null=True)
    mix_time = models.CharField(max_length=32, blank=True, null=True)
    machine_no = models.CharField(max_length=32, blank=True, null=True)
    note = models.CharField(max_length=128, blank=True, null=True)
    user_id = models.CharField(max_length=62, blank=True, null=True)
    is_deleted = models.BooleanField(default=False)
    is_printed = models.BooleanField(default=False)
    inventory_c_date = models.DateField(blank=True, null=True)
    form_type = models.CharField(max_length=16, blank=True, null=True)

    class Meta:
        db_table = "tbl_production01"

    def __str__(self):
        return f"{self.prod_date} - {self.prod_code}"


class tbl_production02(models.Model):
    id = models.AutoField(primary_key=True)
    prod = models.ForeignKey(tbl_production01, on_delete=models.CASCADE, db_column="prod_id")
    sequence_no = models.IntegerField(blank=True, null=True)
    material_code = models.CharField(max_length=32, blank=True, null=True)
    large_scale = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    small_scale = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    total_weight = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    total_loss = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    total_consumption = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)

    class Meta:
        db_table = "tbl_production02"


class tbl_production_quantity(models.Model):
    quantity_id = models.AutoField(primary_key=True)
    prod = models.ForeignKey(tbl_production01, on_delete=models.CASCADE, db_column="prod_id")
    quantity_req = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    quantity_batch = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    quantity_prod = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)

    class Meta:
        db_table = "tbl_production_quantity"


class tbl_production_encode(models.Model):
    encode_id = models.AutoField(primary_key=True)
    prod = models.ForeignKey(tbl_production01, on_delete=models.CASCADE, db_column="prod_id")
    prepared_by = models.CharField(max_length=128, blank=True, null=True)
    encoded_by = models.CharField(max_length=128, blank=True, null=True)
    encoded_on = models.DateTimeField(blank=True, null=True)
    confirmation_encoded_on = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "tbl_production_encode"


# ==========================================
# 8. RAW MATERIALS
# ==========================================

class tbl_raw_material_list(models.Model):
    id = models.AutoField(primary_key=True)
    rm_code = models.CharField(max_length=100, unique=True, blank=True, null=True)

    class Meta:
        db_table = "tbl_raw_material_list"

    def __str__(self):
        return self.rm_code or str(self.id)


class tbl_rm_incoming(models.Model):
    id = models.AutoField(primary_key=True)
    date = models.DateField(blank=True, null=True)
    material_code = models.CharField(max_length=100, unique=True, blank=True, null=True)
    note = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "tbl_rm_incoming"

    def __str__(self):
        return self.material_code or str(self.id)