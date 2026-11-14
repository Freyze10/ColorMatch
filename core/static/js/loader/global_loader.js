// window.addEventListener('load', function() {
//     const loader = document.getElementById('global-loader');
//     // Fade out effect
//     loader.style.opacity = '0';
//     setTimeout(() => {
//         loader.style.visibility = 'hidden';
//     }, 500); 
// });

// // --- 2. Show loader on specific actions ---
// function showLoader() {
//     const loader = document.getElementById('global-loader');
//     loader.style.visibility = 'visible';
//     loader.style.opacity = '1';
// }

// // --- 3. Auto-attach to all Forms on submit ---
// // This ensures that when you save a formula or sync, the loader appears.
// document.querySelectorAll('form').forEach(form => {
//     form.addEventListener('submit', function() {
//         // Only show if the form is valid (to prevent showing on validation errors)
//         if (this.checkValidity()) {
//             showLoader();
//         }
//     });
// });

// --- Global Loader Functions ---
function showLoader() {
    const loader = document.getElementById('global-loader');
    if (loader) {
        loader.style.visibility = 'visible';
        loader.style.opacity = '1';
    }
}

function hideLoader() {
    const loader = document.getElementById('global-loader');
    if (loader) {
        loader.style.opacity = '0';
        setTimeout(() => {
            loader.style.visibility = 'hidden';
        }, 500); 
    }
}

// Initial page load listener
window.addEventListener('load', hideLoader);
window.addEventListener('pageshow', function (event) {
    // Runs when navigating back or forward through browser history
    if (typeof hideLoader === 'function') {
        hideLoader();
    }
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
});