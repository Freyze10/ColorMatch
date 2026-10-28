document.addEventListener('DOMContentLoaded', function () {

    // --- DOM ELEMENTS ---
    const refreshBtn = document.getElementById('refreshBtn');
    const searchInput = document.getElementById('recordSearchInput');
    const searchFieldSelect = document.getElementById('searchFieldSelect');
    const recordCounter = document.getElementById('recordCounter');
    const contextMenu = document.getElementById('customContextMenu');
    const menuTitle = document.getElementById('contextMenuTitle');
    const tableEl = document.querySelector('.rs-records-table');

    if (!tableEl) return;

    // --- DATATABLE (server-side) ---
    const table = new DataTable(tableEl, {
        serverSide: true,
        processing: true,
        searching: false,
        pageLength: 1000,
        order: [[1, 'desc']], // Order by RS No. descending
        layout: {
            topStart: null,
            topEnd: null,
            bottomStart: 'paging',
            bottomEnd: null
        },
        language: {
            emptyTable: "No RS records found in database.",
            zeroRecords: "No matching RS records found."
        },
        ajax: {
            url: '/cmf/rs-records/data/',
            data: function (d) {
                d.search_col = searchFieldSelect ? searchFieldSelect.value : 'all';
                d.search_term = searchInput ? searchInput.value.trim() : '';
            }
        },
        columns: [
            { data: 'id', visible: false, searchable: false },
            { data: 'rs_no', className: 'ps-3 fw-bold' },
            { data: 'customer' },
            { data: 'cm_no' },
            { data: 'product_code' },
            { data: 'salesman' },
            { data: 'approved_by' },
            {
                data: 'status',
                className: 'pe-3',
                render: function (val) {
                    const isCompleted = val === 'Completed';
                    const cls = isCompleted
                        ? 'bg-success-subtle text-success border border-success'
                        : 'bg-warning-subtle text-warning-emphasis border border-warning';
                    return `<span class="badge ${cls}">${val || 'Pending'}</span>`;
                }
            }
        ],
        drawCallback: function () {
            const info = this.api().page.info();
            if (recordCounter) recordCounter.textContent = `Showing ${info.recordsDisplay} records`;
        }
    });

    // --- PAGE LENGTH ---
    const pageLengthSelect = document.getElementById('pageLengthSelect');
    if (pageLengthSelect) {
        pageLengthSelect.addEventListener('change', function () {
            table.page.len(parseInt(this.value, 10)).draw('page');
        });
    }

    // --- SEARCH WITH DEBOUNCE ---
    let searchDebounce;
    function reloadTable() {
        table.ajax.reload();
    }

    if (searchFieldSelect) searchFieldSelect.addEventListener('change', reloadTable);
    if (searchInput) {
        searchInput.addEventListener('input', function () {
            clearTimeout(searchDebounce);
            searchDebounce = setTimeout(reloadTable, 300);
        });
    }
    if (refreshBtn) refreshBtn.addEventListener('click', () => table.ajax.reload(null, false));

    // --- DOUBLE CLICK TO OPEN RS ENTRY ---
    const recordsTbody = tableEl.querySelector('tbody');
    if (recordsTbody) {
        recordsTbody.addEventListener('dblclick', function (e) {
            const tr = e.target.closest('tr');
            if (!tr || tr.closest('thead')) return;

            const rowData = table.row(tr).data();
            if (rowData && rowData.id) {
                window.location.href = `/cmf/rs-entry/?no=${encodeURIComponent(rowData.id)}`;
            }
        });
    }

    // --- CONTEXT MENU (Right Click) ---
    if (recordsTbody && contextMenu) {
        recordsTbody.addEventListener('contextmenu', function (e) {
            const tr = e.target.closest('tr');
            if (!tr) return;

            const rowData = table.row(tr).data();
            if (!rowData) return;
            e.preventDefault();

            const recordId = rowData.id;
            const rsNo = rowData.rs_no;

            menuTitle.innerText = rsNo || `RS #${recordId}`;

            const linkRsEntry = document.getElementById('linkRsEntry');
            const linkPendingCompleted = document.getElementById('linkPendingCompleted');

            // 1. Go to RS Entry
            linkRsEntry.href = `/cmf/rs-entry/?no=${encodeURIComponent(recordId)}`;
            // 2. Go to Pending/Completed
            linkPendingCompleted.href = `/cmf/pending-completed/?no=${encodeURIComponent(recordId)}&type=rs`;

            contextMenu.style.top = `${e.clientY}px`;
            contextMenu.style.left = `${e.clientX}px`;
            contextMenu.style.display = 'block';
        });

        document.addEventListener('click', () => contextMenu.style.display = 'none');
    }
});