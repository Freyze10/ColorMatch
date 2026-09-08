(function () {
    window.addEventListener('load', function () {
        // --- Toggle password visibility ---
        const toggleBtn = document.querySelector('.js-password-toggle-btn');
        const toggleInput = document.querySelector('.js-toggle-password');
        if (toggleBtn && toggleInput) {
            toggleBtn.addEventListener('click', function () {
                const icon = this.querySelector('i');
                const isHidden = toggleInput.type === 'password';
                toggleInput.type = isHidden ? 'text' : 'password';
                icon.className = isHidden ? 'bi bi-eye' : 'bi bi-eye-slash';
            });
        }

        // --- Change Password: confirm before submit + client-side match check ---
        const passwordForm = document.getElementById('changePasswordForm');
        if (passwordForm) {
            passwordForm.addEventListener('submit', function (e) {
                const newPass = document.getElementById('id_new_password').value;
                const confirmPass = document.getElementById('id_confirm_password').value;

                if (newPass !== confirmPass) {
                    e.preventDefault();
                    Preline.toast('New password and confirmation do not match.', 'danger');
                    return;
                }

                if (newPass.length < 8) {
                    e.preventDefault();
                    Preline.toast('Password must be at least 8 characters.', 'warning');
                    return;
                }
            });
        }

        // --- Personal Info: confirm before saving ---
        const infoForm = document.getElementById('personalInfoForm');
        if (infoForm) {
            infoForm.addEventListener('submit', function (e) {
                e.preventDefault();
                Preline.confirm(
                    'Update Personal Info?',
                    'Are you sure you want to save these changes to your profile?',
                    'success',
                    () => infoForm.submit()
                );
            });
        }

        // --- Log out everywhere ---
        const logoutAllBtn = document.getElementById('btnLogoutAllDevices');
        if (logoutAllBtn) {
            logoutAllBtn.addEventListener('click', function () {
                Preline.confirm(
                    'Log Out Everywhere?',
                    'This will end all active sessions on every device, including this one. Continue?',
                    'danger',
                    () => {
                        window.location.href = "{% url 'logout_all_devices' %}";
                    }
                );
            });
        }
    });
})();