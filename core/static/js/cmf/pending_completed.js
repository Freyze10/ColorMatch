document.addEventListener('DOMContentLoaded', function () {
    const qtyGivenCol = document.getElementById('qtyGivenCol');
    const qtyGivenInput = document.querySelector('input[name="qty_given"]');
    const setPcCol = document.getElementById('setPcCol');
    const setPcInput = document.querySelector('input[name="set_pc"]');
    const submittedDetailsRow = document.getElementById('submittedDetailsRow');

    // Locate the "Sample" and "Chips" checkboxes dynamically by their label names
    let sampleCheckbox = null;
    let chipsCheckbox = null;

    document.querySelectorAll('input[name="submitted_options"]').forEach(cb => {
        const label = document.querySelector(`label[for="${cb.id}"]`);
        if (label) {
            const text = label.textContent.trim().toLowerCase();
            if (text.includes('sample')) sampleCheckbox = cb;
            if (text.includes('chip')) chipsCheckbox = cb;
        }
    });

    function updateFieldsVisibility() {
        const isSampleChecked = sampleCheckbox ? sampleCheckbox.checked : false;
        const isChipsChecked = chipsCheckbox ? chipsCheckbox.checked : false;

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
    }

    // Attach change listeners
    if (sampleCheckbox) sampleCheckbox.addEventListener('change', updateFieldsVisibility);
    if (chipsCheckbox) chipsCheckbox.addEventListener('change', updateFieldsVisibility);

    // Initial check on page load (in case they are already checked from the database)
    updateFieldsVisibility();

    // --- AUTO-SYNC DATE SUBMITTED TO AR DATE ---
    const dateSubmittedInput = document.querySelector('input[name="date_submitted"]');
    const arDateInput = document.querySelector('input[name="ar_date"]');

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
            const reasonInput = document.getElementById('id_pending_reason');

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
            // 1. Validate Form
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