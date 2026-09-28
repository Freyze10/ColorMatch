document.addEventListener('DOMContentLoaded', function () {
    const qtyGivenCol = document.getElementById('qtyGivenCol');
    const qtyGivenInput = document.querySelector('input[name="qty_given"]');
    const setPcCol = document.getElementById('setPcCol');
    const setPcInput = document.querySelector('input[name="set_pc"]');
    const submittedDetailsRow = document.getElementById('submittedDetailsRow');
    // Target fields for Lot No, AR No, and AR Date
    const lotInput = document.querySelector('input[name="lot_no"]');
    const arNoInput = document.querySelector('input[name="ar_no"]');
    const arDateInput = document.querySelector('input[name="ar_date"]');

    const lotArRow = lotInput ? lotInput.closest('.row') : null;
    const arDateContainer = arDateInput ? (arDateInput.closest('.mb-0') || arDateInput.closest('.mb-3')) : null;

    // Locate the "Sample" and "Chips" checkboxes dynamically by their label names
    let sampleCheckbox = null;
    let chipsCheckbox = null;
    let priceCheckbox = null;

    const submittedCheckboxes = Array.from(document.querySelectorAll('input[name="submitted_options"]'));

    submittedCheckboxes.forEach(cb => {
        const label = document.querySelector(`label[for="${cb.id}"]`);
        if (label) {
            const text = label.textContent.trim().toLowerCase();
            if (text.includes('sample')) sampleCheckbox = cb;
            if (text.includes('chip')) chipsCheckbox = cb;
            if (text.includes('price')) priceCheckbox = cb;
        }
    });

    function updateFieldsVisibility() {
        const isSampleChecked = sampleCheckbox ? sampleCheckbox.checked : false;
        const isChipsChecked = chipsCheckbox ? chipsCheckbox.checked : false;
        const isPriceChecked = priceCheckbox ? priceCheckbox.checked : false;

        const checkedCount = submittedCheckboxes.filter(cb => cb.checked).length;
        // True ONLY if Price is checked and no other option is checked
        const isOnlyPrice = isPriceChecked && (checkedCount === 1);

        // 1. Toggle Qty Given (Sample)
        if (qtyGivenCol && qtyGivenInput) {
            if (isSampleChecked) {
                qtyGivenCol.style.display = '';
                qtyGivenInput.required = true;
                qtyGivenInput.disabled = false;
            } else {
                qtyGivenCol.style.display = 'none';
                qtyGivenInput.required = false;
                qtyGivenInput.disabled = true; // Prevents submitting empty value
            }
        }

        // 2. Toggle Set Pc (Chips)
        if (setPcCol && setPcInput) {
            if (isChipsChecked) {
                setPcCol.style.display = '';
                setPcInput.required = true;
                setPcInput.disabled = false;
            } else {
                setPcCol.style.display = 'none';
                setPcInput.required = false;
                setPcInput.disabled = true;
            }
        }

        // 3. Adjust Column Width (Full-width col-12 if only one is shown, col-6 if both)
        if (isSampleChecked && !isChipsChecked) {
            qtyGivenCol.className = 'col-12';
        } else if (!isSampleChecked && isChipsChecked) {
            setPcCol.className = 'col-12';
        } else {
            qtyGivenCol.className = 'col-6';
            setPcCol.className = 'col-6';
        }

        // 4. Hide entire row if neither is checked
        if (submittedDetailsRow) {
            submittedDetailsRow.style.display = (!isSampleChecked && !isChipsChecked) ? 'none' : '';
        }

        // 5. Toggle Lot No., AR No., and AR Date (Hide ONLY if Price is the sole selected option)
        if (isOnlyPrice) {
            if (lotArRow) lotArRow.style.display = 'none';
            if (arDateContainer) arDateContainer.style.display = 'none';

            if (lotInput) lotInput.required = false;
            if (arNoInput) arNoInput.required = false;
            if (arDateInput) arDateInput.required = false;
        } else {
            if (lotArRow) lotArRow.style.display = '';
            if (arDateContainer) arDateContainer.style.display = '';

            if (lotInput) lotInput.required = true;
            if (arNoInput) arNoInput.required = true;
            if (arDateInput) arDateInput.required = true;
        }
    }

    // Attach change listener to all submitted checkboxes
    submittedCheckboxes.forEach(cb => {
        cb.addEventListener('change', updateFieldsVisibility);
    });

    // Initial check on page load
    updateFieldsVisibility();

    // ==================================================================
    // ENFORCE AT LEAST ONE "SUBMITTED" CHECKBOX IS CHECKED
    // ==================================================================

    function validateSubmittedOptions() {
        if (!submittedCheckboxes.length) return true;
        const anyChecked = submittedCheckboxes.some(cb => cb.checked);
        
        // Setting custom validity on the first checkbox enforces native HTML5 validation
        submittedCheckboxes[0].setCustomValidity(
            anyChecked ? '' : 'Please select at least one submitted option (e.g. Sample, Chips, or Price).'
        );
        return anyChecked;
    }

    submittedCheckboxes.forEach(cb => {
        cb.addEventListener('change', validateSubmittedOptions);
    });

    // Run initial validation check on load
    validateSubmittedOptions();

    // --- AUTO-SYNC DATE SUBMITTED TO AR DATE ---
    const dateSubmittedInput = document.querySelector('input[name="date_submitted"]');

    if (dateSubmittedInput && arDateInput) {
        // If AR Date already has a distinct value loaded from DB, treat as manually edited
        let isArDateUserEdited = Boolean(
            arDateInput.value.trim() !== '' &&
            arDateInput.value.trim() !== dateSubmittedInput.value.trim()
        );

        // Helper to safely set date on Flatpickr or native input
        const setArDateValue = (val) => {
            const fp = arDateInput._flatpickr || arDateInput.closest('.flatpickr-container')?._flatpickr;
            if (fp) {
                fp.setDate(val, false); // false prevents triggering internal change loops
            } else {
                arDateInput.value = val;
            }
        };

        // 1. Sync from Date Submitted -> AR Date while not manually modified
        const handleDateSubmittedChange = function() {
            if (!isArDateUserEdited) {
                setArDateValue(this.value);
            }
        };

        dateSubmittedInput.addEventListener('change', handleDateSubmittedChange);
        dateSubmittedInput.addEventListener('input', handleDateSubmittedChange);

        function setupPendingReasonToggle() {
            const statusPending = document.getElementById('status_pending');
            const statusCompleted = document.getElementById('status_completed');
            const reasonGroup = document.getElementById('pendingReasonGroup');
            const reasonInput = document.getElementById('input[name="pending_reason"]');

            if (!statusPending || !statusCompleted || !reasonGroup) return;

            function handleStatusChange() {
                if (statusCompleted.checked) {
                    reasonGroup.classList.add('d-none');
                    if (reasonInput) {
                        reasonInput.value = '';
                    }
                } else {
                    reasonGroup.classList.remove('d-none');
                }
            }

            statusPending.addEventListener('change', handleStatusChange);
            statusCompleted.addEventListener('change', handleStatusChange);

            handleStatusChange();
        }
        setupPendingReasonToggle();

        // 2. Track when user manually modifies AR Date
        const handleArDateUserChange = function() {
            const val = this.value.trim();
            if (val === '') {
                // If cleared, resume syncing
                isArDateUserEdited = false;
            } else if (val !== dateSubmittedInput.value.trim()) {
                // User set a custom different date: stop syncing
                isArDateUserEdited = true;
            }
        };

        arDateInput.addEventListener('change', handleArDateUserChange);
        arDateInput.addEventListener('input', handleArDateUserChange);
    }

    const saveBtn = document.querySelector('.btn-update');
    const entryForm = saveBtn ? saveBtn.closest('form') : null;
    if (saveBtn && entryForm) {
        saveBtn.addEventListener('click', function() {
            // Guard: Validate that at least one Submitted option is checked
            const hasSubmittedChecked = validateSubmittedOptions();
            if (!hasSubmittedChecked) {
                if (submittedCheckboxes[0]) {
                    submittedCheckboxes[0].reportValidity();
                }
                if (typeof Preline !== 'undefined' && Preline.toast) {
                    Preline.toast('Please select at least one Submitted option.', 'warning');
                }
                return;
            }
            // Validate Form
            if (entryForm.reportValidity()) {

                Preline.confirm(
                    'Update Entry?',
                    'Are you sure you want to update this entry? Existing records will be modified.',
                    'success',
                    () => {
                        entryForm.submit();
                    }
                );
            }
        });
    }
});