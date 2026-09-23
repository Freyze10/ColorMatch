document.addEventListener('DOMContentLoaded', function () {
    const recordsTbody = document.getElementById('recordsTbody');
    const modalElement = document.getElementById('cmfDetailModal');
    if (!modalElement || !recordsTbody) return;

    const modalTableBody = document.getElementById('modalTableBody');
    const bsModal = new bootstrap.Modal(modalElement);

    // Remember the last-opened record so we can refresh the modal in place
    // after a final-status toggle, instead of forcing a full page reload.
    let currentRecordId = null;
    let currentMode = null;

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let cookie of cookies) {
                cookie = cookie.trim();
                if (cookie.startsWith(name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
    const csrftoken = getCookie('csrftoken');

    async function loadModalContent(recordId, mode) {
        currentRecordId = recordId;
        currentMode = mode;

        modalTableBody.innerHTML = '<tr><td colspan="7" class="text-center py-5"><div class="spinner-border text-teal spinner-border-sm"></div> Fetching data...</td></tr>';

        try {
            const url = mode === 'rs'
                ? `/cmf/rs-records/${encodeURIComponent(recordId)}/`
                : `/cmf/records/${encodeURIComponent(recordId)}/`;

            const response = await fetch(url);
            const htmlSnippet = await response.text();
            modalTableBody.innerHTML = htmlSnippet;
        } catch (error) {
            console.error('Fetch Error:', error);
            modalTableBody.innerHTML = '<tr><td colspan="7" class="text-center py-4 text-danger">Error fetching database records.</td></tr>';
        }
    }

    // --- 1. DOUBLE CLICK TRIGGER: Background Fetch (No Redirect) ---
    recordsTbody.addEventListener('dblclick', function (e) {
        // 1. Target standard 'tr'
        const tr = e.target.closest('tr');
        if (!tr || tr.closest('thead')) return;

        let recordId = '';

        // 2. Safely get the record ID from DataTables API, or fallback to the first visible cell
        if (typeof table !== 'undefined' && table.row) {
            const rowData = table.row(tr).data();
            if (rowData) recordId = rowData.no || rowData.id;
        } else if (window.DataTable && DataTable.isDataTable('.cmf-records-table')) {
            const rowData = new DataTable.Api('.cmf-records-table').row(tr).data();
            if (rowData) recordId = rowData.no || rowData.id;
        }
        // Fallback: first visible column is CMF No.
        if (!recordId && tr.cells.length > 0) {
            recordId = tr.cells[0].innerText.trim();
        }
        if (!recordId) return;

        // 3. Since this table is CMF-only now, mode is always 'cmf'
        const mode = 'cmf';

        bsModal.show();
        loadModalContent(recordId, mode);
    });

    // --- 2. MODAL INTERACTION LOGIC (Click to Expand / Edit / Mark Final) ---
    modalTableBody.addEventListener('click', function (e) {

        // A. Mark/Unmark Final — check first, stop propagation
        const finalIcon = e.target.closest('.formula-final-icon');
        if (finalIcon) {
            e.stopPropagation();

            const formulaId = finalIcon.dataset.formulaId;
            const formulaType = finalIcon.dataset.formulaType;
            const isFinal = finalIcon.dataset.isFinal === 'true';

            Preline.confirm(
                isFinal ? 'Remove Final Status?' : 'Mark as Final Formula?',
                isFinal
                    ? 'This will unmark this formula as the final version for this record.'
                    : 'This will mark this formula as the final version and unmark any other final formula for this record.',
                'warning',
                async () => {
                    try {
                        const response = await fetch(
                            `/cmf/formula/${formulaType}/${formulaId}/toggle-final/`,
                            {
                                method: 'POST',
                                headers: { 'X-CSRFToken': csrftoken }
                            }
                        );
                        const data = await response.json();

                        if (data.success) {
                            Preline.toast('Final status updated.', 'success');
                            if (currentRecordId && currentMode) {
                                loadModalContent(currentRecordId, currentMode);
                            }
                        } else {
                            Preline.toast(data.error || 'Failed to update final status.', 'error');
                        }
                    } catch (err) {
                        console.error('Toggle Final Error:', err);
                        Preline.toast('Error updating final status.', 'error');
                    }
                }
            );
            return;
        }

        // B. Edit Pen Icon — check next, stop propagation
        const editIcon = e.target.closest('.formula-edit-icon');
        if (editIcon) {
            e.stopPropagation();

            const recordNo = editIcon.dataset.cmNo;
            const formulaId = editIcon.dataset.formulaId;
            const formulaType = editIcon.dataset.formulaType;
            const recordType = editIcon.dataset.recordType || 'cmf';

            const basePath = formulaType === 'mb' ? '/cmf/mb-formula/' : '/cmf/dc-formula/';
            window.location.href = `${basePath}?no=${encodeURIComponent(recordNo)}&formula_id=${encodeURIComponent(formulaId)}&type=${encodeURIComponent(recordType)}`;
            return;
        }

        // C. Toggle Main Parent Row (CMF/RS Record detail)
        const parentRow = e.target.closest('.main-modal-parent-row');
        if (parentRow) {
            const formulaRow = parentRow.nextElementSibling;
            const icon = parentRow.querySelector('.toggle-main-icon');
            const isHidden = formulaRow.classList.toggle('d-none');

            icon.className = isHidden ? 'bi bi-plus-circle-fill toggle-main-icon' : 'bi bi-dash-circle-fill toggle-main-icon text-danger';
            return;
        }

        // D. Toggle Internal Formula Headers (Show Ingredients)
        const formulaHeader = e.target.closest('.formula-header-clickable');
        if (formulaHeader) {
            const ingredientRow = formulaHeader.nextElementSibling;
            ingredientRow.classList.toggle('d-none');

            if (!ingredientRow.classList.contains('d-none')) {
                formulaHeader.style.backgroundColor = 'var(--sidebar-hover-bg)';
            } else {
                formulaHeader.style.backgroundColor = '';
            }
        }
    });
});