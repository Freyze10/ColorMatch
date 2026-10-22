/**
 * Spectro fields (L*, a*, b*, C*, H°) for the MB and DC formula entry forms.
 *  1. Formats each value to 4 decimals when you leave the field.
 *  2. Draws a live color swatch (.spectro-swatch) from the values.
 *
 * The swatch is computed from CIELAB (L*, a*, b*) using the D65 white point and
 * converted to sRGB. If a* and b* are empty but C* and H° are filled, a* and b*
 * are derived from them (a = C·cos H, b = C·sin H).
 */
(function () {

    // ---------- color math: CIELAB (D65) -> sRGB hex ----------
    function labToHex(L, a, b) {
        const eps = 216 / 24389, kappa = 24389 / 27;

        // Lab -> XYZ (D65 reference white)
        const fy = (L + 16) / 116;
        const fx = fy + a / 500;
        const fz = fy - b / 200;
        const xr = fx ** 3 > eps ? fx ** 3 : (116 * fx - 16) / kappa;
        const yr = L > kappa * eps ? fy ** 3 : L / kappa;
        const zr = fz ** 3 > eps ? fz ** 3 : (116 * fz - 16) / kappa;
        const X = xr * 0.95047, Y = yr, Z = zr * 1.08883;

        // XYZ -> linear sRGB
        const lin = [
             3.2404542 * X - 1.5371385 * Y - 0.4985314 * Z,
            -0.9692660 * X + 1.8760108 * Y + 0.0415560 * Z,
             0.0556434 * X - 0.2040259 * Y + 1.0572252 * Z
        ];

        // gamma-encode, clamp (out-of-gamut colors are clipped to the nearest edge), to hex
        return '#' + lin.map(function (c) {
            c = Math.min(1, Math.max(0, c));
            const v = c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
            return Math.round(v * 255).toString(16).padStart(2, '0');
        }).join('').toUpperCase();
    }
    window.labToHex = labToHex;

    // ---------- page wiring ----------
    document.addEventListener('DOMContentLoaded', function () {
        const lIn = document.getElementById('id_spectro_l');
        const aIn = document.getElementById('id_spectro_a');
        const bIn = document.getElementById('id_spectro_b');
        const cIn = document.getElementById('id_spectro_c');
        const hIn = document.getElementById('id_spectro_h');
        const swatch = document.querySelector('.spectro-swatch');
        if (!lIn || !aIn || !bIn || !cIn || !hIn || !swatch) return;

        const inputs = [lIn, aIn, bIn, cIn, hIn];
        const num = function (el) {
            const v = parseFloat(el.value);
            return Number.isFinite(v) ? v : null;
        };

        function updateSwatch() {
            const L = num(lIn);
            let a = num(aIn), b = num(bIn);

            // No a*/b*? Fall back to chroma + hue angle
            if (a === null || b === null) {
                const C = num(cIn), H = num(hIn);
                if (C === null || H === null) { swatch.style.backgroundColor = '#FFFFFF'; return; }
                a = C * Math.cos(H * Math.PI / 180);
                b = C * Math.sin(H * Math.PI / 180);
            }
            if (L === null) { swatch.style.backgroundColor = '#FFFFFF'; return; }

            swatch.style.backgroundColor = labToHex(Math.min(100, Math.max(0, L)), a, b);
        }

        inputs.forEach(function (el) {
            // keep the swatch live while typing
            el.addEventListener('input', updateSwatch);

            // 4 decimals once the user leaves the field (e.g. 45.2 -> 45.2000)
            el.addEventListener('blur', function () {
                const v = parseFloat(el.value);
                el.value = Number.isFinite(v) ? v.toFixed(4) : '';
                updateSwatch();
            });

            // number fields also accept "e" and "+": block them
            el.addEventListener('keydown', function (e) {
                if (e.key === 'e' || e.key === 'E' || e.key === '+') e.preventDefault();
            });

            // format values loaded from an existing record
            const v = parseFloat(el.value);
            if (Number.isFinite(v)) el.value = v.toFixed(4);
        });

        updateSwatch();
    });
})();