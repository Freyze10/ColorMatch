document.addEventListener('DOMContentLoaded', function() {

    // --- DOM ELEMENTS ---
    const completedCheckbox = document.getElementById('completed');
    const pendingCheckbox = document.getElementById('pending');
    const refreshBtn = document.getElementById('refreshBtn');
    const searchInput = document.getElementById('recordSearchInput');
    const searchFieldSelect = document.getElementById('searchFieldSelect');
    const recordCounter = document.getElementById('recordCounter');
    const contextMenu = document.getElementById('customContextMenu');
    const menuTitle = document.getElementById('contextMenuTitle');
    const recordsTbody = document.getElementById('recordsTbody');

    const COLS_BOTH = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 13];
    const COLS_COMPLETED = [0, 1, 2, 3, 4, 7, 8, 10, 11];
    const COLS_PENDING = [0, 1, 2, 3, 4, 5, 6, 7, 12];

    function applyFilters() {
        const showCompleted = completedCheckbox ? completedCheckbox.checked : true;
        const showPending = pendingCheckbox ? pendingCheckbox.checked : true;
        const searchTerm = searchInput ? searchInput.value.trim().toLowerCase() : '';
        const searchColIndex = searchFieldSelect ? searchFieldSelect.value : 'all';

        let activeCols = showCompleted && showPending ? COLS_BOTH : (showCompleted ? COLS_COMPLETED : COLS_PENDING);

        for (let i = 0; i <= 12; i++) {
            const isVisible = activeCols.includes(i);
            document.querySelectorAll(`[data-col-index="${i}"]`).forEach(cell => {
                cell.style.display = isVisible ? '' : 'none';
            });
        }

        let visibleCount = 0;
        document.querySelectorAll('.record-row').forEach(row => {
            let matchesStatus = (showCompleted && row.dataset.status === 'Completed') || (showPending && row.dataset.status === 'Pending');
            let matchesSearch = searchTerm === '' || (searchColIndex === 'all' ? row.textContent.toLowerCase().includes(searchTerm) : row.querySelector(`[data-col-index="${searchColIndex}"]`).textContent.toLowerCase().includes(searchTerm));

            if (matchesStatus && matchesSearch) {
                row.style.display = '';
                visibleCount++;
            } else {
                row.style.display = 'none';
            }
        });
        if (recordCounter) recordCounter.textContent = `Showing ${visibleCount} records`;
    }

    // --- CONTEXT MENU (Right Click) ---
    if (recordsTbody && contextMenu) {
        recordsTbody.addEventListener('contextmenu', function (e) {
            const tr = e.target.closest('.record-row');
            if (!tr) return;
            e.preventDefault();

            const recordId = tr.cells[0].innerText.trim();   // hidden real ID — used for lookups
            const recordNo = tr.cells[1].innerText.trim();    // visible No. — used for display only

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

    if (completedCheckbox) completedCheckbox.addEventListener('change', applyFilters);
    if (pendingCheckbox) pendingCheckbox.addEventListener('change', applyFilters);
    if (searchInput) searchInput.addEventListener('input', applyFilters);
    if (searchFieldSelect) searchFieldSelect.addEventListener('change', applyFilters);
    if (refreshBtn) refreshBtn.addEventListener('click', () => window.location.reload());

    applyFilters();

    const syncLegacyBtn = document.getElementById('syncLegacyBtn');

    if (syncLegacyBtn) {
        syncLegacyBtn.addEventListener('click', function() {
            Preline.confirm(
                'Sync Legacy Data?',
                'This will mirror the latest formulas and production records from the legacy server. This process may take a minute.',
                'info',
                () => {
                    // 1. Show the global loading cubes (from our previous step)
                    if (typeof showLoader === 'function') {
                        showLoader();
                    }
                    
                    // 2. Redirect to the sync action URL
                    // Note: Ensure this URL matches your urls.py path
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
        // Set defaults: To = today, From = 7 days ago
        const today = new Date();
        const sevenDaysAgo = new Date();
        sevenDaysAgo.setDate(today.getDate() - 7);

        if (exportDateTo) exportDateTo.value = formatDateMMDDYYYY(today);
        if (exportDateFrom) exportDateFrom.value = formatDateMMDDYYYY(sevenDaysAgo);

        exportFilterBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            exportFilterPanel.classList.toggle('d-none');
        });

        // Close the panel when clicking anywhere outside it
        document.addEventListener('click', function (e) {
            if (!exportFilterPanel.contains(e.target) && e.target !== exportFilterBtn) {
                exportFilterPanel.classList.add('d-none');
            }
        });

        // Prevent clicks inside the panel (e.g. on the date pickers) from closing it
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