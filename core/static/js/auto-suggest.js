document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.ts-select').forEach((el) => {
        const allowCreate = el.dataset.create === 'true'; // Only true if data-create="true" is set

        new TomSelect(el, {
            selectOnTab: true,
            create: allowCreate,        // <-- Dynamic: true for Resin, false for everything else
            createOnBlur: allowCreate,
            refreshThrottle: 0, // <-- Disables the 300ms delay for instant filtering
            openOnFocus: true, 
            controlInput: '<input />',
            controlClass: 'ts-control form-select-sm', 
            render: {
                option: function(data, escape) {
                    return `<div class="extra-small">${escape(data.text)}</div>`;
                },
                item: function(data, escape) {
                    return `<div class="extra-small">${escape(data.text)}</div>`;
                }
            }
        });
    });
});