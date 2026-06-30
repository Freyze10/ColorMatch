am5.ready(function() {

    // Ensure this ID matches the one in your dashboard.html
    let root = am5.Root.new("sample_order_chart"); 

    if (root._logo) { root._logo.set("forceHidden", true); }

    root.setThemes([am5themes_Animated.new(root)]);

    // Make the chart's own canvas background transparent so the surrounding
    // .theme-card's background color (light or dark) shows through instead
    // of amCharts' default white background painted underneath the chart.
    root.container.set("background", am5.Rectangle.new(root, {
        fill: am5.color(0xffffff),
        fillOpacity: 0
    }));

    // Create chart
    let chart = root.container.children.push(am5percent.PieChart.new(root, {
        layout: root.verticalLayout,
        innerRadius: am5.percent(55) // Thinner donut for a more modern look
    }));

    // === COLOR PALETTE (theme-aware) ===
    // Slice colors stay the same in both themes (teal/slate brand colors read
    // fine on both backgrounds), but text/label colors need to flip.
    function getThemeColors() {
        let isDark = document.body.classList.contains("dark-mode");

        return {
            isDark: isDark,

            // Center label (Orders/Samples/Total)
            labelMuted: isDark
                ? am5.color(0xCBD5E1)    // Light gray
                : am5.color(0x64748B),   // Slate gray

            // Center value
            labelMain: isDark
                ? am5.color(0xF8FAFC)    // Almost white
                : am5.color(0x1E293B),   // Dark slate

            legendText: isDark
                ? am5.color(0xCBD5E1)
                : am5.color(0x64748B),

            legendValue: am5.color(0x14B8A6),

            sliceStroke: isDark
                ? am5.color(0x0F172A)
                : am5.color(0xFFFFFF)
        };
    }

    // === DATA WITH THEME COLORS ===
    let data = [{
        category: "Samples",
        value: 325,
        color: am5.color(0x14b8a6) // Vibrant Teal
    }, {
        category: "Orders",
        value: 175,
        color: am5.color(0x1e293b) // Corporate Slate
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
                { opacity: 0.6, color: am5.color(0x8C8A89) }, // Darken edges slightly
                { opacity: 0.9 },
            ]
        })
    });

    // Match slice colors to data colors
    series.slices.template.adapters.add("fill", function(fill, target) {
        return target.dataItem.dataContext.color;
    });

    // Hide default labels/ticks
    series.labels.template.set("forceHidden", true);
    series.ticks.template.set("forceHidden", true);

    // --- THEME-AWARE CENTER LABEL ---
    let label = chart.seriesContainer.children.push(am5.Label.new(root, {
        centerX: am5.percent(50),
        centerY: am5.percent(50),
        textAlign: "center",
        populateText: true,
        fontSize: 16,
        fill: getThemeColors().labelMain
    }));

    // Update label based on which slices are currently visible.
    // Rules:
    //   - Both visible        -> show Orders total
    //   - Only Orders visible -> show Orders total
    //   - Only Samples visible -> show Samples total
    //   - Neither visible     -> show Total 0
    function refreshLabel() {

        let samplesItem = series.dataItems.find(d => d.dataContext.category === "Samples");
        let ordersItem  = series.dataItems.find(d => d.dataContext.category === "Orders");

        let samplesVisible = samplesItem.get("visible");
        let ordersVisible  = ordersItem.get("visible");

        if (ordersVisible) {

            label.set("html",
                "<div style='text-align:center;'>" +
                "<div style='font-size:14px;'>Orders</div>" +
                "<div style='font-size:30px;font-weight:bold;'>" +
                ordersItem.get("value") +
                "</div></div>"
            );

        } else if (samplesVisible) {

            label.set("html",
                "<div style='text-align:center;'>" +
                "<div style='font-size:14px;'>Samples</div>" +
                "<div style='font-size:30px;font-weight:bold;'>" +
                samplesItem.get("value") +
                "</div></div>"
            );

        } else {

            label.set("html",
                "<div style='text-align:center;'>" +
                "<div style='font-size:14px;'>Total</div>" +
                "<div style='font-size:30px;font-weight:bold;'>0</div>" +
                "</div>"
            );

        }
    }

    // valueSum recalculates automatically whenever a slice is toggled via the
    // legend, so hooking onto it is a reliable trigger for refreshing the label.
    series.onPrivate("valueSum", refreshLabel);

    // Set Data
    series.data.setAll(data);

    // --- LEGEND STYLING ---
    let legend = chart.children.push(am5.Legend.new(root, {
        centerX: am5.percent(50),
        x: am5.percent(50),
        marginTop: 15,
        marginBottom: 10
    }));

    legend.data.setAll(series.dataItems);

    // --- APPLY THEME COLORS (initial + on toggle) ---
    function applyTheme() {
        let colors = getThemeColors();
        label.set("fill", colors.labelMain);
        
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

        series.slices.template.set("stroke", colors.sliceStroke);
        series.slices.template.set("strokeOpacity", 1);
        series.slices.template.set("strokeWidth", 2);

        refreshLabel();
    }

    applyTheme();

    // React live to dark/light mode toggle (dispatched by sidebar.js)
    document.addEventListener("themechange", applyTheme);

    // Animations
    series.appear(1000, 100);
});