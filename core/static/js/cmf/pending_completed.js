document.addEventListener('DOMContentLoaded', function () {
    const qtyGivenCol = document.getElementById('qtyGivenCol');
    const qtyGivenInput = document.querySelector('input[name="qty_given"]');
    const setPcCol = document.getElementById('setPcCol');
    const setPcInput = document.querySelector('input[name="set_pc"]');
    const submittedDetailsRow = document.getElementById('submittedDetailsRow');

    const remarksInput = document.getElementById('id_submitted_remarks');
    const remarksLabel = document.getElementById('submittedRemarksLabel');
    const noneCheckbox = document.getElementById('opt_none');

    // Target fields for Lot No, AR No, and AR Date
    const lotInput = document.querySelector('input[name="lot_no"]');
    const arNoInput = document.querySelector('input[name="ar_no"]');
    const arDateInput = document.querySelector('input[name="ar_date"]');

    const lotArRow = lotInput ? lotInput.closest('.row') : null;
    const arDateContainer = arDateInput ? (arDateInput.closest('.mb-0') || arDateInput.closest('.mb-3')) : null;

    // Locate the "Sample" and "Chips" checkboxes dynamically by their label names\
    const canonicalCheckboxes = Array.from(document.querySelectorAll('.canonical-option'));
    let sampleCheckbox = null;
    let chipsCheckbox = null;
    let priceCheckbox = null;

    canonicalCheckboxes.forEach(cb => {
        const label = document.querySelector(`label[for="${cb.id}"]`);
        if (label) {
            const text = label.textContent.trim().toLowerCase();
            if (text.includes('sample')) sampleCheckbox = cb;
            if (text.includes('chip')) chipsCheckbox = cb;
            if (text.includes('price')) priceCheckbox = cb;
        }
    });

    // --- MUTUAL EXCLUSIVITY ---
    // If "None" is checked -> uncheck Sample, Chips, Price
    if (noneCheckbox) {
        noneCheckbox.addEventListener('change', function () {
            if (this.checked) {
                canonicalCheckboxes.forEach(cb => cb.checked = false);
            }
            updateFieldsVisibility();
            if (this.checked && remarksInput) {
                setTimeout(() => remarksInput.focus(), 50);
            }
        });
    }

    // If any canonical option is checked -> uncheck "None"
    canonicalCheckboxes.forEach(cb => {
        cb.addEventListener('change', function () {
            if (this.checked && noneCheckbox) {
                noneCheckbox.checked = false;
            }
            updateFieldsVisibility();
        });
    });

    // const submittedCheckboxes = Array.from(document.querySelectorAll('input[name="submitted_options"]'));

    // submittedCheckboxes.forEach(cb => {
    //     const label = document.querySelector(`label[for="${cb.id}"]`);
    //     if (label) {
    //         const text = label.textContent.trim().toLowerCase();
    //         if (text.includes('sample')) sampleCheckbox = cb;
    //         if (text.includes('chip')) chipsCheckbox = cb;
    //         if (text.includes('price')) priceCheckbox = cb;
    //     }
    // });

    function updateFieldsVisibility() {
        const isSampleChecked = sampleCheckbox ? sampleCheckbox.checked : false;
        const isChipsChecked = chipsCheckbox ? chipsCheckbox.checked : false;
        const isPriceChecked = priceCheckbox ? priceCheckbox.checked : false;
        const isNoneChecked = noneCheckbox ? noneCheckbox.checked : false;

        const checkedCanonicalCount = canonicalCheckboxes.filter(cb => cb.checked).length;
        const isOnlyPriceOrNone = isNoneChecked || (isPriceChecked && checkedCanonicalCount === 1);

        // 1. Remarks Field Toggle (Editable + Required ONLY when 'None' is checked)
        if (remarksInput && remarksLabel) {
            if (isNoneChecked) {
                remarksInput.readOnly = false;
                remarksInput.removeAttribute('readonly');
                remarksInput.classList.remove('readonly-gray');
                remarksInput.required = true;
                remarksLabel.classList.add('required-label');
            } else {
                remarksInput.readOnly = true;
                remarksInput.setAttribute('readonly', 'readonly');
                remarksInput.classList.add('readonly-gray');
                remarksInput.required = false;
                remarksLabel.classList.remove('required-label');
                remarksInput.value = '';
            }
        }

        // 2. Qty Given (Sample)
        if (qtyGivenCol && qtyGivenInput) {
            if (isSampleChecked) {
                qtyGivenCol.style.display = '';
                qtyGivenInput.required = true;
                qtyGivenInput.disabled = false;
            } else {
                qtyGivenCol.style.display = 'none';
                qtyGivenInput.required = false;
                qtyGivenInput.disabled = true;
            }
        }

        // 3. Set Pc (Chips)
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

        // 4. Adjust Column Width
        if (isSampleChecked && !isChipsChecked) {
            qtyGivenCol.className = 'col-12';
        } else if (!isSampleChecked && isChipsChecked) {
            setPcCol.className = 'col-12';
        } else {
            qtyGivenCol.className = 'col-6';
            setPcCol.className = 'col-6';
        }

        if (submittedDetailsRow) {
            submittedDetailsRow.style.display = (!isSampleChecked && !isChipsChecked) ? 'none' : '';
        }

        // 5. Hide and relax Lot No / AR No / AR Date if only Price or None is selected
        if (isOnlyPriceOrNone) {
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


    // Initial check on page load
    updateFieldsVisibility();

    // ==================================================================
    // ENFORCE AT LEAST ONE "SUBMITTED" CHECKBOX IS CHECKED
    // ==================================================================

    // Enforce at least one option is chosen (either None or one of the canonical options)
    function validateSubmittedOptions() {
        const isNone = noneCheckbox ? noneCheckbox.checked : false;
        const anyCanonical = canonicalCheckboxes.some(cb => cb.checked);
        const isValid = isNone || anyCanonical;

        if (canonicalCheckboxes.length > 0) {
            canonicalCheckboxes[0].setCustomValidity(
                isValid ? '' : 'Please select at least one Submitted option (or check None).'
            );
        }
        return isValid;
    }

    if (noneCheckbox) noneCheckbox.addEventListener('change', validateSubmittedOptions);
    canonicalCheckboxes.forEach(cb => cb.addEventListener('change', validateSubmittedOptions));

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
        saveBtn.addEventListener('click', function () {
            if (!validateSubmittedOptions()) {
                if (canonicalCheckboxes[0]) canonicalCheckboxes[0].reportValidity();
                if (typeof Preline !== 'undefined' && Preline.toast) {
                    Preline.toast('Please select at least one Submitted option.', 'warning');
                }
                return;
            }

            if (entryForm.reportValidity()) {
                Preline.confirm(
                    'Update Entry?',
                    'Are you sure you want to update this entry? Existing records will be modified.',
                    'success',
                    () => { entryForm.submit(); }
                );
            }
        });
    }
});