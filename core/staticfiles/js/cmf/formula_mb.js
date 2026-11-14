/**
 * formula_mb.js
 * Logic specific to Masterbatch (MB) Formula.
 * - Calculation: [Supposed Total Weight] * ([Row %] / 100) = [Row Weight]
 * - Row locking: a row is only editable once every row above it is complete
 *   (material + percent + weight).
 * - Enter key moves to the next field, like Tab.
 * - Every Final % and Weight entry is reformatted to 4 decimal places the
 *   moment you leave the cell — by Tab, Enter, or clicking elsewhere.
 *   Type "5.1" and it becomes "5.1000" as soon as you move on.
 */
(function () {
    const table = document.querySelector('.js-formula-table');
    const supposedWeightInput = document.querySelector('.total-weight-display');
    const summaryTotalPercent = document.querySelector('.js-total-percent-summary');
    const summaryTotalWeight = document.querySelector('.js-total-weight-summary');

    if (!table || !supposedWeightInput) return;

    const form = table.closest('form');
    const DECIMALS = 4;

    // ------------------------------------------------------------------
    // CALCULATIONS
    // ------------------------------------------------------------------

    /**
     * Calculates a single row's weight based on the supposed total weight and the row's percent
     */
    function calculateRowWeight(row) {
        const percentInput = row.querySelector('.js-percent-input');
        const weightInput = row.querySelector('.js-weight-input');
        const masterWeight = parseFloat(supposedWeightInput.value) || 0;

        // No percent typed in this row -> no weight (don't fill empty rows with 0.0000)
        if (percentInput.value.trim() === '') {
            weightInput.value = "";
            return;
        }

        if (masterWeight > 0) {
            const percent = parseFloat(percentInput.value) || 0;
            weightInput.value = (masterWeight * (percent / 100)).toFixed(DECIMALS);
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

        if (summaryTotalPercent) {
            summaryTotalPercent.value = totalPct.toFixed(DECIMALS);
            // Visual Validation: Red if not 100%
            summaryTotalPercent.style.color = (totalPct.toFixed(DECIMALS) !== (100).toFixed(DECIMALS)) ? "#dc3545" : "#198754";
        }

        if (summaryTotalWeight) {
            summaryTotalWeight.value = totalWgt.toFixed(DECIMALS);
            // Visual Validation: Red if doesn't match supposed weight
            const masterWgt = parseFloat(supposedWeightInput.value) || 0;
            summaryTotalWeight.style.color = (totalWgt.toFixed(DECIMALS) !== masterWgt.toFixed(DECIMALS)) ? "#dc3545" : "#198754";
        }
    }

    /**
     * Rewrites a field's own displayed value to a fixed number of decimals,
     * e.g. "5.1" -> "5.1000". Returns true if it actually changed something,
     * so callers know whether dependent totals need recomputing.
     */
    function formatEntry(input) {
        const raw = input.value.trim();
        if (raw === '') return false;

        const num = parseFloat(raw);
        if (isNaN(num)) return false;

        const formatted = num.toFixed(DECIMALS);
        if (input.value === formatted) return false;

        input.value = formatted;
        return true;
    }

    /**
     * Formats whichever of Final % / Weight the given element is, and
     * refreshes the row weight / summary totals that depend on it. Called
     * from both the blur/focusout handler and the Enter-key handler, so
     * the 4-decimal formatting is guaranteed regardless of how the user
     * leaves the cell.
     */
    function commitEntry(el) {
        if (!el || !el.classList) return;
        const isPercent = el.classList.contains('js-percent-input');
        const isWeight = el.classList.contains('js-weight-input');
        if (!isPercent && !isWeight) return;

        formatEntry(el);

        if (isPercent) calculateRowWeight(el.closest('tr'));
        updateSummaryTotals();
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
     * Row N is editable only if every row above it is complete
     * (material + percent + weight). Row 1 is always editable.
     */
    function updateRowLocks() {
        let previousRowsComplete = true;

        getRows().forEach(row => {
            setRowLocked(row, !previousRowsComplete);
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

        // Plain inputs — format Final % / Weight to 4 decimals immediately,
        // don't wait on the browser's own blur/focusout to get around to it.
        if (target.tagName !== 'INPUT') return;
        e.preventDefault();
        commitEntry(target);
        focusNextField(target);
    }, true);

    // ------------------------------------------------------------------
    // EVENTS
    // ------------------------------------------------------------------

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

    // EVENT 5: Format to 4 decimals the moment the user leaves the cell by
    // Tab or by clicking elsewhere. ('focusout' bubbles, unlike 'blur', so
    // this is delegated on the table like the other listeners.) Enter is
    // covered explicitly above, since preventDefault() there stops it from
    // ever reaching a native Tab-like blur in some browsers.
    table.addEventListener('focusout', function (e) {
        commitEntry(e.target);
    });

    // Run once on page load (in case of existing data)
    updateSummaryTotals();
    updateRowLocks();

})();