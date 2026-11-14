const Preline = {
    // 1. TOAST SYSTEM
    toast: function(message, type = 'success') {
        let container = document.getElementById('preline-toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'preline-toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        const cleanType = type.includes('error') ? 'danger' : type;
        toast.className = `preline-toast ${cleanType}`;
        
        let icon = 'check-circle-fill';
        if (cleanType === 'danger' || cleanType === 'error') icon = 'exclamation-triangle-fill';
        if (cleanType === 'warning') icon = 'exclamation-circle-fill';

        toast.innerHTML = `
            <i class="bi bi-${icon} fs-5"></i>
            <div class="flex-grow-1 mr-2">
                <span class="small fw-semibold d-block">${cleanType.toUpperCase()}</span>
                <span class="small opacity-75">${message}</span>
            </div>
            <button type="button" class="btn-close ms-2" style="font-size: 0.7rem" onclick="this.parentElement.remove()"></button>
        `;

        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(40px)';
            setTimeout(() => toast.remove(), 500);
        }, 4000);
    },

    // 2. ALERT (ONLY 1 OK BUTTON & NO STUCK GRAY BACKDROP)
    alert: function(title, message, type = 'info', onOk) {
        const modalEl = document.getElementById('dynamicModal');
        if (!modalEl) return;

        // Use getOrCreateInstance to prevent multiple backdrop duplication
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

        document.getElementById('modalTitle').innerText = title;
        document.getElementById('modalMessage').innerText = message;

        const iconContainer = document.getElementById('modalIconContainer');
        const icon = document.getElementById('modalIcon');
        const cleanType = (type === 'error') ? 'danger' : (type || 'info');

        iconContainer.className = 'modal-icon-circle icon-' + cleanType;
        if (cleanType === 'danger') icon.className = 'bi bi-exclamation-triangle';
        else if (cleanType === 'warning') icon.className = 'bi bi-exclamation-circle';
        else if (cleanType === 'info') icon.className = 'bi bi-info-circle';
        else icon.className = 'bi bi-check-lg';

        const confirmBtn = document.getElementById('modalConfirmBtn');
        const newConfirmBtn = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

        // Hide ALL other buttons in the footer (guarantees "Cancel" is hidden)
        modalEl.querySelectorAll('.modal-footer button, button[data-bs-dismiss="modal"]').forEach(btn => {
            if (btn !== newConfirmBtn && !btn.classList.contains('btn-close')) {
                btn.style.setProperty('display', 'none', 'important');
            }
        });

        newConfirmBtn.innerText = 'OK';

        let handled = false;
        const triggerCallback = () => {
            if (!handled) {
                handled = true;
                if (typeof onOk === 'function') onOk();
            }
        };

        newConfirmBtn.onclick = () => {
            triggerCallback();
            modal.hide();
        };

        modalEl.addEventListener('hidden.bs.modal', function handler() {
            triggerCallback();

            // Restore all hidden buttons for future confirm dialogs
            modalEl.querySelectorAll('.modal-footer button').forEach(btn => {
                btn.style.removeProperty('display');
            });

            // 🛑 FORCE REMOVE ANY STUCK GRAY BACKDROP
            document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
            document.body.classList.remove('modal-open');
            document.body.style.removeProperty('overflow');
            document.body.style.removeProperty('padding-right');

            modalEl.removeEventListener('hidden.bs.modal', handler);
        });

        modal.show();
    },
    
    // 3. CONFIRMATION MODAL
    confirm: function(title, message, type, onConfirm, onCancel) {
        const modalEl = document.getElementById('dynamicModal');
        const modal = new bootstrap.Modal(modalEl);
        
        document.getElementById('modalTitle').innerText = title;
        document.getElementById('modalMessage').innerText = message;
        
        const iconContainer = document.getElementById('modalIconContainer');
        const icon = document.getElementById('modalIcon');
        
        // 1. Normalize type
        const cleanType = (type === 'error') ? 'danger' : (type || 'success');
        
        // 2. Set Circle Color Class (Ensure .icon-info exists in your CSS)
        iconContainer.className = 'modal-icon-circle icon-' + cleanType;
        
        // 3. Set the specific Icon (ADDED 'info' HERE)
        if (cleanType === 'danger') {
            icon.className = 'bi bi-exclamation-triangle'; // Error Triangle
        } else if (cleanType === 'warning') {
            icon.className = 'bi bi-exclamation-circle';   // Warning Circle
        } else if (cleanType === 'info') {
            icon.className = 'bi bi-info-circle';          // Info Circle <--- ADDED
        } else {
            icon.className = 'bi bi-check-lg';              // Success Check
        }

        const confirmBtn = document.getElementById('modalConfirmBtn');
        const newConfirmBtn = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

        let confirmed = false;

        newConfirmBtn.onclick = () => {
            confirmed = true;
            if (typeof onConfirm === 'function') {
                onConfirm();
            }
            modal.hide();
        };

        modalEl.addEventListener('hidden.bs.modal', function handler() {
            if (!confirmed && typeof onCancel === 'function') {
                onCancel();
            }
            modalEl.removeEventListener('hidden.bs.modal', handler);
        });

        modal.show();
    }
};