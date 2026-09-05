(function () {
    // --- 1. TOM SELECT INITIALIZATION ---
    document.querySelectorAll('.ts-select-table').forEach((el) => {
        if (el.tomselect) return; 
        
        new TomSelect(el, {
            selectOnTab: true,
            create: false,
            placeholder: "Search material...",
            maxOptions: 50,
            dropdownParent: 'body',
            onItemAdd: function () { this.blur(); },
            onInitialize: function() { updateRowRequirement(this.input); },
            onChange: function() {
                updateRowRequirement(this.input);
                calculateFormulaTotals(this.input.closest('.js-formula-table'));
            }
        });
    });

    const hexInput = document.querySelector('.hex-input');
    const swatch = document.querySelector('.color-swatch');

    if (hexInput && swatch) {
        const isValidHex = (value) => /^#([0-9A-Fa-f]{3}){1,2}$/.test(value);

        hexInput.addEventListener('input', function () {
            let value = hexInput.value.trim();
            if (value && !value.startsWith('#')) value = '#' + value;
            if (isValidHex(value)) swatch.style.backgroundColor = value;
        });

        hexInput.addEventListener('blur', function () {
            let value = hexInput.value.trim();
            if (value === "") { swatch.style.backgroundColor = "#FFFFFF"; return; }
            if (!value.startsWith('#')) value = '#' + value;

            if (!isValidHex(value)) {
                hexInput.value = "";
                swatch.style.backgroundColor = "#FFFFFF";
            } else {
                hexInput.value = value;
            }
        });
    }
    function updateRowRequirement(selectEl) {
        const row = selectEl.closest('tr');
        if (!row) return;
        const percentInput = row.querySelector('.js-percent-input, .js-version-value');
        if (!percentInput) return;

        if (selectEl.value && selectEl.value.trim() !== "") {
            percentInput.required = true;
        } else {
            percentInput.required = false;
        }
    }

    // --- 2. FORMULA CALCULATIONS ---
    function calculateFormulaTotals(table) {
        if (!table) return;

        const isMB = document.querySelector('.js-mb-formula');
        const isDC = document.querySelector('.js-dc-formula');

        if (isMB) {
            let totalPercent = 0;
            let totalWeight = 0;
            const percentInputs = table.querySelectorAll('.js-percent-input');
            const weightInputs = table.querySelectorAll('.js-weight-input');
            
            percentInputs.forEach(input => totalPercent += parseFloat(input.value) || 0);
            weightInputs.forEach(input => totalWeight += parseFloat(input.value) || 0);

            const totalPercentDisplay = table.querySelector('.js-total-percent-summary');
            const totalWeightDisplay = table.querySelector('.js-total-weight-summary');

            if (totalPercentDisplay) {
                totalPercentDisplay.value = totalPercent.toFixed(4);
                totalPercentDisplay.style.color = totalPercent > 100.0001 ? 'red' : '';
            }
            if (totalWeightDisplay) totalWeightDisplay.value = totalWeight.toFixed(4);
        }

        if (isDC) {
            const totals = {};
            table.querySelectorAll('.js-version-value').forEach(input => {
                const v = input.dataset.version;
                const val = parseFloat(input.value) || 0;
                totals[v] = (totals[v] || 0) + val;
            });

            table.querySelectorAll('.js-version-total').forEach(totalInput => {
                const v = totalInput.dataset.version;
                totalInput.value = (totals[v] || 0).toFixed(6);
            });
        }
    }

    document.addEventListener('input', function (e) {
        const table = e.target.closest('.js-formula-table');
        if (table) calculateFormulaTotals(table);
    });

    // --- 3. DC COLUMN LOCKING LOGIC ---
    function applyDcReadonlyLogic() {
        const form = document.querySelector('.js-dc-formula');
        if (!form) return;

        const isUpdate = form.querySelector('[name="formula_id"]')?.value.trim() !== '';
        let lastVersionWithData = 0;

        // Find the highest version number that currently has any data saved or typed
        document.querySelectorAll('.js-version-value').forEach(input => {
            if (input.value.trim() !== "" && parseFloat(input.value) !== 0) {
                const v = parseInt(input.dataset.version);
                if (v > lastVersionWithData) lastVersionWithData = v;
            }
        });

        // Rule: If New, only V1 is open. If Update, the next empty version is open.
        const activeVersion = isUpdate ? lastVersionWithData + 1 : 1;

        document.querySelectorAll('.js-version-value').forEach(input => {
            const v = parseInt(input.dataset.version);
            // Lock columns that are beyond the current allowed trial
            if (v > activeVersion) {
                input.readOnly = true;
                input.style.backgroundColor = "#f8f9fa";
                input.style.cursor = "not-allowed";
                input.tabIndex = "-1";
            } else {
                input.readOnly = false;
                input.style.backgroundColor = "";
                input.style.cursor = "text";
                input.tabIndex = "0";
            }
        });
    }
    const restrictToNumbers = (e) => {
        const charCode = (e.which) ? e.which : e.keyCode;
        if (charCode !== 46 && charCode > 31 && (charCode < 48 || charCode > 57)) { e.preventDefault(); return false; }
        if (charCode === 46 && e.target.value.indexOf('.') !== -1) { e.preventDefault(); return false; }
        return true;
    };

    document.querySelectorAll('.js-mixing-time-input').forEach(input => {
        input.addEventListener('keypress', restrictToNumbers);
    });
    
    // This splits "5 MIN" -> "5" when you open an existing formula
    document.querySelectorAll('.js-mixing-time-hidden').forEach(hidden => {
        if (hidden.value.includes(' MIN')) {
            const visibleInput = hidden.closest('.col-7').querySelector('.js-mixing-time-input');
            if (visibleInput) {
                visibleInput.value = hidden.value.replace(' MIN', '').trim();
            }
        } else if (hidden.value) {
            // Fallback if data is just a number
            const visibleInput = hidden.closest('.col-7').querySelector('.js-mixing-time-input');
            if (visibleInput) visibleInput.value = hidden.value;
        }
    });
    // final icon toggle logic
    const finalIcon = document.querySelector('.formula-final-star');
    const finalInput = document.querySelector('input[name="is_final"]');

    if (finalIcon && finalInput) {
        finalIcon.addEventListener('click', function() {
            // 1. Check current state from hidden input
            const isCurrentlyFinal = finalInput.value === 'true';
            
            // 2. Toggle state
            const newState = !isCurrentlyFinal;
            finalInput.value = newState ? 'true' : 'false';

            // 3. Update UI (Classes and Title)
            if (newState) {
                // Change to Filled Star
                this.classList.remove('bi-star', 'text-muted');
                this.classList.add('bi-star-fill', 'text-warning');
                this.title = "Final formula — click to unmark";
                Preline.toast("Marked as Final Formula", "success");
            } else {
                // Change to Empty Star
                this.classList.remove('bi-star-fill', 'text-warning');
                this.classList.add('bi-star', 'text-muted');
                this.title = "Mark as final formula";
                Preline.toast("Unmarked from Final", "info");
            }
        });
    }

    // --- 4. SAVE / NEW / PRINT BUTTONS ---
    const saveBtn = document.querySelector('.btn-save-formula');
    const newBtn = document.querySelector('.btn-new');
    const printBtn = document.querySelector('.btn-print');
    const form = saveBtn ? saveBtn.closest('form') : null;

    if (saveBtn && form) {
        saveBtn.addEventListener('click', function () {
            if (!form.reportValidity()) return;

            // --- CONCATENATE MIXING TIME BEFORE VALIDATION/SAVE ---
            const mixHidden = form.querySelector('.js-mixing-time-hidden');
            const mixVisible = form.querySelector('.js-mixing-time-input');
            if (mixHidden && mixVisible && mixVisible.value.trim() !== '') {
                mixHidden.value = `${mixVisible.value.trim()} MIN`;
            }

            const isMB = form.classList.contains('js-mb-formula');
            const isDC = form.classList.contains('js-dc-formula');
            const masterWgt = parseFloat(document.querySelector('.total-weight-display')?.value) || 0;

            if (isMB) {
                const totalPct = parseFloat(document.querySelector('.js-total-percent-summary')?.value) || 0;
                const totalWgt = parseFloat(document.querySelector('.js-total-weight-summary')?.value) || 0;
                
                if (totalPct.toFixed(2) !== "100.00") {
                    Preline.toast(`MB Error: Total percentage must be 100%. Current: ${totalPct}%`, 'error');
                    return;
                }
                if (totalWgt.toFixed(2) !== masterWgt.toFixed(2)) {
                    Preline.toast(`MB Error: Summary weight mismatch.`, 'error');
                    return;
                }
            }

            if (isDC) {
                // Find the version we are currently working on
                let activeV = 0;
                document.querySelectorAll('.js-version-value').forEach(input => {
                    if (input.value.trim() !== "" && !input.readOnly) {
                        activeV = Math.max(activeV, parseInt(input.dataset.version));
                    }
                });

                if (activeV === 0) {
                    Preline.toast("Please enter values for at least one version.", "error");
                    return;
                }

                const versionTotalInput = document.querySelector(`.js-version-total[data-version="${activeV}"]`);
                const versionTotal = parseFloat(versionTotalInput?.value) || 0;

                if (versionTotal.toFixed(2) !== masterWgt.toFixed(2)) {
                    Preline.toast(`DC Error: Trial #${activeV} total (${versionTotal.toFixed(4)}) must match Total Weight (${masterWgt.toFixed(4)}).`, 'error');
                    return;
                }
            }

            const isUpdate = form.querySelector('[name="formula_id"]')?.value.trim() !== '';
            Preline.confirm(
                isUpdate ? 'Update Formula?' : 'Save Formula?',
                'Please verify all technical specs before confirming.',
                'success',
                () => { form.submit(); }
            );
        });
    }

    // ... (New and Print logic remain the same as your provided code) ...
    if (newBtn) {
        newBtn.addEventListener('click', () => {
            Preline.confirm('Create New?', 'Unsaved changes will be lost.', 'warning', () => {
                window.location.href = window.location.pathname;
            });
        });
    }

    if (printBtn) {
        printBtn.addEventListener('click', () => {
            const config = getFormulaPrintConfig();
            if (!config?.formulaId) {
                Preline.confirm('Not Yet Saved', 'Please save this formula before printing.', 'warning', () => {});
                return;
            }
            // function for print preview using Com/ms office and modifying the template in print excel
            // openFormulaPreview(config.urlPrefix, config.formulaId);
            
            // print using html css for flexible print
            printFormula(config.urlPrefix, config.formulaId);

        });
    }

    function getFormulaPrintConfig() {
        const mb = document.querySelector('.js-mb-formula');
        const dc = document.querySelector('.js-dc-formula');
        return {
            urlPrefix: mb ? 'mb-formula' : 'dc-formula',
            formulaId: document.querySelector('input[name="formula_id"]')?.value,
        };
    }

    function printFormula(urlPrefix, formulaId) {
        const oldFrame = document.getElementById('formulaPrintFrame');
        if (oldFrame) oldFrame.remove();

        const iframe = document.createElement('iframe');
        iframe.id = 'formulaPrintFrame';
        iframe.style.display = 'none'
        iframe.src = `/${urlPrefix}/print/${formulaId}/`;

        iframe.onload = function () {
            setTimeout(() => {
                iframe.contentWindow.focus();
                iframe.contentWindow.print();

                const csrfToken = document.querySelector('#formulaForm [name=csrfmiddlewaretoken]')?.value;
                fetch(`/${urlPrefix}/log-print/${formulaId}/`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken }
                });
            }, 500);
        };

        document.body.appendChild(iframe);
    }

    // function for print preview using Com/ms office and modifying the template in print excel
    // function openFormulaPreview(urlPrefix, formulaId) {
    //     const previewUrl = `/${urlPrefix}/print/${encodeURIComponent(formulaId)}/preview`;
    //     showLoader();
    //     const dialog = document.createElement('dialog');
    //     dialog.className = 'p-0 border-0 rounded-3 shadow-lg';
    //     dialog.style.width = '90vw'; dialog.style.height = '90vh'; dialog.style.maxWidth = '1200px';
    //     dialog.innerHTML = `
    //         <div class="d-flex flex-column w-100 h-100">
    //             <div class="d-flex justify-content-end gap-2 p-2 bg-dark">
    //                 <button id="formulaPreviewPrintBtn" class="btn btn-primary btn-sm"><i class="bi bi-printer"></i> Print</button>
    //                 <button id="formulaPreviewCloseBtn" class="btn btn-secondary btn-sm">Close</button>
    //             </div>
    //             <iframe id="formulaPreviewFrame" src="${previewUrl}" class="flex-grow-1 w-100 border-0"></iframe>
    //         </div>
    //     `;
    //     document.body.appendChild(dialog);
    //     const iframe = dialog.querySelector('#formulaPreviewFrame');
    //     iframe.addEventListener('load', () => { hideLoader(); dialog.showModal(); });
    //     dialog.querySelector('#formulaPreviewPrintBtn').addEventListener('click', () => {
    //         iframe.contentWindow.print();
    //         fetch(`//${urlPrefix}/log-print/${formulaId}/`);
    //     });
    //     dialog.querySelector('#formulaPreviewCloseBtn').addEventListener('click', () => dialog.close());
    //     dialog.addEventListener('close', () => dialog.remove());
    // }

    // --- 5. INITIALIZATION ---
    const initialTable = document.querySelector('.js-formula-table');
    if(initialTable) calculateFormulaTotals(initialTable);
    
    // Apply DC specific UI logic
    if (document.querySelector('.js-dc-formula')) {
        applyDcReadonlyLogic();
    }
    

    //  Shared AJAX Auto-population Logic for MB and DC
    const cmfSelectMB = document.getElementById('id_mb_cmf_number');
    const cmfSelectDC = document.getElementById('id_dc_cmf_number');
    const isDC = !!cmfSelectDC;
    const cmfSelectEl = cmfSelectMB || cmfSelectDC;

    async function fetchCmfDetails(cmfNo, matId = null) {
        const fields = {
            customer: isDC ? 'id_dc_customer' : 'id_customer',
            resin: isDC ? 'id_dc_resin' : 'id_resin_used',
            color: isDC ? 'id_dc_color' : 'id_color',
            product: isDC ? 'id_dc_product_code' : 'id_product',
            dosage: isDC ? 'id_dc_dosage' : 'id_dosage',
            application: isDC ? 'id_dc_application' : 'id_application',
            finished_product: isDC ? 'id_dc_finished_product' : 'id_finished_product',
            lot_no: 'id_lot_number' 
        };
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.value = val || '';
        };
        try {
            // Pass matId as an extra parameter
            let url = `/cmf/mb-dc-formula/?cm_no=${encodeURIComponent(cmfNo)}`;
            if (matId) url += `&mat_id=${encodeURIComponent(matId)}`;

            const response = await fetch(url);
            if (!response.ok) throw new Error('Network response was not ok');
            const data = await response.json();

            setVal(fields.customer, data.customer);
            setVal(fields.resin, data.resin_used || data.resin);
            setVal(fields.color, data.color);
            setVal(fields.application, data.application);
            setVal(fields.finished_product, data.finished_product);
            setVal(fields.product, data.product_code); // Priority to generated code
            setVal(fields.dosage, data.dosage);
            setVal(fields.lot_no, data.lot_no);

            if (data.product_code === "(Select Material)") {
                Preline.toast("CMF details loaded. Please select a Material Code to generate the Product Code.", "info");
            } else {
                Preline.toast(`Details for ${cmfNo} loaded.`, 'success');
            }
            
        } catch (error) {
            Object.values(fields).forEach(id => setVal(id, ''));
            Preline.toast('Error fetching details.', 'danger');
        }
    }
    
    // Add this inside your (function () { ... })(); wrapper
    const matSelectDC = document.getElementById('id_dc_material_code');

    const initDcMaterialPop = () => {
        if (matSelectDC && matSelectDC.tagName === 'SELECT') {
            let tsAttempts = 0;
            const pollTomSelect = setInterval(() => {
                tsAttempts++;
                if (matSelectDC.tomselect) {
                    clearInterval(pollTomSelect);
                    
                    matSelectDC.tomselect.on('change', function(value) {
                        const cmfNo = cmfSelectEl.value; // Get the currently selected CMF No
                        if (!value || !cmfNo) return;

                        // Call the same function, but the backend will now have the matId
                        fetchCmfDetails(cmfNo, value);
                    });
                } else if (tsAttempts > 50) {
                    clearInterval(pollTomSelect);
                }
            }, 100);
        }
    };

    const initAutoPop = () => {
        if (cmfSelectEl && cmfSelectEl.tagName === 'SELECT') {
            let tsAttempts = 0;
            const pollTomSelect = setInterval(() => {
                tsAttempts++;
                if (cmfSelectEl.tomselect) {
                    clearInterval(pollTomSelect);
                    
                    cmfSelectEl.tomselect.on('change', function(value) {
                        if (!value) return;

                       
                        Preline.confirm(
                            'Load Record Details?',
                            `Do you want to automatically fill the form with details from CMF #${value}?`,
                            'info',
                            () => fetchCmfDetails(value), 
                            () => { console.log("User cancelled auto-fill."); }
                        );
                    });
                } else if (tsAttempts > 50) {
                    clearInterval(pollTomSelect);
                }
            }, 100);
        }
    };

    initAutoPop();
    initDcMaterialPop();

    const init = () => {
        if (!cmfSelectEl) return;

        // 1. Handle URL Redirects (Automatic Load)
        const params = new URLSearchParams(window.location.search);
        const recordNo = params.get('no');
        const recordType = params.get('type');
        const formulaId = params.get('formula_id');

        // Only auto-trigger if type is 'cmf' and it's not a saved formula edit
        if (recordNo && recordType === 'cmf' && !formulaId) {
            // Wait for TomSelect to be ready
            const checkTS = setInterval(() => {
                if (cmfSelectEl.tomselect) {
                    clearInterval(checkTS);
                    // Set value visually in dropdown
                    cmfSelectEl.tomselect.setValue(recordNo, true); // 'true' silent mode
                    // Call AJAX immediately for CMF
                    fetchCmfDetails(recordNo);
                }
            }, 100);
        }

        // 2. Handle Manual Selection Changes
        if (cmfSelectEl.tagName === 'SELECT') {
            const checkTSManual = setInterval(() => {
                if (cmfSelectEl.tomselect) {
                    clearInterval(checkTSManual);
                    
                    cmfSelectEl.tomselect.on('change', function(value) {
                        if (!value) return;

                        // Check if value was already populated by Django (for RS)
                        // If it's a manual change by user, we always show confirmation
                        if (window.Preline && typeof Preline.confirm === 'function') {
                            Preline.confirm(
                                'Load Record Details?',
                                `Do you want to automatically fill the form with details from CMF #${value}?`,
                                'info',
                                () => fetchCmfDetails(value),
                                () => {}
                            );
                        } else {
                        }
                    });
                }
            }, 100);
        }
    };

    // Run when page is ready
    window.addEventListener('load', init);
})();