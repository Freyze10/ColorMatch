document.addEventListener("DOMContentLoaded", function () {
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebarOverlay");
    const toggleSidebar = document.getElementById("toggleSidebar"); // Button inside sidebar
    const mobileToggle = document.getElementById("mobileToggle"); // Button in top navbar
    const themeToggle = document.getElementById("themeToggle");
    const body = document.body;

    // --- 1. Sidebar Toggle Logic ---
    function toggleMenu() {
        if (window.innerWidth < 992) {
            sidebar.classList.toggle("show");
            overlay.classList.toggle("show");
        } else {
            sidebar.classList.toggle("collapsed");
        }
    }

    if (toggleSidebar) toggleSidebar.addEventListener("click", toggleMenu);
    if (mobileToggle) mobileToggle.addEventListener("click", toggleMenu);
    
    if (overlay) {
        overlay.addEventListener("click", () => {
            sidebar.classList.remove("show");
            overlay.classList.remove("show");
        });
    }

    // --- 2. Theme Toggle Logic ---
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme === "dark") {
        body.classList.add("dark-mode");
        if (themeToggle) themeToggle.textContent = "Switch to Light Mode";
    }

    if (themeToggle) {
        themeToggle.addEventListener("click", (e) => {
            e.preventDefault();
            body.classList.toggle("dark-mode");
            
            const isDark = body.classList.contains("dark-mode");
            localStorage.setItem("theme", isDark ? "dark" : "light");
            themeToggle.textContent = isDark ? "Switch to Light Mode" : "Try Dark Mode";
        });
    }

    // --- 3. Datetime Logic ---
    const dtField = document.getElementById('datetimeFooter');
    if (dtField) {
        setInterval(() => {
            const now = new Date();
            dtField.textContent = now.toLocaleString();
        }, 1000);
    }
});