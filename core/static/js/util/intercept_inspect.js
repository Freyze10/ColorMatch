(function() {
    'use strict';

    // =========================================================================
    // 1. BLOCK RIGHT-CLICK CONTEXT MENU
    // =========================================================================
    document.addEventListener('contextmenu', function(e) {
        e.preventDefault();
        return false;
    });

    // =========================================================================
    // 2. BLOCK KEYBOARD SHORTCUTS (Windows & Mac)
    // =========================================================================
    document.addEventListener('keydown', function(e) {
        // F12
        if (e.key === 'F12' || e.keyCode === 123) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        }

        const isCtrlOrCmd = e.ctrlKey || e.metaKey;

        // Ctrl + Shift + I (Inspect)
        // Ctrl + Shift + J (Console)
        // Ctrl + Shift + C (Element selector)
        if (isCtrlOrCmd && e.shiftKey && ['I', 'J', 'C', 'i', 'j', 'c'].includes(e.key)) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        }

        // Ctrl + U (View Source)
        // Ctrl + S (Save Page)
        if (isCtrlOrCmd && ['u', 'U', 's', 'S'].includes(e.key)) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        }
    });

    // =========================================================================
    // 3. INTERCEPT WHEN DEVTOOLS IS OPENED
    // =========================================================================
    function onDevToolsDetected() {
        // Clears the screen and displays a security lockdown message
        document.body.innerHTML = `
            <div style="
                height: 100vh;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                background-color: #0f172a;
                color: #f8fafc;
                font-family: sans-serif;
                text-align: center;
                padding: 20px;
            ">
                <div style="font-size: 3rem; margin-bottom: 1rem;">🔒</div>
                <h2 style="font-weight: 700; margin-bottom: 0.5rem;">Access Denied</h2>
                <p style="color: #94a3b8; max-width: 420px; margin-bottom: 1.5rem; font-size: 0.95rem;">
                    Developer tools and code inspection are restricted on this system for security purposes.
                </p>
                <button onclick="window.location.reload()" style="
                    background-color: #0d9488;
                    color: white;
                    border: none;
                    padding: 8px 24px;
                    border-radius: 6px;
                    font-weight: 600;
                    cursor: pointer;
                ">
                    Reload Page
                </button>
            </div>
        `;
    }

    // Method A: Dimension Check (Catches docked DevTools on side or bottom)
    const threshold = 160;
    setInterval(function() {
        const widthDiff = window.outerWidth - window.innerWidth > threshold;
        const heightDiff = window.outerHeight - window.innerHeight > threshold;
        if (widthDiff || heightDiff) {
            onDevToolsDetected();
        }
    }, 1000);

    // Method B: Debugger Freeze (Traps anyone who manages to open DevTools in an infinite pause loop)
    setInterval(function() {
        (function() {
            return false;
        }['constructor']('debugger')['call']());
    }, 200);

})();