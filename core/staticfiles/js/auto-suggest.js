document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.ts-select').forEach((el) => {
        new TomSelect(el, {
            selectOnTab: true,
            create: false,
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