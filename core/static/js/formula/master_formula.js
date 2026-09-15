(function () {
    // --- 1. CORE MATERIAL UTILITIES ---
    function recalcTotal() {
        let total = 0;
        document.querySelectorAll('.mf-material-row').forEach(row => {
            total += parseFloat(row.dataset.concentration || 0);
        });
        
        const formatted = total.toFixed(6);

        // 1. Update the UI Span (Material Breakdown card)
        document.getElementById('mfTotalConcentration').innerText = formatted;

        // 2. Update the Hidden Input (to be sent to the server as total_concentration)
        document.getElementById('id_hidden_total_concentration').value = formatted;

        // 3. Update the Visible Input (Formulation Details card)
        document.getElementById('id_mf_sum_of_con').value = formatted;
    }

    function addMaterialRow(code, conc) {
        if (!code) return;
        const tbody = document.getElementById('mfMaterialTableBody');
        const row = document.createElement('tr');
        row.className = 'mf-material-row';
        row.dataset.material = code;
        row.dataset.concentration = conc;
        row.style.cursor = 'pointer';
        row.innerHTML = `<td>${code}</td><td class="text-end">${parseFloat(conc).toFixed(6)}</td>`;
        
        row.onclick = function() {
            document.querySelectorAll('.mf-material-row').forEach(r => r.classList.remove('table-active'));
            this.classList.add('table-active');
        };
        tbody.appendChild(row);
    }

    window.addEventListener('load', function() {
        const entryForm = document.getElementById('masterFormulaEntryForm');
        const saveBtn = document.querySelector('.btn-save');
        const newBtn = document.querySelector('.btn-new');
        const printBtn = document.querySelector('.btn-print');
        const materialCodeSelect = document.getElementById('id_mf_material_code').tomselect;
        const concentrationInput = document.getElementById('id_mf_concentration');
        const materialTableBody = document.getElementById('mfMaterialTableBody');

        // --- 2. SAVE WITH PRELINE CONFIRMATION ---
        if (saveBtn && entryForm) {
            saveBtn.addEventListener('click', function() {
                if (entryForm.reportValidity()) {
                    const isUpdate = document.querySelector('[name="is_new_flag"]').value !== 'true';

                    Preline.confirm(
                        isUpdate ? 'Update Master Formula?' : 'Save Master Formula?',
                        isUpdate
                            ? 'Are you sure you want to update this formula? This will modify existing records.'
                            : 'Are you sure you want to save this new Master Formula? Please verify all concentrations before confirming.',
                        'success',
                        () => {
                            const materials = [];
                            document.querySelectorAll('.mf-material-row').forEach(row => {
                                materials.push({
                                    material: row.dataset.material,
                                    concentration: row.dataset.concentration
                                });
                            });
                            document.getElementById('id_materials_data').value = JSON.stringify(materials);
                            entryForm.submit();
                        }
                    );
                }
            });
        }

        if (newBtn) {
            newBtn.addEventListener('click', () => {
                Preline.confirm(
                    'Create New?',
                    'Any unsaved changes on this form will be lost. Do you want to continue?',
                    'warning',
                    () => {
                        window.location.href = "/master-formula/?new_entry=true";
                    }
                );
            });
        }

        // --- 3. MATERIAL CONTROL BUTTONS WITH ERROR HANDLING ---
        document.getElementById('mfAddMaterialBtn').addEventListener('click', function () {
            const code = materialCodeSelect.getValue();
            const concentration = parseFloat(concentrationInput.value) || 0;

            if (!code) { 
                Preline.toast('Please select a material code.', 'warning'); 
                return; 
            }

            // Check for duplicates
            const existing = Array.from(materialTableBody.querySelectorAll('tr.mf-material-row'))
                                 .find(r => r.dataset.material === code);

            if (existing) {
                // Update existing row
                existing.dataset.concentration = concentration;
                existing.querySelector('td:last-child').innerText = concentration.toFixed(6);
                Preline.toast(`Updated concentration for ${code}`, 'success');
            } else { 
                // Add new row
                addMaterialRow(code, concentration); 
            }

            recalcTotal();
            materialCodeSelect.clear();
            concentrationInput.value = "0.000000";
        });

        document.getElementById('mfRemoveMaterialBtn').addEventListener('click', function () {
            const selectedRow = materialTableBody.querySelector('.mf-material-row.table-active');
            if (!selectedRow) { 
                Preline.toast('Select a material row from the table first.', 'warning'); 
                return; 
            }
            selectedRow.remove(); 
            recalcTotal();
            Preline.toast('Material removed.', 'success');
        });

        document.getElementById('mfClearMaterialsBtn').addEventListener('click', function () {
            if (materialTableBody.children.length === 0) return;

            Preline.confirm('Clear All Materials?', 'This will remove every material row. Continue?', 'warning', () => {
                materialTableBody.innerHTML = ''; 
                recalcTotal();
                Preline.toast('All materials cleared.', 'success');
            });
        });

        // --- 4. LOOKUP MODAL LOGIC ---
        const cmNoEl = document.getElementById('id_mf_cm_no');
        const browseBtn = document.getElementById('mfBrowseFormulasBtn');
        const lookupModal = document.getElementById('mfFormulaLookupModal');
        const lookupModalBody = document.getElementById('mfLookupModalBody');
        const selectBtn = document.getElementById('id_modal_select_btn');
        let highlightedLookupRow = null;

        if (cmNoEl.tomselect) {
            cmNoEl.tomselect.on('change', (val) => browseBtn.disabled = val.trim() === '');
        }

        function loadFormulaIntoForm(row) {
            const ds = row.dataset;
            document.getElementById('id_source_formula_pk').value = ds.pk || '';
            document.getElementById('id_source_formula_type').value = ds.formulaType || '';

            if (document.getElementById('id_mf_customer').tomselect) document.getElementById('id_mf_customer').tomselect.setValue(ds.customer || '');
            if (document.getElementById('id_mf_matched_by').tomselect) document.getElementById('id_mf_matched_by').tomselect.setValue(ds.matchedBy || '');
            
            document.getElementById('id_mf_resin').value = ds.resin || '';
            document.getElementById('id_mf_application').value = ds.application || '';
            document.getElementById('id_mf_product_code').value = ds.productCode || '';
            document.getElementById('id_mf_prod_color').value = ds.color || '';
            document.getElementById('id_mf_dosage').value = ds.dosage || '';
            document.getElementById('id_mf_mix_time').value = ds.mixingTime || '5 MIN';
            document.getElementById('id_mf_colormatch_date').value = ds.dateMatched || '';
            document.getElementById('id_mf_html').value = ds.html || '';
            document.getElementById('id_mf_cyan').value = ds.cyan || '';
            document.getElementById('id_mf_magenta').value = ds.magenta || '';
            document.getElementById('id_mf_yellow').value = ds.yellow || '';
            document.getElementById('id_mf_black').value = ds.black || '';
            
            const radioId = (ds.formulaType === 'DC') ? 'typeDC' : 'typeMB';
            const radio = document.getElementById(radioId);
            if (radio) radio.checked = true;

            const scriptTag = document.getElementById(ds.scriptId);
            if (scriptTag) {
                const ingredients = JSON.parse(scriptTag.textContent);
                materialTableBody.innerHTML = '';
                ingredients.forEach(ing => addMaterialRow(ing.material, ing.value));
                recalcTotal();
            }
            lookupModal.style.display = 'none';
            Preline.toast('Formula details loaded.', 'success');
        }
        if (browseBtn) {
            browseBtn.addEventListener('click', async function () {
                const matchingNo = cmNoEl.tomselect.getValue();
                if (!matchingNo) return;
                document.getElementById('mfLookupMatchingNo').innerText = matchingNo;
                lookupModalBody.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-teal"></div></div>';
                lookupModal.style.display = 'flex';
                selectBtn.disabled = true;

                try {
                    const response = await fetch(`/master-formula/lookup/?matching_no=${encodeURIComponent(matchingNo)}`);
                    lookupModalBody.innerHTML = await response.text();
                    
                    lookupModalBody.querySelectorAll('.mf-lookup-header-row').forEach(row => {
                        row.addEventListener('click', function() {
                            lookupModalBody.querySelectorAll('.mf-lookup-header-row').forEach(r => r.classList.remove('table-active'));
                            row.classList.add('table-active');
                            highlightedLookupRow = row; 
                            selectBtn.disabled = false;
                            
                            const nextRow = row.nextElementSibling;
                            if (nextRow && nextRow.classList.contains('ingredient-sub-row')) {
                                const isHidden = nextRow.classList.toggle('d-none');
                                const icon = row.querySelector('.toggle-main-icon');
                                if(icon) icon.className = isHidden ? 'bi bi-plus-circle-fill toggle-main-icon text-teal' : 'bi bi-dash-circle-fill toggle-main-icon text-danger';
                            }
                        });
                        row.addEventListener('dblclick', () => loadFormulaIntoForm(row));
                    });
                } catch (err) { lookupModalBody.innerHTML = '<div class="text-center py-5 text-danger">Error fetching lookup data.</div>'; }
            });
        }
        selectBtn.addEventListener('click', () => { if (highlightedLookupRow) loadFormulaIntoForm(highlightedLookupRow); });
        document.getElementById('id_close_modal_top').onclick = () => lookupModal.style.display='none';
        document.getElementById('id_close_modal_bottom').onclick = () => lookupModal.style.display='none';
    
        if (printBtn) {
            printBtn.addEventListener('click', function () {
                const formId = document.querySelector('[name="form_id"]').value;
                const isNew = document.querySelector('[name="is_new_flag"]').value === 'true';

                if (isNew || !formId) {
                    Preline.toast('Please save the formula before printing.', 'warning');
                    return;
                }

                // Remove any leftover print iframe from a previous click
                const oldFrame = document.getElementById('mfPrintFrame');
                if (oldFrame) oldFrame.remove();

                const iframe = document.createElement('iframe');
                iframe.id = 'mfPrintFrame';
                iframe.style.display = 'none'; // Keep it hidden
                iframe.src = `/master-formula/print/${formId}/`;

                iframe.onload = function () {
                    // Small delay to ensure styles are loaded
                    setTimeout(() => {
                        iframe.contentWindow.focus();
                        iframe.contentWindow.print();
                    }, 500);
                };

                document.body.appendChild(iframe);
            });
        }
    });
})();