am5.ready(function() {

    // Ensure this ID matches the one in your dashboard.html
    let root = am5.Root.new("sample_order_chart"); 

    if (root._logo) { root._logo.set("forceHidden", true); }

    root.setThemes([am5themes_Animated.new(root)]);

    // Create chart
    let chart = root.container.children.push(am5percent.PieChart.new(root, {
        layout: root.verticalLayout,
        innerRadius: am5.percent(55) // Thinner donut for a more modern look
    }));

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
        textAlign: "center",
        centerY: am5.p50,
        centerX: am5.p50,
        text: "[#64748b fs14]Orders\n[bold fs30]0[/]"
    }));

    // Adapter to change label color based on Dark Mode
    label.adapters.add("fill", function(fill, target) {
        if (document.body.classList.contains("dark-mode")) {
            return am5.color(0xf8fafc); // Light color for dark mode
        }
        return am5.color(0x1e293b);     // Slate color for light mode
    });

    // Update label based on which slices are currently visible.
    // Rules:
    //   - Both visible        -> show Orders total
    //   - Only Orders visible -> show Orders total
    //   - Only Samples visible -> show Samples total
    //   - Neither visible     -> show Total 0
    function refreshLabel() {
        let samplesItem = series.dataItems.find(function(d) { return d.dataContext.category === "Samples"; });
        let ordersItem = series.dataItems.find(function(d) { return d.dataContext.category === "Orders"; });

        let samplesVisible = samplesItem.get("visible");
        let ordersVisible = ordersItem.get("visible");

        if (ordersVisible) {
            label.set("text", "[#64748b fs14]Orders\n[bold fs30]" + ordersItem.get("value") + "[/]");
        } else if (samplesVisible) {
            label.set("text", "[#64748b fs14]Samples\n[bold fs30]" + samplesItem.get("value") + "[/]");
        } else {
            label.set("text", "[#64748b fs14]Total\n[bold fs30]0[/]");
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

    legend.labels.template.setAll({
        fontSize: 14,
        fontWeight: "500",
        fill: am5.color(0x64748b) // Muted Slate
    });

    legend.valueLabels.template.setAll({
        fontSize: 14,
        fontWeight: "700",
        fill: am5.color(0x14b8a6) // Teal numbers in legend
    });

    legend.data.setAll(series.dataItems);

    // Animations
    series.appear(1000, 100);
    refreshLabel(); // Set initial text after data is loaded
});