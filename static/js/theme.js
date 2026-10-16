/* Runs before CSS: the server supplies the signed-in user's saved preference. */
(() => {
  const root = document.documentElement;
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  const graphElements = new Set();
  const originalLayouts = new WeakMap();
  const originalTraces = new WeakMap();
  let preferences = {};
  const palettes = {
    "okabe-ito": ["#0072b2", "#e69f00", "#009e73", "#cc79a7", "#d55e00", "#56b4e9", "#f0e442", "#000000"],
    muted: ["#4878a8", "#ee854a", "#6acc64", "#d65f5f", "#956cb4", "#8c613c"],
  };
  const diverging = {
    "blue-orange": [[0, "#2166ac"], [0.5, "#f7f7f7"], [1, "#b35806"]],
    "purple-green": [[0, "#762a83"], [0.5, "#f7f7f7"], [1, "#1b7837"]],
  };
  function traceStyle(trace) {
    if (trace.type === "heatmap") {
      const scale = trace.zmid !== undefined
        ? diverging[preferences.diverging_palette]
        : {viridis: "Viridis", cividis: "Cividis"}[preferences.heatmap_palette];
      return { colorscale: scale || trace.colorscale };
    }
    const palette = palettes[preferences.plot_palette];
    const group = trace.meta?.cohortome_group;
    if (group === undefined) return {};
    const colour = index => palette[index % palette.length];
    if (Array.isArray(group)) {
      const key = trace.type === "pie" ? "colors" : "color";
      return { marker: {...trace.marker, [key]: palette ? group.map(colour) : trace.marker[key]} };
    }
    const style = {};
    if (trace.line) style.line = {...trace.line, color: palette ? colour(group) : trace.line.color};
    if (trace.marker) style.marker = {...trace.marker, color: palette ? colour(group) : trace.marker.color};
    return style;
  }
  function applyPalettes(settings) {
    preferences = settings;
    for (const el of graphElements) {
      if (!el.isConnected) { graphElements.delete(el); continue; }
      if (!el._fullLayout || !window.Plotly?.restyle) continue;
      (originalTraces.get(el) || []).forEach((trace, index) => {
        const style = traceStyle(trace);
        if (!Object.keys(style).length) return;
        // Restyle only colours: leave zoom, data, ordering and scale limits intact.
        const patch = Object.fromEntries(Object.entries(style).map(([key, value]) => [key, [value]]));
        Promise.resolve(window.Plotly.restyle(el, patch, [index])).catch(() => {});
      });
    }
  }
  function palettePreview(key, value) {
    const el = document.getElementById(`preview_${key}`);
    if (!el) return;
    const colours = key === "plot_palette" ? palettes[value]
      : key === "diverging_palette" ? diverging[value]?.map(stop => stop[1])
      : {viridis: ["#440154", "#31688e", "#35b779", "#fde725"], cividis: ["#00224e", "#575d6d", "#a59c74", "#fee838"]}[value];
    el.style.cssText = colours ? `height:12px;margin-top:8px;border-radius:4px;background:linear-gradient(to right,${colours.join(",")})` : "";
  }
  function colors() {
    const style = getComputedStyle(root);
    return { ink: style.getPropertyValue("--ink").trim(),
      muted: style.getPropertyValue("--muted").trim(),
      panel: root.dataset.theme === "dark" ? "#172435" : "#f8fbff",
      line: root.dataset.theme === "dark" ? "#34465c" : "#cbd5e1" };
  }
  function layout(base) {
    const c = colors();
    const themed = { ...base, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: c.panel,
      font: { ...base.font, color: c.ink },
      legend: { ...base.legend, font: { ...base.legend?.font, color: c.ink } },
      hoverlabel: { ...base.hoverlabel, bgcolor: c.panel, font: { ...base.hoverlabel?.font, color: c.ink } } };
    for (const key of new Set(["xaxis", "yaxis", ...Object.keys(base).filter(k => /^[xy]axis\d*$/.test(k))])) {
      const axis = base[key] || {};
      const title = typeof axis.title === "string" ? { text: axis.title } : axis.title;
      themed[key] = { ...axis, gridcolor: c.line, linecolor: c.line,
        tickfont: { ...axis.tickfont, color: c.muted },
        title: { ...title, font: { ...title?.font, color: c.muted } } };
    }
    return themed;
  }
  function apply(preference) {
    root.dataset.appearance = ["light", "dark", "system"].includes(preference) ? preference : "light";
    const theme = root.dataset.appearance === "system" ? (system.matches ? "dark" : "light") : root.dataset.appearance;
    if (root.dataset.theme === theme) return;
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    for (const el of graphElements) {
      if (!el.isConnected) { graphElements.delete(el); continue; }
      if (el._fullLayout && window.Plotly) {
        const update = layout(originalLayouts.get(el) || {});
        // Relayout only presentation fields: preserve zoom, selection and data.
        const patch = { paper_bgcolor: update.paper_bgcolor, plot_bgcolor: update.plot_bgcolor,
          "font.color": update.font.color, "legend.font.color": update.font.color,
          hoverlabel: update.hoverlabel };
        for (const key of Object.keys(update).filter(k => /^[xy]axis\d*$/.test(k))) {
          for (const prop of ["gridcolor", "linecolor", "tickfont"]) patch[`${key}.${prop}`] = update[key][prop];
          patch[`${key}.title.font.color`] = update.font.color;
        }
        Promise.resolve(window.Plotly.relayout(el, patch)).catch(() => {});
      }
    }
    document.querySelectorAll("[id]").forEach(el => {
      if (el._cy && !el._cy.destroyed()) {
        const c = colors();
        el._cy.style().selector("node, edge").style({ color: c.ink })
          .selector("edge").style({ "text-background-color": c.panel }).update();
      }
    });
  }
  window.CohortomeTheme = {
    apply, colors, applyPalettes, palettePreview,
    newPlot(el, traces, base = {}, config) {
      originalLayouts.set(el, base);
      originalTraces.set(el, structuredClone(traces));
      graphElements.add(el);
      const custom = [preferences.plot_palette, preferences.heatmap_palette, preferences.diverging_palette].some(value => value && value !== "default");
      return window.Plotly.newPlot(el, custom ? traces.map(trace => ({...trace, ...traceStyle(trace)})) : traces, layout(base), config);
    },
  };
  system.addEventListener("change", () => {
    if (root.dataset.appearance === "system") apply("system");
  });
  apply(root.dataset.appearance);
})();
