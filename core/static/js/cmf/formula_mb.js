/**
 * formula_mb.js
 * Logic specific to Masterbatch (MB) Formula.
 * Calculation: [Supposed Total Weight] * ([Row %] / 100) = [Row Weight]
 */
(function () {
    const table = document.querySelector('.js-formula-table');
    const supposedWeightInput = document.querySelector('.total-weight-display');
    const summaryTotalPercent = document.querySelector('.js-total-percent-summary');
    const summaryTotalWeight = document.querySelector('.js-total-weight-summary');

    if (!table || !supposedWeightInput) return;

    const form = table.closest('form');
    /**
     * Calculates a single row's weight based on the supposed total weight and the row's percent
     */
    function calculateRowWeight(row) {
        const percentInput = row.querySelector('.js-percent-input');
        const weightInput = row.querySelector('.js-weight-input');
        const masterWeight = parseFloat(supposedWeightInput.value) || 0;
        const percent = parseFloat(percentInput.value) || 0;

        if (masterWeight > 0 && percent >= 0) {
            const calculatedWeight = masterWeight * (percent / 100);
            weightInput.value = calculatedWeight.toFixed(6);
        } else if (percent === 0) {
            weightInput.value = "";
        }
    }

    /**
     * Sums up all percentages and weights to update the footer summary
     */
    function updateSummaryTotals() {
        let totalPct = 0;
        let totalWgt = 0;

        table.querySelectorAll('.js-percent-input').forEach(input => {
            totalPct += parseFloat(input.value) || 0;
        });

        table.querySelectorAll('.js-weight-input').forEach(input => {
            totalWgt += parseFloat(input.value) || 0;
        });

        // Update Footer UI
        if (summaryTotalPercent) {
            summaryTotalPercent.value = totalPct.toFixed(6);
            // Visual Validation: Red if not 100%
            summaryTotalPercent.style.color = (totalPct.toFixed(2) !== "100.00") ? "#dc3545" : "#198754";
        }

        if (summaryTotalWeight) {
            summaryTotalWeight.value = totalWgt.toFixed(6);
            // Visual Validation: Red if doesn't match supposed weight
            const masterWgt = parseFloat(supposedWeightInput.value) || 0;
            summaryTotalWeight.style.color = (totalWgt.toFixed(2) !== masterWgt.toFixed(2)) ? "#dc3545" : "#198754";
        }
    }
    // ------------------------------------------------------------------
    // SEQUENTIAL ROW LOCKING
    // ------------------------------------------------------------------
 
    const getRows = () => Array.from(table.querySelectorAll('tbody tr'));
 
    function getRowValues(row) {
        return [
            row.querySelector('.js-material-select')?.value.trim() || '',
            row.querySelector('.js-percent-input')?.value.trim() || '',
            row.querySelector('.js-weight-input')?.value.trim() || ''
        ];
    }
 
    const isRowComplete = (row) => getRowValues(row).every(v => v !== '');
    const rowHasData = (row) => getRowValues(row).some(v => v !== '');
 
    function setRowLocked(row, locked) {
        if (row.dataset.locked === String(locked)) return; // nothing changed
        row.dataset.locked = String(locked);
 
        const select = row.querySelector('.js-material-select');
        if (select) {
            if (select.tomselect) {
                locked ? select.tomselect.disable() : select.tomselect.enable();
            } else {
                select.disabled = locked;
            }
        }
 
        row.querySelectorAll('.js-percent-input, .js-weight-input').forEach(input => {
            input.readOnly = locked;
            input.style.backgroundColor = locked ? '#f8f9fa' : '';
            input.style.cursor = locked ? 'not-allowed' : '';
            if (locked) input.tabIndex = -1;
            else input.removeAttribute('tabindex');
        });
    }
 
    /**
     * Row N is editable only if all rows above it are complete
     * (or if it already contains data, so nothing gets stuck locked).
     */
    function updateRowLocks() {
        let previousRowsComplete = true;
 
        getRows().forEach(row => {
            setRowLocked(row, !previousRowsComplete && !rowHasData(row));
            previousRowsComplete = previousRowsComplete && isRowComplete(row);
        });
    }

    // ------------------------------------------------------------------
    // ENTER KEY = TAB
    // ------------------------------------------------------------------
 
    /**
     * Ordered list of fields the cursor can land on.
     * Tom Select fields are represented by their original <select>.
     */
    function getFocusableFields() {
        return Array.from(form.querySelectorAll('input, select, textarea')).filter(el => {
            if (el.type === 'hidden' || el.disabled) return false;
            if (el.closest('.ts-wrapper')) return false;   // Tom Select's internal search input
            if (el.tomselect) return true;                 // Tom Select field
            return !el.readOnly && el.tabIndex >= 0;
        });
    }
 
    function focusNextField(current) {
        const fields = getFocusableFields();
        const next = fields[fields.indexOf(current) + 1];
        if (!next) return;
 
        if (next.tomselect) {
            next.tomselect.focus();
        } else {
            next.focus();
            if (typeof next.select === 'function') next.select();
        }
    }
 
    // Capture phase so this runs before Tom Select handles the key
    form.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
 
        const target = e.target;
        if (target.tagName === 'TEXTAREA' || target.tagName === 'BUTTON') return;
 
        // Material dropdowns in the table
        const wrapper = target.closest('.ts-wrapper');
        if (wrapper) {
            const select = wrapper.previousElementSibling;
            if (!select || !select.classList.contains('js-material-select')) return; // leave other dropdowns alone
 
            const ts = select.tomselect;
            if (ts.isOpen) {
                // Let Tom Select pick the highlighted option first, then move on
                setTimeout(() => { if (ts.getValue()) focusNextField(select); }, 0);
            } else {
                e.preventDefault();
                focusNextField(select);
            }
            return;
        }
 
        // Plain inputs
        if (target.tagName !== 'INPUT') return;
        e.preventDefault();
        focusNextField(target);
    }, true);

    // EVENT 1: User changes the Supposed Total Weight
    supposedWeightInput.addEventListener('input', function () {
        // When the master weight changes, re-calculate EVERY row's weight
        table.querySelectorAll('tbody tr').forEach(row => calculateRowWeight(row));
        updateSummaryTotals();
        updateRowLocks();
    });
 
    // EVENT 2: User changes a Percentage in a row
    table.addEventListener('input', function (e) {
        if (e.target.classList.contains('js-percent-input')) {
            calculateRowWeight(e.target.closest('tr'));
            updateSummaryTotals();
        }
 
        // EVENT 3: Manual weight edit
        if (e.target.classList.contains('js-weight-input')) {
            updateSummaryTotals();
        }
 
        updateRowLocks();
    });
 
    // EVENT 4: Material picked/cleared (Tom Select fires change on the original select)
    table.addEventListener('change', updateRowLocks);
 
    // Run once on page load (in case of existing data)
    updateSummaryTotals();
    updateRowLocks();

})();