document.addEventListener('DOMContentLoaded', function () {

    // --- DOM ELEMENTS ---
    const completedCheckbox = document.getElementById('completed');
    const pendingCheckbox = document.getElementById('pending');
    const refreshBtn = document.getElementById('refreshBtn');
    const searchInput = document.getElementById('recordSearchInput');
    const searchFieldSelect = document.getElementById('searchFieldSelect');
    const recordCounter = document.getElementById('recordCounter');
    const contextMenu = document.getElementById('customContextMenu');
    const menuTitle = document.getElementById('contextMenuTitle');
    const tableEl = document.querySelector('.cmf-records-table');

    if (!tableEl) return;

    // Maps the "logical" column ids used by the status filter (unchanged
    // from before) to the DataTable column POSITION — 0-based, left to
    // right as drawn in <thead>. Must match the <th> order in the template.
    const COL_POS = {
        id: 0, 0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7,
        7: 8, 13: 9, 8: 10, 9: 11, 10: 12, 11: 13, 12: 14
    };
    const COLS_BOTH = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 13];
    const COLS_COMPLETED = [0, 1, 2, 3, 4, 7, 8, 10, 11];
    const COLS_PENDING = [0, 1, 2, 3, 4, 5, 6, 7, 12];

    // --- DATATABLE (server-side) ---
    const table = new DataTable(tableEl, {
        serverSide: true,
        processing: true,
        searching: false,   // we drive filtering ourselves via the row above
        pageLength: 1000,
        order: [[1, 'desc']], // CMF No., descending — same default as before
        // Drop DataTables' own "Showing X to Y of Z entries" text and its
        // built-in page-length control — #recordCounter and #pageLengthSelect
        // (in the Filter Status row) replace them — and put the page-number
        // buttons on the left instead of the default bottom-right.
        layout: {
            topStart: null,
            topEnd: null,
            bottomStart: 'paging',
            bottomEnd: null
        },
        language: {
            emptyTable: "No records found in database.",
            zeroRecords: "No matching records found."
        },
        ajax: {
            url: '/cmf/records/data/',
            data: function (d) {
                d.status_completed = completedCheckbox ? completedCheckbox.checked : true;
                d.status_pending = pendingCheckbox ? pendingCheckbox.checked : true;
                d.search_col = searchFieldSelect ? searchFieldSelect.value : 'all';
                d.search_term = searchInput ? searchInput.value.trim() : '';
            }
        },
        columns: [
            { data: 'id', visible: false, searchable: false },
            { data: 'no', className: 'ps-3 fw-bold' },
            { data: 'customer' },
            { data: 'primary_color' },
            { data: 'description' },
            { data: 'product' },
            { data: 'required_date' },
            { data: 'target_date' },
            { data: 'type' },
            { data: 'colorant_type' },
            { data: 'code' },
            {
                data: 'status',
                render: function (val) {
                    const cls = val === 'Completed'
                        ? 'bg-success-subtle text-success border border-success'
                        : 'bg-warning-subtle text-warning-emphasis border border-warning';
                    return `<span class="badge ${cls}">${val}</span>`;
                }
            },
            { data: 'submitted_date' },
            { data: 'ar_no' },
            { data: 'reason', className: 'pe-3' }
        ],
        drawCallback: function () {
            const info = this.api().page.info();
            if (recordCounter) recordCounter.textContent = `Showing ${info.recordsDisplay} records`;
        }
    });

    // --- COLUMN VISIBILITY (per Completed/Pending checkboxes) ---
    function applyColumnVisibility() {
        const showCompleted = completedCheckbox ? completedCheckbox.checked : true;
        const showPending = pendingCheckbox ? pendingCheckbox.checked : true;
        const activeCols = showCompleted && showPending ? COLS_BOTH : (showCompleted ? COLS_COMPLETED : COLS_PENDING);

        Object.keys(COL_POS).forEach(function (logicalKey) {
            if (logicalKey === 'id') return; // stays hidden regardless of filters
            const key = isNaN(logicalKey) ? logicalKey : parseInt(logicalKey, 10);
            table.column(COL_POS[logicalKey]).visible(activeCols.includes(key));
        });
    }
    applyColumnVisibility();

    // --- PAGE LENGTH (custom select, placed before "Filter Status:") ---
    const pageLengthSelect = document.getElementById('pageLengthSelect');
    if (pageLengthSelect) {
        pageLengthSelect.addEventListener('change', function () {
            table.page.len(parseInt(this.value, 10)).draw('page');
        });
    }

    let searchDebounce;
    function reloadTable() {
        applyColumnVisibility();
        table.ajax.reload();
    }

    if (completedCheckbox) completedCheckbox.addEventListener('change', reloadTable);
    if (pendingCheckbox) pendingCheckbox.addEventListener('change', reloadTable);
    if (searchFieldSelect) searchFieldSelect.addEventListener('change', reloadTable);
    if (searchInput) {
        searchInput.addEventListener('input', function () {
            clearTimeout(searchDebounce);
            searchDebounce = setTimeout(reloadTable, 300);
        });
    }
    if (refreshBtn) refreshBtn.addEventListener('click', () => table.ajax.reload(null, false));

    // --- CONTEXT MENU (Right Click) ---
    // Delegated on the <tbody> element itself (not the rows), so it keeps
    // working after DataTables replaces the rows on every redraw.
    const recordsTbody = tableEl.querySelector('tbody');
    if (recordsTbody && contextMenu) {
        recordsTbody.addEventListener('contextmenu', function (e) {
            const tr = e.target.closest('tr');
            if (!tr) return;
            const rowData = table.row(tr).data();
            if (!rowData) return;
            e.preventDefault();

            const recordId = rowData.id;   // hidden real ID — used for lookups
            const recordNo = rowData.no;   // visible No. — used for display only

            menuTitle.innerText = recordNo;

            const linkCmfEntry = document.getElementById('linkCmfEntry');
            const linkMbFormula = document.getElementById('linkMbFormula');
            const linkDcFormula = document.getElementById('linkDcFormula');
            const linkPendingCompleted = document.getElementById('linkPendingCompleted');

            linkCmfEntry.href = `/cmf/entry/?no=${encodeURIComponent(recordId)}&type=cmf`;
            linkMbFormula.href = `/cmf/mb-formula/?no=${encodeURIComponent(recordId)}&type=cmf`;
            linkDcFormula.href = `/cmf/dc-formula/?no=${encodeURIComponent(recordId)}&type=cmf`;
            linkPendingCompleted.href = `/cmf/pending-completed/?no=${encodeURIComponent(recordId)}&type=cmf`;

            contextMenu.style.top = `${e.clientY}px`;
            contextMenu.style.left = `${e.clientX}px`;
            contextMenu.style.display = 'block';
        });
        document.addEventListener('click', () => contextMenu.style.display = 'none');
    }

    const syncLegacyBtn = document.getElementById('syncLegacyBtn');

    if (syncLegacyBtn) {
        syncLegacyBtn.addEventListener('click', function () {
            Preline.confirm(
                'Sync Legacy Data?',
                'This will mirror the latest formulas and production records from the legacy server. This process may take a minute.',
                'info',
                () => {
                    if (typeof showLoader === 'function') {
                        showLoader();
                    }
                    window.location.href = "/legacy/sync/";
                }
            );
        });
    }

    // --- EXPORT FILTER PANEL ---
    const exportFilterBtn = document.getElementById('exportFilterBtn');
    const exportFilterPanel = document.getElementById('exportFilterPanel');
    const exportDateFrom = document.getElementById('exportDateFrom');
    const exportDateTo = document.getElementById('exportDateTo');
    const exportIncludeRs = document.getElementById('exportIncludeRs');
    const exportExcelBtn = document.getElementById('exportExcelBtn');

    function formatDateMMDDYYYY(date) {
        const mm = String(date.getMonth() + 1).padStart(2, '0');
        const dd = String(date.getDate()).padStart(2, '0');
        const yyyy = date.getFullYear();
        return `${mm}/${dd}/${yyyy}`;
    }

    if (exportFilterBtn && exportFilterPanel) {
        const today = new Date();
        const sevenDaysAgo = new Date();
        sevenDaysAgo.setDate(today.getDate() - 7);

        if (exportDateTo) exportDateTo.value = formatDateMMDDYYYY(today);
        if (exportDateFrom) exportDateFrom.value = formatDateMMDDYYYY(sevenDaysAgo);

        exportFilterBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            exportFilterPanel.classList.toggle('d-none');
        });

        document.addEventListener('click', function (e) {
            if (!exportFilterPanel.contains(e.target) && e.target !== exportFilterBtn) {
                exportFilterPanel.classList.add('d-none');
            }
        });

        exportFilterPanel.addEventListener('click', function (e) {
            e.stopPropagation();
        });
    }

    if (exportExcelBtn) {
        exportExcelBtn.addEventListener('click', function () {
            const dateFrom = exportDateFrom?.value || '';
            const dateTo = exportDateTo?.value || '';
            const includeRs = exportIncludeRs?.checked ?? false;
            const showCompleted = completedCheckbox?.checked ?? true;
            const showPending = pendingCheckbox?.checked ?? true;

            const statusParts = [];
            if (showCompleted) statusParts.push('Completed');
            if (showPending) statusParts.push('Pending');
            const statusText = statusParts.length ? statusParts.join(' & ') : 'No statuses selected';

            const message = `
                Date Range: ${dateFrom} to ${dateTo}
                Status: ${statusText}
                Include RS Data: ${includeRs ? 'Yes' : 'No'}
            `;

            Preline.confirm(
                'Export to Excel?',
                message,
                'success',
                () => {
                    const params = new URLSearchParams();
                    params.set('date_from', dateFrom);
                    params.set('date_to', dateTo);
                    params.set('include_rs', includeRs ? '1' : '0');
                    params.set('completed', showCompleted ? '1' : '0');
                    params.set('pending', showPending ? '1' : '0');

                    window.location.href = `/cmf/records/export/?${params.toString()}`;
                }
            );
        });
    }

});