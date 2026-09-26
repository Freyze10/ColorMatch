/**
 * formula_dc.js
 * Logic specific to Dry Color (DC) Formula.
 * Load AFTER formula.js (it applies the version-column locking this file builds on).
 *
 * - Row locking: row N+1 becomes editable once row N has a material AND a value in
 *   the version being entered (the right-most column formula.js left editable:
 *   V1 for a new formula, next empty version when updating).
 *   Rows that already have data stay editable.
 * - Enter key moves to the next field, like Tab.
 * - Every version-value entry is reformatted to 4 decimal places the moment
 *   you leave the cell — by Tab, Enter, or clicking elsewhere. Type "5.1"
 *   and it becomes "5.1000" as soon as you move on.
 */
(function () {
    const table = document.querySelector('.js-formula-table');
    const form = document.querySelector('.js-dc-formula');

    if (!table || !form) return;

    const DECIMALS = 4;

    // Version currently being entered. Read once on load, before any row gets locked.
    const openVersions = Array.from(table.querySelectorAll('.js-version-value'))
        .filter(input => !input.readOnly)
        .map(input => parseInt(input.dataset.version));
    const activeVersion = openVersions.length ? Math.max(...openVersions) : 1;

    // ------------------------------------------------------------------
    // DOSAGE -> TOTAL WEIGHT REAL-TIME SYNC
    // ------------------------------------------------------------------

    const dosageInput = form.querySelector('#id_dc_dosage') || form.querySelector('[name="dosage"]');
    const totalWeightInput = form.querySelector('.total-weight-display') || form.querySelector('[name="total_weight"]');

    function syncDosageToTotalWeight() {
        if (!dosageInput || !totalWeightInput) return;

        const raw = dosageInput.value.trim();

        // Allows any positive number: whole numbers, decimals of any length, or starting with a dot (e.g., "2", "2.5", ".5", "0.12345")
        // Blocks letters, symbols (%), negatives, and multiple dots
        const isNumeric = /^\d*\.?\d*$/.test(raw) && raw !== '' && raw !== '.';

        if (isNumeric) {
            const num = parseFloat(raw);
            if (!isNaN(num) && num > 0) {
                // Keep Total Weight formatted to 4 decimals
                totalWeightInput.value = num.toFixed(DECIMALS);
                totalWeightInput.dispatchEvent(new Event('input', { bubbles: true }));
                return;
            }
        }

        // If it contains non-numeric text (e.g. "2%", letters, symbols) or is empty,
        // do not display it in Total Weight.
        totalWeightInput.value = '';
        totalWeightInput.dispatchEvent(new Event('input', { bubbles: true }));
    }

    if (dosageInput && totalWeightInput) {
        // Sync in real-time as the user types or leaves the field
        dosageInput.addEventListener('input', syncDosageToTotalWeight);
        dosageInput.addEventListener('change', syncDosageToTotalWeight);
        dosageInput.addEventListener('blur', syncDosageToTotalWeight);

        // On initial page load for new formulas: clean up if dosage note had non-numeric text
        const isUpdate = form.querySelector('[name="formula_id"]')?.value.trim() !== '';
        if (!isUpdate && dosageInput.value.trim() !== '') {
            syncDosageToTotalWeight();
        }
    }

    // ------------------------------------------------------------------
    // 4-DECIMAL FORMATTING
    // ------------------------------------------------------------------

    /**
     * Rewrites a field's own displayed value to a fixed number of decimals,
     * e.g. "5.1" -> "5.1000". Returns true if it actually changed something.
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
     * Formats a version-value cell and lets formula.js's column-total
     * listener know something changed, so the Total row picks it up.
     * Called from both the blur/focusout handler and the Enter-key
     * handler, so formatting is guaranteed regardless of how the user
     * leaves the cell.
     */
    function commitEntry(el) {
        if (!el || !el.classList || !el.classList.contains('js-version-value')) return;
        if (formatEntry(el)) {
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }

    // ------------------------------------------------------------------
    // SEQUENTIAL ROW LOCKING
    // ------------------------------------------------------------------

    const getRows = () => Array.from(table.querySelectorAll('tbody tr'));
    const getMaterial = (row) => row.querySelector('.js-material-select')?.value.trim() || '';
    const getVersionInputs = (row) => Array.from(row.querySelectorAll('.js-version-value'));
    const hasAnyValue = (row) => getVersionInputs(row).some(input => input.value.trim() !== '');

    function isRowComplete(row) {
        const active = row.querySelector(`.js-version-value[data-version="${activeVersion}"]`);
        return getMaterial(row) !== '' && !!active && active.value.trim() !== '';
    }

    const rowHasData = (row) => getMaterial(row) !== '' || hasAnyValue(row);

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

        getVersionInputs(row).forEach(input => {
            // Columns beyond the active version stay locked no matter what
            const lock = locked || parseInt(input.dataset.version) > activeVersion;
            input.readOnly = lock;
            input.style.backgroundColor = lock ? '#f8f9fa' : '';
            input.style.cursor = lock ? 'not-allowed' : '';
            if (lock) input.tabIndex = -1;
            else input.removeAttribute('tabindex');
        });
    }

    /**
     * Row N is editable only if the row above it is complete
     * (or if it already contains data, so nothing gets stuck locked).
     */
    function updateRowLocks() {
        let previousRowComplete = true;

        getRows().forEach(row => {
            setRowLocked(row, !previousRowComplete && !rowHasData(row));
            previousRowComplete = isRowComplete(row);
        });
    }

    table.addEventListener('input', updateRowLocks);
    table.addEventListener('change', updateRowLocks); // Tom Select fires change on the original select

    // Format to 4 decimals the moment the user leaves the cell by Tab or by
    // clicking elsewhere. ('focusout' bubbles, unlike 'blur', so this is
    // delegated on the table like the other listeners.) Enter is covered
    // explicitly below, since preventDefault() there stops it from ever
    // reaching a native Tab-like blur in some browsers.
    table.addEventListener('focusout', function (e) {
        commitEntry(e.target);
    });

    // Locked (disabled) material selects are not posted by the browser,
    // so re-enable them right before the form is submitted.
    const nativeSubmit = form.submit;
    form.submit = function () {
        table.querySelectorAll('[disabled]').forEach(el => { el.disabled = false; });
        nativeSubmit.call(form);
    };

    // formula.js marks the first version column (V1) as required whenever a material is picked.
    // Before validation runs, require a value only in the active version, and only if
    // the row has no value at all yet.
    document.addEventListener('click', function (e) {
        if (!e.target.closest('.btn-save-formula')) return;

        getRows().forEach(row => {
            const needsValue = getMaterial(row) !== '' && !hasAnyValue(row);
            getVersionInputs(row).forEach(input => {
                input.required = needsValue && parseInt(input.dataset.version) === activeVersion;
            });
        });
    }, true);

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

        // Plain inputs — format the version value to 4 decimals immediately,
        // don't wait on the browser's own blur/focusout to get around to it.
        if (target.tagName !== 'INPUT') return;
        e.preventDefault();
        commitEntry(target);
        focusNextField(target);
    }, true);

    // Run once on page load (in case of existing data)
    updateRowLocks();

})();