
jQuery(document).ready(function($) {
    const table = $('#feedbackTable').DataTable({
        serverSide: true,
        processing: true,
        destroy: true,
        deferRender: true,
        scrollY: '58vh',
        scrollCollapse: true,
        ajax: {
            url: "/feedback/data/",
            type: "GET",
            data: function(d) {
                d.column_choice = $('#filterFeedbackCol').val();
            }
        },
        columns: [
            { data: "feedback_no", className: "ps-3" },
            {
                data: "matching_no",
                className: "fw-bold",
                render: function(data, type, row) {
                    const colorClass = row.mode === 'rs' ? 'text-primary' : 'text-teal';
                    return `<span class="${colorClass}">${data}</span>`;
                }
            },
            { data: "customer" },
            { data: "prod_code", render: data => `<code>${data}</code>` },
            { data: "color_desc" },
            { data: "finished_prod" },
            { data: "required_date" },
            { data: "due_date" },
            { data: "type" },
            {
                data: "status",
                render: function(data) {
                    const statusLower = (data || '').toLowerCase();
                    let cls = "bg-light text-dark border-secondary";

                    if (statusLower === 'pending') cls = "bg-warning-subtle text-warning border-warning";
                    else if (statusLower === 'rematch') cls = "bg-primary-subtle text-primary border-primary";
                    else if (statusLower === 'abandoned') cls = "bg-danger-subtle text-danger border-danger";
                    else if (statusLower === 'ordered') cls = "bg-dark-subtle text-dark border-dark";
                    else if (statusLower.includes('approved')) cls = "bg-success-subtle text-success border-success";
                    else if (statusLower.includes('request')) cls = "bg-info-subtle text-info border-info";

                    return `<span class="badge ${cls} border">${data}</span>`;
                }
            },
            {
                data: "details",
                render: function(data) {
                    return `<div class="text-truncate" style="max-width: 150px;" title="${data || ''}">${data || '---'}</div>`;
                }
            },
            { data: "package_details", className: "pe-3" }
        ],
        // columnDefs: [
        //     { target: 0, visible: false, searchable: false }
        // ],
        dom: 'rtp',
        pageLength: 100,
        ordering: false,
        language: {
            processing: '<div class="d-flex justify-content-center py-4"><div class="spinner-border text-teal"></div></div>',
            paginate: {
                previous: '<i class="bi bi-chevron-left"></i>',
                next: '<i class="bi bi-chevron-right"></i>'
            }
        },
        createdRow: function(row, data) {
            $(row).attr('title', 'Double-click to open feedback entry')
                  .css('cursor', 'pointer')
                  .on('dblclick', function() {
                      window.location.href = `?feedback_no=${data.feedback_no}`;
                  });
        },
        drawCallback: function() {
            const info = this.api().page.info();
            const total = info.recordsTotal.toLocaleString();
            const filtered = info.recordsDisplay.toLocaleString();

            if (info.recordsTotal === info.recordsDisplay) {
                $('#feedbackCountLabel').text(`Showing ${total} records`);
            } else {
                $('#feedbackCountLabel').text(`${filtered} found (from ${total})`);
            }
        }
    });

    const handleSearch = debounce(function(value) {
        table.search(value).draw();
    }, 600);

    $('#feedbackSearch').on('input', function() {
        handleSearch(this.value);
    });

    $('#filterFeedbackCol').on('change', () => table.ajax.reload());
    $('#btnRefreshFeedback').on('click', () => table.ajax.reload());
});