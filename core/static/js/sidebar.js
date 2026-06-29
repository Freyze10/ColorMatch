document.addEventListener("DOMContentLoaded", function () {
const sidebar = document.getElementById("sidebar");
const toggle = document.getElementById("toggleSidebar");

if (toggle && sidebar) {
    toggle.addEventListener("click", () => {
        if (window.innerWidth <= 992) {
            // Mobile: Toggle visibility
            sidebar.classList.toggle("show");
        } else {
            // Desktop: Toggle narrow width
            sidebar.classList.toggle("collapsed");
        }
    });
}

// Close sidebar when clicking outside on mobile
document.addEventListener("click", (e) => {
    if (window.innerWidth <= 992) {
        if (!sidebar.contains(e.target) && !toggle.contains(e.target) && sidebar.classList.contains("show")) {
            sidebar.classList.remove("show");
        }
    }
});
});