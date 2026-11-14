/**
 * formula_mb.js
 * Logic specific to Masterbatch (MB) Formula.
 *
 * Total Weight accepts a number OR the word "NONE".
 *
 * NUMBER mode (unchanged):
 *  - Row Weight = Total Weight * (Row % / 100)
 *  - A row unlocks once every row above has material + percent + weight.
 *
 * NONE mode:
 *  - Weight column is never computed and is locked.
 *  - A row unlocks once every row above has material + percent.
 *  - Only the total % (must be 100) is validated on save.
 *
 * Enter moves to the next field like Tab. Final % / Weight are reformatted
 * to fixed decimals when you leave the cell.
 */
(function () {
    const table = document.querySelector('.js-formula-table');
    const supposedWeightInput = document.querySelector('.total-weight-display');
    const summaryTotalPercent = document.querySelector('.js-total-percent-summary');
    const summaryTotalWeight = document.querySelector('.js-total-weight-summary');

    if (!table || !supposedWeightInput) return;

    const form = table.closest('form');
    const DECIMALS = 8;
    const NONE_WORD = 'NONE';

    // ------------------------------------------------------------------
    // TOTAL WEIGHT FIELD: numbers or "NONE"
    // ------------------------------------------------------------------

    const isNoneMode = () =>
        supposedWeightInput.value.trim().toUpperCase() === NONE_WORD;

    // Allowed while typing: digits with one optional dot, or a prefix of "NONE"
    const isAllowedMasterValue = (v) =>
        /^\d*\.?\d*$/.test(v) ||
        (v.length > 0 && NONE_WORD.startsWith(v.toUpperCase()));

    let lastValidMaster = '';

    /** Cleans the field when the user leaves it / presses Enter */
    function normalizeMasterWeight() {
        const v = supposedWeightInput.value.trim();

        if (v.toUpperCase() === NONE_WORD) {
            supposedWeightInput.value = NONE_WORD;
        } else {
            const num = parseFloat(v);
            supposedWeightInput.value = isNaN(num) ? '' : num.toFixed(DECIMALS);
        }
        lastValidMaster = supposedWeightInput.value;
        refreshAll();
    }

    // ------------------------------------------------------------------
    // CALCULATIONS
    // ------------------------------------------------------------------

    function calculateRowWeight(row) {
        const percentInput = row.querySelector('.js-percent-input');
        const weightInput = row.querySelector('.js-weight-input');

        // NONE mode: weights are never computed
        if (isNoneMode()) {
            weightInput.value = '';
            return;
        }

        const masterWeight = parseFloat(supposedWeightInput.value) || 0;

        if (percentInput.value.trim() === '') {
            weightInput.value = '';
            return;
        }

        if (masterWeight > 0) {
            const percent = parseFloat(percentInput.value) || 0;
            weightInput.value = (masterWeight * (percent / 100)).toFixed(DECIMALS);
        }
    }

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
            summaryTotalPercent.style.color =
                (totalPct.toFixed(DECIMALS) !== (100).toFixed(DECIMALS)) ? '#dc3545' : '#198754';
        }

        if (summaryTotalWeight) {
            summaryTotalWeight.value = totalWgt.toFixed(DECIMALS);
            if (isNoneMode()) {
                // No weight validation in NONE mode
                summaryTotalWeight.style.color = '';
            } else {
                const masterWgt = parseFloat(supposedWeightInput.value) || 0;
                summaryTotalWeight.style.color =
                    (totalWgt.toFixed(DECIMALS) !== masterWgt.toFixed(DECIMALS)) ? '#dc3545' : '#198754';
            }
        }
    }

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

    /** Number mode: material + % + weight. NONE mode: material + % only. */
    function isRowComplete(row) {
        const [material, percent, weight] = getRowValues(row);
        if (material === '' || percent === '') return false;
        return isNoneMode() || weight !== '';
    }

    function lockInput(input, locked) {
        if (!input) return;
        input.readOnly = locked; // readOnly (not disabled) so the field still posts
        input.style.backgroundColor = locked ? '#a3a3a3' : '';
        input.style.cursor = locked ? 'not-allowed' : '';
        if (locked) input.tabIndex = -1;
        else input.removeAttribute('tabindex');
    }

    function setRowLocked(row, locked) {
        const none = isNoneMode();
        const state = `${locked}|${none}`;
        if (row.dataset.lockState === state) return; // nothing changed
        row.dataset.lockState = state;

        const select = row.querySelector('.js-material-select');
        if (select) {
            if (select.tomselect) {
                locked ? select.tomselect.disable() : select.tomselect.enable();
            } else {
                select.disabled = locked;
            }
        }

        lockInput(row.querySelector('.js-percent-input'), locked);
        // Weight is always locked in NONE mode, otherwise follows the row lock
        lockInput(row.querySelector('.js-weight-input'), locked || none);
    }

    function updateRowLocks() {
        let previousRowsComplete = true;

        getRows().forEach(row => {
            setRowLocked(row, !previousRowsComplete);
            previousRowsComplete = previousRowsComplete && isRowComplete(row);
        });
    }

    /** Recalculate everything after the total weight changes */
    function refreshAll() {
        getRows().forEach(row => calculateRowWeight(row));
        updateSummaryTotals();
        updateRowLocks();
    }

    // ------------------------------------------------------------------
    // ENTER KEY = TAB
    // ------------------------------------------------------------------

    function getFocusableFields() {
        return Array.from(form.querySelectorAll('input, select, textarea')).filter(el => {
            if (el.type === 'hidden' || el.disabled) return false;
            if (el.closest('.ts-wrapper')) return false;
            if (el.tomselect) return true;
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

    form.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;

        const target = e.target;
        if (target.tagName === 'TEXTAREA' || target.tagName === 'BUTTON') return;

        const wrapper = target.closest('.ts-wrapper');
        if (wrapper) {
            const select = wrapper.previousElementSibling;
            if (!select || !select.classList.contains('js-material-select')) return;

            const ts = select.tomselect;
            if (ts.isOpen) {
                setTimeout(() => { if (ts.getValue()) focusNextField(select); }, 0);
            } else {
                e.preventDefault();
                focusNextField(select);
            }
            return;
        }

        if (target.tagName !== 'INPUT') return;
        e.preventDefault();

        if (target === supposedWeightInput) normalizeMasterWeight();
        else commitEntry(target);

        focusNextField(target);
    }, true);

    // ------------------------------------------------------------------
    // EVENTS
    // ------------------------------------------------------------------

    // EVENT 1: Total Weight typed (numbers or NONE only)
    supposedWeightInput.addEventListener('input', function () {
        const cleaned = supposedWeightInput.value.replace(/\s+/g, '');

        if (isAllowedMasterValue(cleaned)) {
            supposedWeightInput.value = cleaned;
            lastValidMaster = cleaned;
        } else {
            supposedWeightInput.value = lastValidMaster; // reject the keystroke / paste
        }
        refreshAll();
    });

    supposedWeightInput.addEventListener('blur', normalizeMasterWeight);

    // EVENT 2 & 3: Percentage / weight edits in a row
    table.addEventListener('input', function (e) {
        if (e.target.classList.contains('js-percent-input')) {
            calculateRowWeight(e.target.closest('tr'));
            updateSummaryTotals();
        }
        if (e.target.classList.contains('js-weight-input')) {
            updateSummaryTotals();
        }
        updateRowLocks();
    });

    // EVENT 4: Material picked/cleared
    table.addEventListener('change', updateRowLocks);

    // EVENT 5: Format on leaving a cell
    table.addEventListener('focusout', function (e) {
        commitEntry(e.target);
    });

    // ------------------------------------------------------------------
    // INITIAL LOAD (also handles saved records where total weight is none)
    // ------------------------------------------------------------------
    if (isNoneMode()) supposedWeightInput.value = NONE_WORD; // normalizes "None"/"none"
    lastValidMaster = supposedWeightInput.value;
    // ------------------------------------------------------------------
    // WEIGHED BY: required only when Total Weight is numeric
    // ------------------------------------------------------------------
    const weighedByInput = document.getElementById('id_dc_weighed_by');
    const weighedByLabel = weighedByInput
        ? weighedByInput.closest('.row')?.querySelector('label')
        : null;

    function updateWeighedByRequirement() {
        if (!weighedByInput) return;
        const none = isNoneMode();

        weighedByInput.required = !none;
        if (weighedByLabel) weighedByLabel.classList.toggle('required-label', !none);
    }

    updateSummaryTotals();
    updateRowLocks();
})();