
document.addEventListener('DOMContentLoaded', function() {

    // --- 2. DOM ELEMENTS ---
    const cmfInput = document.getElementById('id_cmf_no');
    const saveBtn = document.querySelector('.btn-save');
    const newBtn = document.querySelector('.btn-new');
    const printBtn = document.querySelector('.btn-cmf-print');
    const refreshBtn = document.getElementById('refreshBtn');

    // Works on any page — CMF Entry, RS Entry, or anywhere else these
    // buttons appear — since it finds whichever <form> actually wraps
    // the Save button, instead of relying on a hardcoded form class.
    const entryForm = saveBtn ? saveBtn.closest('form') : null;

    const completedCheckbox = document.getElementById('completed');
    const pendingCheckbox = document.getElementById('pending');
    const modeToggle = document.getElementById('modeToggle');
    const searchInput = document.getElementById('recordSearchInput');
    const searchFieldSelect = document.getElementById('searchFieldSelect');
    const recordsTbody = document.getElementById('recordsTbody');

    // --- 3. NUMERIC INPUT FORMATTING LOGIC ---
    const restrictToNumbers = (e) => {
        const charCode = (e.which) ? e.which : e.keyCode;
        if (charCode !== 46 && charCode > 31 && (charCode < 48 || charCode > 57)) { e.preventDefault(); return false; }
        if (charCode === 46 && e.target.value.indexOf('.') !== -1) { e.preventDefault(); return false; }
        return true;
    };

    document.querySelectorAll('.qty-resin-input, .dosage-input, .est-qty-input').forEach(input => {
        input.addEventListener('keypress', restrictToNumbers);
    });

    // --- POPULATE QTY RESIN ON LOAD ---
    const hiddenField = document.getElementById('id_qty_resin_test_hidden');
    const numInput = document.getElementById('id_qty_resin_num');
    const unitSelect = document.getElementById('id_qty_resin_unit');

    if (hiddenField && hiddenField.value.trim() !== "") {
        // Split the string (e.g., "3 KG" becomes ["3", "KG"])
        const parts = hiddenField.value.trim().split(" ");
        
        if (parts.length === 2) {
            numInput.value = parts[0]; // The number part
            unitSelect.value = parts[1]; // The unit part (KG or G)
        } else {
            // If there's no unit found (legacy data), just put the whole value in the number box
            numInput.value = hiddenField.value;
        }
    }

    // --- 4. BUTTON LISTENERS ---

    if (saveBtn && entryForm) {
    saveBtn.addEventListener('click', function() {
        if (entryForm.reportValidity()) {
            const numInput = document.getElementById('id_qty_resin_num');
            const unitSelect = document.getElementById('id_qty_resin_unit');
            const hiddenField = document.getElementById('id_qty_resin_test_hidden');
            if (numInput && hiddenField) {
                hiddenField.value = `${numInput.value.trim()} ${unitSelect.value}`;
            }

            const hiddenInput = entryForm.querySelector(
                '[name="original_cmf_no"], [name="original_rs_no"], [name="record_no"]'
            );
            const isUpdate = hiddenInput && hiddenInput.value.trim() !== '';

            Preline.confirm(
                isUpdate ? 'Update Entry?' : 'Save Entry?',
                isUpdate
                    ? 'Are you sure you want to update this entry? Existing records will be modified.'
                    : 'Are you sure you want to save this new entry? Please verify all technical specs before confirming.',
                'success',
                () => {
                    showLoader();
                    if (window.myDropzone && window.myDropzone.files.length > 0) {
                        const dataTransfer = new DataTransfer();
                        window.myDropzone.files.forEach(function(file) {
                            dataTransfer.items.add(file);
                        });

                        const hiddenFileInput = document.getElementById('hidden-file-input');
                        if (hiddenFileInput) {
                            hiddenFileInput.files = dataTransfer.files;
                        }
                    }

                    entryForm.submit();
                }
            );
        }
    });
}

    if (newBtn) {
        newBtn.addEventListener('click', function() {
            Preline.confirm(
                'Create New?', 
                'Any unsaved changes on this form will be lost. Do you want to continue?', 
                'warning', 
                () => {
                    // Redirect to clear the form (clears ?no= query string)
                    window.location.href = window.location.pathname; 
                }
            );
        });
    }


    if (printBtn) {
        printBtn.addEventListener('click', function() {
            const cmNo = cmfInput.value.trim();

            if (!cmNo) {
                Preline.confirm(
                    'Missing CMF',
                    'Please enter or load a Color Matching No. before printing.',
                    'danger',
                    () => {}
                );
                return;
            }

            // openPrintPreview(cmNo); for printing using COM/MS Office
            
            // Use the new HTML/CSS print preview method
            // Remove any leftover print iframe from a previous click
            const oldFrame = document.getElementById('cmfPrintFrame');
            if (oldFrame) oldFrame.remove();

            const iframe = document.createElement('iframe');
            iframe.id = 'cmfPrintFrame';
            iframe.style.display = 'none'; // Keep it hidden
            iframe.src = `/cmf/print/${encodeURIComponent(cmNo)}/`;

            iframe.onload = function () {
                // Small delay to ensure styles are loaded
                setTimeout(() => {
                    iframe.contentWindow.focus();
                    iframe.contentWindow.print();
                }, 500);
            };

            document.body.appendChild(iframe);
        });
    }

    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => window.location.reload());
    }

    // --- 5. REUSABLE "OTHERS" TOGGLE LOGIC ---
    const updateOtherInputState = (trigger, input) => {
        if (trigger.checked) {
            input.disabled = false;
            input.required = true;
        } else {
            input.disabled = true;
            input.required = false;
            input.value = ""; 
        }
    };

    document.querySelectorAll('.js-other-container').forEach(container => {
        const trigger = container.querySelector('.js-other-trigger');
        const input = container.querySelector('.js-other-input');
        if (!trigger || !input) return;

        if (trigger.type === 'checkbox') {
            trigger.addEventListener('change', () => updateOtherInputState(trigger, input));
        } else if (trigger.type === 'radio') {
            const groupName = trigger.name;
            document.querySelectorAll(`input[name="${groupName}"]`).forEach(radio => {
                radio.addEventListener('change', () => updateOtherInputState(trigger, input));
            });
        }
        updateOtherInputState(trigger, input);
    });

    // --- 6. TABLE FILTERING LOGIC (Records View) ---
    function applyFilters() {
        if (!recordsTbody) return; // Only run if on the records page
        
        const isRsMode = modeToggle ? modeToggle.checked : false;
        const currentMode = isRsMode ? 'rs' : 'cmf';
        const showCompleted = completedCheckbox?.checked ?? true;
        const showPending = pendingCheckbox?.checked ?? true;
        const searchTerm = searchInput?.value.trim().toLowerCase() ?? '';

        document.querySelectorAll('.record-row').forEach(row => {
            const matchesMode = row.dataset.mode === currentMode;
            const rowStatus = row.dataset.status;
            const matchesStatus = (showCompleted && rowStatus === 'Completed') || (showPending && rowStatus === 'Pending');
            const matchesSearch = searchTerm === '' || row.textContent.toLowerCase().includes(searchTerm);

            row.style.display = (matchesMode && matchesStatus && matchesSearch) ? '' : 'none';
        });
    }

    [completedCheckbox, pendingCheckbox, modeToggle].forEach(el => el?.addEventListener('change', applyFilters));
    searchInput?.addEventListener('input', applyFilters);

    // Initial run
    applyFilters();

    // The function that checks the database
    async function validateCmf(isBlur = false) {
        const query = cmfInput.value.trim();
        if (query.length < 3) return;

        try {
            const response = await fetch(`/check-previous-matching/?cm_no=${query}`);
            const data = await response.json();

            let hasError = false;
            let errorMessage = "";

            // Check for exact duplicate
            if (data.exists_exact) {
                errorMessage = `Error: CMF No. ${query} already exists!`;
                hasError = true;
            } 
            // Check for sequential gap (e.g., missing 'b' when typing 'c')
            else if (data.sequential_error) {
                errorMessage = data.sequential_error;
                hasError = true;
            }

            if (hasError) {
                // 1. Show Toast
                if (typeof Preline.toast === 'function') {
                    Preline.toast(errorMessage, 'error');
                } else {
                    alert(errorMessage);
                }

                // 2. Visual Feedback
                saveBtn.disabled = true;

                // 3. Force Focus back
                setTimeout(() => {
                    cmfInput.focus();
                }, 10);
                return; // STOP HERE
            } else {
                saveBtn.disabled = false;
            }

            // 4. SUGGESTION: Only show if we aren't in a blur event
            if (!isBlur && data.match) {
                Preline.confirm(
                    'Previous Matching Found',
                    `A previous record (${data.latest_cm_no}) exists. Do you want to auto-fill?`,
                    'info',
                    () => {
                        window.location.href = `/cmf/entry/?no=${data.latest_cm_no}&new_no=${query}`;
                    }
                );
            }
        } catch (error) {
            console.error("Error fetching matching data:", error);
        }
    }


    // Debounced version for the 'input' event (real-time typing)
    const handleCmfInput = debounce(() => {
        validateCmf(false);
    }, 800);

    // Attach to the input event
    if (cmfInput) {
        cmfInput.addEventListener('input', handleCmfInput);
        cmfInput.addEventListener('blur', () => {
            validateCmf(true);
        });
    }
});