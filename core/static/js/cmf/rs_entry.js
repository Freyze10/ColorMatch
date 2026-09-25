document.addEventListener('DOMContentLoaded', function () {
    const cmSelect = document.querySelector('select[name="cm_no"]');
    const productCodeInput = document.querySelector('input[name="product_code"]');
    const saveBtn = document.querySelector('.btn-save');
    const newBtn = document.querySelector('.btn-new');
    const entryForm = saveBtn ? saveBtn.closest('form') : null;

    /**
     * AJAX function to fetch the final product code of the selected CMF
     */
    async function fetchCmfFinalCode(cmNo) {
        if (!cmNo) {
            if (productCodeInput) productCodeInput.value = '';
            return;
        }

        if (productCodeInput) {
            productCodeInput.value = 'Fetching...';
        }

        try {
            const response = await fetch(`/cmf/rs/get-final-code/?cm_no=${encodeURIComponent(cmNo)}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();

            if (productCodeInput) {
                productCodeInput.value = data.product_code || '';
            }

            // --- Toast Notifications ---
            if (typeof Preline !== 'undefined' && typeof Preline.toast === 'function') {
                if (data.product_code) {
                    Preline.toast(`Product code loaded: ${data.product_code}`, 'success');
                } else {
                    Preline.toast(`No final product code found for CMF #${cmNo}.`, 'info');
                }
            }
        } catch (error) {
            if (productCodeInput) productCodeInput.value = '';
            if (typeof Preline !== 'undefined' && typeof Preline.toast === 'function') {
                Preline.toast('Error fetching product code.', 'danger');
            }
        }
    }

    /**
     * Listen to TomSelect change event
     */
    if (cmSelect) {
        let attempts = 0;
        const pollTomSelect = setInterval(() => {
            attempts++;
            if (cmSelect.tomselect) {
                clearInterval(pollTomSelect);

                // Listen to TomSelect's custom change event
                cmSelect.tomselect.on('change', function (value) {
                    fetchCmfFinalCode(value);
                });
            } else if (attempts > 50) {
                // Fallback for native select if TomSelect is not used
                clearInterval(pollTomSelect);
                cmSelect.addEventListener('change', function () {
                    fetchCmfFinalCode(this.value);
                });
            }
        }, 100);
    }

    // --- BUTTON LISTENERS ---
    if (saveBtn && entryForm) {
        saveBtn.addEventListener('click', function () {
            if (entryForm.reportValidity()) {
                const hiddenInput = entryForm.querySelector('[name="original_rs_no"]');
                const isUpdate = hiddenInput && hiddenInput.value.trim() !== '';

                if (window.Preline && typeof Preline.confirm === 'function') {
                    Preline.confirm(
                        isUpdate ? 'Update RS Entry?' : 'Save RS Entry?',
                        isUpdate
                            ? 'Are you sure you want to update this RS entry?'
                            : 'Are you sure you want to save this new RS entry?',
                        'success',
                        () => entryForm.submit()
                    );
                }
            }
        });
    }

    if (newBtn) {
        newBtn.addEventListener('click', function () {
            window.location.href = window.location.pathname;
        });
    }
});