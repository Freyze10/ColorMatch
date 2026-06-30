am5.ready(function() {

    // 1. Unique ID to prevent collisions
    var donutRoot = am5.Root.new("sample_order_chart"); 

    if (donutRoot._logo) { donutRoot._logo.set("forceHidden", true); }

    donutRoot.setThemes([am5themes_Animated.new(donutRoot)]);

    // 2. Create Donut Chart
    var donutChart = donutRoot.container.children.push(am5percent.PieChart.new(donutRoot, {
        layout: donutRoot.verticalLayout,
        innerRadius: am5.percent(60) 
    }));

    // 3. Data
    var data = [{
        category: "Samples",
        value: 325,
        sliceSettings: { fill: am5.color(0x14b8a6) } // Teal
    }, {
        category: "Orders",
        value: 175,
        sliceSettings: { fill: am5.color(0x1e293b) } // Slate
    }];

    // 4. Create Series
    var series = donutChart.series.push(am5percent.PieSeries.new(donutRoot, {
        name: "Series",
        valueField: "value",
        categoryField: "category",
        alignLabels: false
    }));

    series.slices.template.setAll({
        strokeOpacity: 0,
        templateField: "sliceSettings",
        fillGradient: am5.RadialGradient.new(donutRoot, {
            stops: [{ opacity: 1 }, { opacity: 0.8 }, { opacity: 0.5, color: am5.color(0x000000) }]
        })
    });

    series.labels.template.set("forceHidden", true);
    series.ticks.template.set("forceHidden", true);

    // 5. THE DYNAMIC CENTER LABEL
    var label = donutChart.seriesContainer.children.push(am5.Label.new(donutRoot, {
        textAlign: "center",
        centerY: am5.p50,
        centerX: am5.p50,
        text: "" // Initially empty, filled by refreshLabel()
    }));

    // Theme-aware color for the text
    label.adapters.add("fill", function() {
        return document.body.classList.contains("dark-mode") ? am5.color(0xf8fafc) : am5.color(0x1e293b);
    });

    // --- LOGIC: SWITCH BETWEEN ORDERS AND SAMPLES ---
    function refreshLabel() {
        var samplesItem = series.dataItems[0]; 
        var ordersItem = series.dataItems[1];

        // Logic Priority:
        // 1. If Orders is visible -> Show Orders
        // 2. If Orders is hidden but Samples is visible -> Show Samples
        // 3. If both are hidden -> Show Total 0

        if (ordersItem && !ordersItem.get("hidden")) {
            label.set("text", "[#64748b fs14]Orders\n[bold fs30]" + ordersItem.get("value") + "[/]");
        } 
        else if (samplesItem && !samplesItem.get("hidden")) {
            label.set("text", "[#64748b fs14]Samples\n[bold fs30]" + samplesItem.get("value") + "[/]");
        } 
        else {
            label.set("text", "[#64748b fs14]Total\n[bold fs30]0[/]");
        }
    }

    // Trigger update when legend is toggled
    series.slices.template.events.on("visible", refreshLabel);
    series.slices.template.events.on("hidden", refreshLabel);
    
    // Trigger update when data is first loaded
    series.events.on("datavalidated", refreshLabel);

    series.data.setAll(data);

    // 6. LEGEND
    var legend = donutChart.children.push(am5.Legend.new(donutRoot, {
        centerX: am5.p50, x: am5.p50, marginTop: 15
    }));

    legend.labels.template.setAll({ fontSize: 14, fill: am5.color(0x64748b) });
    legend.valueLabels.template.setAll({ fontSize: 14, fontWeight: "700", fill: am5.color(0x14b8a6) });
    
    legend.data.setAll(series.dataItems);
    
    series.appear(1000, 100);
});