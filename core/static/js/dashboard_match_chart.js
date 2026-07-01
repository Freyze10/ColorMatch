am5.ready(function() {

    let root = am5.Root.new("match_rematch_chart");

    // Hide logo
    if (root._logo) { root._logo.set("forceHidden", true); }

    root.setThemes([am5themes_Animated.new(root)]);

    // Make the chart's own canvas background transparent so the surrounding
    // .theme-card's background color (light or dark) shows through instead
    // of amCharts' default white background painted underneath the chart.
    root.container.set("background", am5.Rectangle.new(root, {
        fill: am5.color(0xffffff),
        fillOpacity: 0
    }));

    let chart = root.container.children.push(am5xy.XYChart.new(root, {
        panX: false,
        panY: false,
        wheelX: "none",
        wheelY: "zoomY", 
        paddingLeft: 0,
        layout: root.verticalLayout
    }));

    // === DATA (Full Year) ===
    let data = [
        { month: "Feb", matches: 55, rematches: 15 },
        { month: "Mar", matches: 80, rematches: 25 },
        { month: "Apr", matches: 45, rematches: 12 },
        { month: "May", matches: 60, rematches: 20 },
        { month: "Jun", matches: 70, rematches: 22 },
        { month: "Jul", matches: 85, rematches: 30 }
    ];

    // === COLOR PALETTE (theme-aware) ===
    function getThemeColors() {
        let isDark = document.body.classList.contains("dark-mode");
        return {
            isDark: isDark,
            axisLabel: isDark ? am5.color(0xcbd5e1) : am5.color(0x475569),
            gridLine: isDark ? am5.color(0x334155) : am5.color(0xe2e8f0),
            legendText: isDark ? am5.color(0xcbd5e1) : am5.color(0x64748b),
            bulletStroke: isDark ? am5.color(0x1e293b) : am5.color(0xffffff)
        };
    }

    // === Y-AXIS (LEFT: MONTHS) ===
    let yRenderer = am5xy.AxisRendererY.new(root, {
        minGridDistance: 1, // THE FIX: Setting this to 1 forces EVERY label to show
        inversed: true
    });

    yRenderer.labels.template.adapters.add("fill", function () {
        return getThemeColors().axisLabel;
    });

    // Clean look
    yRenderer.grid.template.set("visible", false);

    let yAxis = chart.yAxes.push(am5xy.CategoryAxis.new(root, {
        categoryField: "month",
        renderer: yRenderer
    }));

    yAxis.data.setAll(data);

    // === X-AXIS (BOTTOM: NUMBERS) ===
    let xRenderer = am5xy.AxisRendererX.new(root, {
        strokeOpacity: 0.1
    });

    xRenderer.labels.template.adapters.add("fill", function () {
        return getThemeColors().axisLabel;
    });

    xRenderer.grid.template.adapters.add("stroke", function () {
        return getThemeColors().gridLine;
    });

    let xAxis = chart.xAxes.push(am5xy.ValueAxis.new(root, {
        min: 0,
        renderer: xRenderer
    }));

    // === CLEAN VERTICAL SCROLLBAR ===
    let scrollbarY = am5.Scrollbar.new(root, {
        orientation: "vertical",
        marginLeft: 15
    });
    chart.set("scrollbarY", scrollbarY);
    scrollbarY.startGrip.set("forceHidden", true);
    scrollbarY.endGrip.set("forceHidden", true);
    scrollbarY.get("background").setAll({ fillOpacity: 0, strokeOpacity: 0 });

    // === TOOLTIP CURSOR ===
    let cursor = chart.set("cursor", am5xy.XYCursor.new(root, {
        behavior: "none",
        xAxis: xAxis,
        yAxis: yAxis
    }));
    cursor.lineX.set("visible", false);
    cursor.lineY.set("visible", false);

    // === SERIES 1: MATCHES ===
    let matchesSeries = chart.series.push(am5xy.ColumnSeries.new(root, {
        name: "Matches",
        xAxis: xAxis,
        yAxis: yAxis,
        valueXField: "matches",
        categoryYField: "month",
        sequencedInterpolation: true,
        tooltip: am5.Tooltip.new(root, {
            pointerOrientation: "horizontal",
            labelText: "[bold]{categoryY}[/]\n{name}: {valueX}" 
        })
    }));

    matchesSeries.columns.template.setAll({
        height: am5.p70, 
        cornerRadiusTR: 5,
        cornerRadiusBR: 5,
        strokeOpacity: 0,
        fill: am5.color(0x0d9488)
    });

    // === SERIES 2: REMATCHES ===
    let rematchesSeries = chart.series.push(am5xy.LineSeries.new(root, {
        name: "Rematches",
        xAxis: xAxis,
        yAxis: yAxis,
        valueXField: "rematches",
        categoryYField: "month",
        sequencedInterpolation: true,
        stroke: am5.color(0x0f172a),
        strokeWidth: 3,
        tooltip: am5.Tooltip.new(root, {
            pointerOrientation: "horizontal",
            labelText: "{name}: {valueX}"
        })
    }));

    let bullet = rematchesSeries.bullets.push(function() {
        return am5.Bullet.new(root, {
            sprite: am5.Circle.new(root, {
                radius: 5,
                fill: am5.color(0x0f172a),
                stroke: am5.color(0xffffff), // overridden by applyTheme() below
                strokeWidth: 2
            })
        });
    });

    matchesSeries.data.setAll(data);
    rematchesSeries.data.setAll(data);

    // === FORCED ZOOM TO BOTTOM 5 (LARGE BARS) ===
    // We use ready event to ensure the chart is fully calculated before zooming
    chart.events.on("ready", function() {
        yAxis.zoomToIndexes(data.length - 5, data.length);
    });

    // === LEGEND ===
    let legend = chart.children.push(am5.Legend.new(root, {
        centerX: am5.percent(50),
        x: am5.percent(50),
        marginTop: 15,
        marginBottom: 10
    }));

    legend.labels.template.adapters.add("fill", function () {
        return getThemeColors().legendText;
    });

    legend.data.setAll(chart.series.values);

    // === APPLY THEME COLORS (initial + on toggle) ===
    function applyTheme() {
        let colors = getThemeColors();

        // Update templates
        yRenderer.labels.template.setAll({
            fill: colors.axisLabel
        });

        xRenderer.labels.template.setAll({
            fill: colors.axisLabel
        });

        xRenderer.grid.template.setAll({
            stroke: colors.gridLine
        });

        legend.labels.template.setAll({
            fill: colors.legendText
        });

        // Force the axes to recreate their labels
        yAxis.markDirty();
        xAxis.markDirty();
        legend.markDirty();
    }

    applyTheme();

    // React live to dark/light mode toggle (dispatched by sidebar.js)
    document.addEventListener("themechange", applyTheme);

    chart.appear(1000, 100);
});