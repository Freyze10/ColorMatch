am5.ready(function() {

    // Ensure this ID matches the one in your dashboard.html
    let root = am5.Root.new("sample_order_chart"); 

    if (root._logo) { root._logo.set("forceHidden", true); }

    root.setThemes([am5themes_Animated.new(root)]);

    // Make the chart's own canvas background transparent
    root.container.set("background", am5.Rectangle.new(root, {
        fill: am5.color(0xffffff),
        fillOpacity: 0
    }));

    // Create chart
    let chart = root.container.children.push(am5percent.PieChart.new(root, {
        layout: root.verticalLayout,
        innerRadius: am5.percent(55) 
    }));

    // === COLOR PALETTE (theme-aware) ===
    function getThemeColors() {
        let isDark = document.body.classList.contains("dark-mode");

        return {
            isDark: isDark,
            labelMuted: isDark ? am5.color(0xCBD5E1) : am5.color(0x64748B),
            labelMain: isDark ? am5.color(0xF8FAFC) : am5.color(0x1E293B),
            legendText: isDark ? am5.color(0xCBD5E1) : am5.color(0x64748B),
            legendValue: am5.color(0x14B8A6),
            sliceStroke: isDark ? am5.color(0x0F172A) : am5.color(0xFFFFFF)
        };
    }

    // === DATA ===
    let data = [{
        category: "Samples",
        value: 325,
        color: am5.color(0x14b8a6) 
    }, {
        category: "Orders",
        value: 175,
        color: am5.color(0x1e293b) 
    }];

    // Create Series
    let series = chart.series.push(am5percent.PieSeries.new(root, {
        name: "Series",
        valueField: "value",
        categoryField: "category",
        alignLabels: false
    }));

    // --- GRADIENT & SLICE DESIGN ---
    series.slices.template.setAll({
        strokeOpacity: 0,
        fillGradient: am5.RadialGradient.new(root, {
            stops: [
                { opacity: 1 },
                { opacity: 0.6, color: am5.color(0x8C8A89) }, 
                { opacity: 0.9 },
            ]
        })
    });

    series.slices.template.adapters.add("fill", function(fill, target) {
        return target.dataItem.dataContext.color;
    });

    series.labels.template.set("forceHidden", true);
    series.ticks.template.set("forceHidden", true);

    // --- THEME-AWARE CENTER LABEL ---
    let label = chart.seriesContainer.children.push(am5.Label.new(root, {
        centerX: am5.percent(50),
        centerY: am5.percent(50),
        textAlign: "center",
        populateText: true,
        fontSize: 16
    }));

    // Logic for visibility remains exactly the same as yours, 
    // but we added the dynamic 'color' style to the HTML.
    function refreshLabel() {
        let colors = getThemeColors();
        let hexColor = colors.labelMain.toCSSHex(); // Converts am5 color to #FFFFFF etc.

        let samplesItem = series.dataItems.find(d => d.dataContext.category === "Samples");
        let ordersItem  = series.dataItems.find(d => d.dataContext.category === "Orders");

        let samplesVisible = samplesItem.get("visible");
        let ordersVisible  = ordersItem.get("visible");

        if (ordersVisible) {
            label.set("html",
                `<div style='text-align:center; color: ${hexColor};'>` +
                "<div style='font-size:14px;'>Orders</div>" +
                "<div style='font-size:30px;font-weight:bold;'>" +
                ordersItem.get("value") +
                "</div></div>"
            );
        } else if (samplesVisible) {
            label.set("html",
                `<div style='text-align:center; color: ${hexColor};'>` +
                "<div style='font-size:14px;'>Samples</div>" +
                "<div style='font-size:30px;font-weight:bold;'>" +
                samplesItem.get("value") +
                "</div></div>"
            );
        } else {
            label.set("html",
                `<div style='text-align:center; color: ${hexColor};'>` +
                "<div style='font-size:14px;'>Total</div>" +
                "<div style='font-size:30px;font-weight:bold;'>0</div>" +
                "</div>"
            );
        }
    }

    series.onPrivate("valueSum", refreshLabel);
    series.data.setAll(data);

    // --- LEGEND ---
    let legend = chart.children.push(am5.Legend.new(root, {
        centerX: am5.percent(50),
        x: am5.percent(50),
        marginTop: 15,
        marginBottom: 10
    }));

    legend.data.setAll(series.dataItems);

    // --- APPLY THEME COLORS ---
    function applyTheme() {
        let colors = getThemeColors();
        
        legend.labels.template.setAll({
            fontSize: 14,
            fontWeight: "500",
            fill: colors.legendText
        });

        legend.valueLabels.template.setAll({
            fontSize: 14,
            fontWeight: "700",
            fill: colors.legendValue
        });

        series.slices.template.setAll({
            stroke: colors.sliceStroke,
            strokeOpacity: 1,
            strokeWidth: 2
        });

        // This forces the HTML label to re-render with the new color
        refreshLabel();
    }

    applyTheme();

    // Listen for the theme change event
    document.addEventListener("themechange", applyTheme);

    // Watch the body class as a fallback (if themechange event doesn't fire)
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.attributeName === 'class') { applyTheme(); }
        });
    });
    observer.observe(document.body, { attributes: true });

    series.appear(1000, 100);
});