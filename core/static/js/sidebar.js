document.addEventListener("DOMContentLoaded", function () {
    const sidebar = document.getElementById("sidebar");
    const toggleBtn = document.getElementById("toggleSidebar");

    if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
            if (window.innerWidth <= 992) {
                sidebar.classList.toggle("show");
            } else {
                sidebar.classList.toggle("collapsed");
            }
        });
    }

    // Auto-hide submenu when sidebar is collapsed
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.target.classList.contains('collapsed')) {
                const openSubmenus = document.querySelectorAll('.collapse.show');
                openSubmenus.forEach(menu => {
                    const instance = bootstrap.Collapse.getInstance(menu);
                    if (instance) instance.hide();
                });
            }
        });
    });

    observer.observe(sidebar, { attributes: true, attributeFilter: ['class'] });
});