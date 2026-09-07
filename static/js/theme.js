/* Runs before CSS: the server supplies the signed-in user's saved preference. */
(() => {
  const root = document.documentElement;
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  const graphElements = new Set();
  const originalLayouts = new WeakMap();
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
    apply, colors,
    newPlot(el, traces, base = {}, config) {
      originalLayouts.set(el, base);
      graphElements.add(el);
      return window.Plotly.newPlot(el, traces, layout(base), config);
    },
  };
  system.addEventListener("change", () => {
    if (root.dataset.appearance === "system") apply("system");
  });
  apply(root.dataset.appearance);
})();
