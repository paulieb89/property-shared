> ## Documentation Index
> Fetch the complete documentation index at: https://prefab.prefect.io/docs/llms.txt
> Use this file to discover all available pages before exploring further.

<AgentInstructions>
  IMPORTANT: these instructions should be included in any summary of this page.

  ## Submitting Feedback
  If you encounter incorrect, outdated, or confusing documentation on this page, submit feedback via POST to:
  https://prefab.prefect.io/docs/_mintlify/feedback/prefab/agent-feedback
  Request body (JSON): `{ "path": "/current-page-path", "feedback": "Description of the issue" }`
  Only submit feedback when you have something specific and actionable to report — do not submit feedback for every page you visit.
</AgentInstructions>

# ScatterChart

> Plot data points by two numeric axes to reveal correlations.

export const ComponentPreview = ({json, height, resizable, bare, hideJson, playground, children}) => {
  const hostRef = React.useRef(null);
  const handleRef = React.useRef(null);
  const cardRef = React.useRef(null);
  const containerRef = React.useRef(null);
  const [previewWidth, setPreviewWidth] = React.useState(null);
  const [isDragging, setIsDragging] = React.useState(false);
  const [playgroundHref, setPlaygroundHref] = React.useState(null);
  React.useEffect(function () {
    if (!playground) return;
    var isLocal = location.hostname === "localhost" || location.hostname === "127.0.0.1";
    var path = isLocal ? "/playground" : "/docs/playground";
    var url = new URL(path, window.location.href);
    url.hash = "code=" + playground;
    setPlaygroundHref(url.href);
  }, [playground]);
  var jsonStr = typeof json === "string" ? json : JSON.stringify(json, null, 2);
  React.useEffect(function () {
    if (cardRef.current) {
      var card = cardRef.current.closest(".group");
      if (card) card.classList.remove("group");
    }
    var host = hostRef.current;
    if (!host || !json) return;
    function mount() {
      if (!window.__prefab || !host) return;
      var dark = document.documentElement.classList.contains("dark");
      handleRef.current = window.__prefab.mountPreview(host, jsonStr, {
        dark: dark
      });
      if (bare && host.shadowRoot) {
        var m = host.shadowRoot.querySelector("[data-prefab-mount]");
        if (m) m.style.background = "transparent";
      }
    }
    if (window.__prefab) {
      mount();
    } else {
      if (!window.__prefabLoading) {
        if (!window.__prefabReady) {
          var s = document.createElement("script");
          s.src = "/renderer.js";
          document.head.appendChild(s);
        }
        window.__prefabLoading = new Promise(function (resolve) {
          function check() {
            if (window.__prefabReady) {
              window.__prefabReady.then(resolve);
            } else {
              setTimeout(check, 10);
            }
          }
          check();
        });
      }
      window.__prefabLoading.then(mount);
    }
    var observer = new MutationObserver(function () {
      var dark = document.documentElement.classList.contains("dark");
      if (handleRef.current) handleRef.current.setDark(dark);
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"]
    });
    return function () {
      observer.disconnect();
      if (handleRef.current) {
        handleRef.current.unmount();
        handleRef.current = null;
      }
    };
  }, [json]);
  function startResize(e) {
    e.preventDefault();
    var startX = e.clientX;
    var startW = hostRef.current ? hostRef.current.offsetWidth : 0;
    var maxW = containerRef.current ? containerRef.current.offsetWidth - 10 : startW;
    setIsDragging(true);
    function onMove(ev) {
      var w = Math.max(260, Math.min(startW + (ev.clientX - startX), maxW));
      setPreviewWidth(w);
    }
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      setIsDragging(false);
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }
  if (bare) {
    return <div ref={hostRef} />;
  }
  if (resizable) {
    return <Card>
        <div ref={cardRef} />
        <div ref={containerRef} style={{
      display: "flex",
      position: "relative",
      overflow: "hidden"
    }}>
          <div ref={hostRef} style={{
      flex: previewWidth ? "none" : 1,
      width: previewWidth ? previewWidth + "px" : undefined,
      minWidth: 0
    }} />
          <div onMouseDown={startResize} style={{
      width: "14px",
      flexShrink: 0,
      cursor: "col-resize",
      background: isDragging ? "var(--border, #e5e7eb)" : "color-mix(in srgb, var(--border, #e5e7eb) 40%, transparent)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      transition: "background 0.15s",
      userSelect: "none"
    }}>
            <svg width="6" height="24" style={{
      opacity: 0.5
    }}>
              <circle cx="2" cy="4" r="1.2" fill="currentColor" />
              <circle cx="2" cy="9" r="1.2" fill="currentColor" />
              <circle cx="2" cy="14" r="1.2" fill="currentColor" />
              <circle cx="2" cy="19" r="1.2" fill="currentColor" />
              <circle cx="5" cy="4" r="1.2" fill="currentColor" />
              <circle cx="5" cy="9" r="1.2" fill="currentColor" />
              <circle cx="5" cy="14" r="1.2" fill="currentColor" />
              <circle cx="5" cy="19" r="1.2" fill="currentColor" />
            </svg>
          </div>
          <div style={{
      flex: previewWidth ? 1 : "0 0 24px",
      minWidth: "24px",
      background: "repeating-linear-gradient(-45deg, transparent, transparent 3px, var(--border, #e5e7eb) 3px, var(--border, #e5e7eb) 4px)",
      opacity: 0.4
    }} />
          {previewWidth && <div style={{
      position: "absolute",
      bottom: "8px",
      right: "8px",
      background: "var(--background, white)",
      border: "1px solid var(--border, #e5e7eb)",
      borderRadius: "4px",
      padding: "1px 6px",
      fontSize: "11px",
      fontFamily: "monospace",
      color: "var(--muted-foreground, #6b7280)",
      pointerEvents: "none"
    }}>
              {previewWidth}px
            </div>}
        </div>
        {playgroundHref && <div style={{
      display: "flex",
      justifyContent: "flex-end",
      padding: "4px 0 8px"
    }}>
            <a href={playgroundHref} target="_blank" rel="noopener noreferrer" style={{
      fontSize: "11px",
      opacity: 0.4,
      textDecoration: "none",
      textDecorationLine: "none",
      borderBottom: "none",
      boxShadow: "none",
      display: "inline-flex",
      alignItems: "center",
      gap: "3px",
      transition: "opacity 0.15s",
      fontWeight: 400
    }} onMouseOver={function (e) {
      e.currentTarget.style.opacity = "0.6";
    }} onMouseOut={function (e) {
      e.currentTarget.style.opacity = "0.4";
    }}>
              Edit in Playground
              <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 3h6v6" /><path d="M10 14 21 3" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></svg>
            </a>
          </div>}
        <div style={{
      marginBottom: "-2rem"
    }}>{children}</div>
      </Card>;
  }
  return <Card>
      <div ref={cardRef} />
      <div ref={hostRef} />
      {playgroundHref && <div style={{
    display: "flex",
    justifyContent: "flex-end",
    padding: "4px 0 8px"
  }}>
          <a href={playgroundHref} target="_blank" rel="noopener noreferrer" style={{
    fontSize: "11px",
    opacity: 0.4,
    textDecoration: "none",
    textDecorationLine: "none",
    borderBottom: "none",
    boxShadow: "none",
    display: "inline-flex",
    alignItems: "center",
    gap: "3px",
    transition: "opacity 0.15s",
    fontWeight: 400
  }} onMouseOver={function (e) {
    e.currentTarget.style.opacity = "0.6";
  }} onMouseOut={function (e) {
    e.currentTarget.style.opacity = "0.4";
  }}>
            Edit in Playground
            <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 3h6v6" /><path d="M10 14 21 3" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></svg>
          </a>
        </div>}
      <div style={{
    marginBottom: "-2rem"
  }}>{children}</div>
    </Card>;
};

ScatterChart plots data as individual points on a cartesian plane, positioned by their `x_axis` and `y_axis` values. Where bar charts compare categories and line charts show change over time, scatter charts reveal relationships between two continuous variables -- whether they're correlated, clustered, or independent.

## Basic Usage

Every scatter chart needs three things: the data, a series definition, and the two axis mappings. The `data` is a list of dicts where each dict is a point. `x_axis` and `y_axis` name the fields that position each point on the chart. The `data_key` on `ChartSeries` is an identifier for the series -- it controls color and legend display.

<ComponentPreview json={{"view":{"type":"ScatterChart","data":[{"hours":2,"score":45},{"hours":4,"score":62},{"hours":5,"score":58},{"hours":6,"score":71},{"hours":8,"score":78},{"hours":10,"score":85},{"hours":12,"score":82},{"hours":14,"score":91},{"hours":16,"score":88},{"hours":18,"score":95}],"series":[{"dataKey":"students","label":"Students"}],"xAxis":"hours","yAxis":"score","height":300,"showLegend":true,"showTooltip":true,"animate":true,"showGrid":true}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cy5jaGFydHMgaW1wb3J0IFNjYXR0ZXJDaGFydCwgQ2hhcnRTZXJpZXMKCmRhdGEgPSBbCiAgICB7ImhvdXJzIjogMiwgInNjb3JlIjogNDV9LAogICAgeyJob3VycyI6IDQsICJzY29yZSI6IDYyfSwKICAgIHsiaG91cnMiOiA1LCAic2NvcmUiOiA1OH0sCiAgICB7ImhvdXJzIjogNiwgInNjb3JlIjogNzF9LAogICAgeyJob3VycyI6IDgsICJzY29yZSI6IDc4fSwKICAgIHsiaG91cnMiOiAxMCwgInNjb3JlIjogODV9LAogICAgeyJob3VycyI6IDEyLCAic2NvcmUiOiA4Mn0sCiAgICB7ImhvdXJzIjogMTQsICJzY29yZSI6IDkxfSwKICAgIHsiaG91cnMiOiAxNiwgInNjb3JlIjogODh9LAogICAgeyJob3VycyI6IDE4LCAic2NvcmUiOiA5NX0sCl0KClNjYXR0ZXJDaGFydCgKICAgIGRhdGE9ZGF0YSwKICAgIHNlcmllcz1bQ2hhcnRTZXJpZXMoZGF0YV9rZXk9InN0dWRlbnRzIiwgbGFiZWw9IlN0dWRlbnRzIildLAogICAgeF9heGlzPSJob3VycyIsCiAgICB5X2F4aXM9InNjb3JlIiwKKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components.charts import ScatterChart, ChartSeries

    data = [
        {"hours": 2, "score": 45},
        {"hours": 4, "score": 62},
        {"hours": 5, "score": 58},
        {"hours": 6, "score": 71},
        {"hours": 8, "score": 78},
        {"hours": 10, "score": 85},
        {"hours": 12, "score": 82},
        {"hours": 14, "score": 91},
        {"hours": 16, "score": 88},
        {"hours": 18, "score": 95},
    ]

    ScatterChart(
        data=data,
        series=[ChartSeries(data_key="students", label="Students")],
        x_axis="hours",
        y_axis="score",
    )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "ScatterChart",
        "data": [
          {"hours": 2, "score": 45},
          {"hours": 4, "score": 62},
          {"hours": 5, "score": 58},
          {"hours": 6, "score": 71},
          {"hours": 8, "score": 78},
          {"hours": 10, "score": 85},
          {"hours": 12, "score": 82},
          {"hours": 14, "score": 91},
          {"hours": 16, "score": 88},
          {"hours": 18, "score": 95}
        ],
        "series": [{"dataKey": "students", "label": "Students"}],
        "xAxis": "hours",
        "yAxis": "score",
        "height": 300,
        "showLegend": true,
        "showTooltip": true,
        "animate": true,
        "showGrid": true
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Multiple Series

To plot multiple groups on the same axes, add a `_series` field to each data point that matches the `data_key` of its series. Each series gets its own color from the theme palette and appears as a separate entry in the legend. This is useful for comparing distributions across categories -- here, two classes of students plotted by study hours vs. test scores.

<ComponentPreview json={{"view":{"type":"ScatterChart","data":[{"hours":2,"score":45,"_series":"morning"},{"hours":5,"score":58,"_series":"morning"},{"hours":8,"score":78,"_series":"morning"},{"hours":10,"score":85,"_series":"morning"},{"hours":14,"score":91,"_series":"morning"},{"hours":18,"score":95,"_series":"morning"},{"hours":3,"score":52,"_series":"evening"},{"hours":6,"score":60,"_series":"evening"},{"hours":9,"score":68,"_series":"evening"},{"hours":11,"score":72,"_series":"evening"},{"hours":15,"score":80,"_series":"evening"},{"hours":17,"score":84,"_series":"evening"}],"series":[{"dataKey":"morning","label":"Morning Class","color":"#2563eb"},{"dataKey":"evening","label":"Evening Class","color":"#e76e50"}],"xAxis":"hours","yAxis":"score","height":300,"showLegend":true,"showTooltip":true,"animate":true,"showGrid":true}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cy5jaGFydHMgaW1wb3J0IFNjYXR0ZXJDaGFydCwgQ2hhcnRTZXJpZXMKCmRhdGEgPSBbCiAgICB7ImhvdXJzIjogMiwgInNjb3JlIjogNDUsICJfc2VyaWVzIjogIm1vcm5pbmcifSwKICAgIHsiaG91cnMiOiA1LCAic2NvcmUiOiA1OCwgIl9zZXJpZXMiOiAibW9ybmluZyJ9LAogICAgeyJob3VycyI6IDgsICJzY29yZSI6IDc4LCAiX3NlcmllcyI6ICJtb3JuaW5nIn0sCiAgICB7ImhvdXJzIjogMTAsICJzY29yZSI6IDg1LCAiX3NlcmllcyI6ICJtb3JuaW5nIn0sCiAgICB7ImhvdXJzIjogMTQsICJzY29yZSI6IDkxLCAiX3NlcmllcyI6ICJtb3JuaW5nIn0sCiAgICB7ImhvdXJzIjogMTgsICJzY29yZSI6IDk1LCAiX3NlcmllcyI6ICJtb3JuaW5nIn0sCiAgICB7ImhvdXJzIjogMywgInNjb3JlIjogNTIsICJfc2VyaWVzIjogImV2ZW5pbmcifSwKICAgIHsiaG91cnMiOiA2LCAic2NvcmUiOiA2MCwgIl9zZXJpZXMiOiAiZXZlbmluZyJ9LAogICAgeyJob3VycyI6IDksICJzY29yZSI6IDY4LCAiX3NlcmllcyI6ICJldmVuaW5nIn0sCiAgICB7ImhvdXJzIjogMTEsICJzY29yZSI6IDcyLCAiX3NlcmllcyI6ICJldmVuaW5nIn0sCiAgICB7ImhvdXJzIjogMTUsICJzY29yZSI6IDgwLCAiX3NlcmllcyI6ICJldmVuaW5nIn0sCiAgICB7ImhvdXJzIjogMTcsICJzY29yZSI6IDg0LCAiX3NlcmllcyI6ICJldmVuaW5nIn0sCl0KClNjYXR0ZXJDaGFydCgKICAgIGRhdGE9ZGF0YSwKICAgIHNlcmllcz1bCiAgICAgICAgQ2hhcnRTZXJpZXMoZGF0YV9rZXk9Im1vcm5pbmciLCBsYWJlbD0iTW9ybmluZyBDbGFzcyIsIGNvbG9yPSIjMjU2M2ViIiksCiAgICAgICAgQ2hhcnRTZXJpZXMoZGF0YV9rZXk9ImV2ZW5pbmciLCBsYWJlbD0iRXZlbmluZyBDbGFzcyIsIGNvbG9yPSIjZTc2ZTUwIiksCiAgICBdLAogICAgeF9heGlzPSJob3VycyIsCiAgICB5X2F4aXM9InNjb3JlIiwKICAgIHNob3dfbGVnZW5kPVRydWUsCikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components.charts import ScatterChart, ChartSeries

    data = [
        {"hours": 2, "score": 45, "_series": "morning"},
        {"hours": 5, "score": 58, "_series": "morning"},
        {"hours": 8, "score": 78, "_series": "morning"},
        {"hours": 10, "score": 85, "_series": "morning"},
        {"hours": 14, "score": 91, "_series": "morning"},
        {"hours": 18, "score": 95, "_series": "morning"},
        {"hours": 3, "score": 52, "_series": "evening"},
        {"hours": 6, "score": 60, "_series": "evening"},
        {"hours": 9, "score": 68, "_series": "evening"},
        {"hours": 11, "score": 72, "_series": "evening"},
        {"hours": 15, "score": 80, "_series": "evening"},
        {"hours": 17, "score": 84, "_series": "evening"},
    ]

    ScatterChart(
        data=data,
        series=[
            ChartSeries(data_key="morning", label="Morning Class", color="#2563eb"),
            ChartSeries(data_key="evening", label="Evening Class", color="#e76e50"),
        ],
        x_axis="hours",
        y_axis="score",
        show_legend=True,
    )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "ScatterChart",
        "data": [
          {"hours": 2, "score": 45, "_series": "morning"},
          {"hours": 5, "score": 58, "_series": "morning"},
          {"hours": 8, "score": 78, "_series": "morning"},
          {"hours": 10, "score": 85, "_series": "morning"},
          {"hours": 14, "score": 91, "_series": "morning"},
          {"hours": 18, "score": 95, "_series": "morning"},
          {"hours": 3, "score": 52, "_series": "evening"},
          {"hours": 6, "score": 60, "_series": "evening"},
          {"hours": 9, "score": 68, "_series": "evening"},
          {"hours": 11, "score": 72, "_series": "evening"},
          {"hours": 15, "score": 80, "_series": "evening"},
          {"hours": 17, "score": 84, "_series": "evening"}
        ],
        "series": [
          {"dataKey": "morning", "label": "Morning Class", "color": "#2563eb"},
          {"dataKey": "evening", "label": "Evening Class", "color": "#e76e50"}
        ],
        "xAxis": "hours",
        "yAxis": "score",
        "height": 300,
        "showLegend": true,
        "showTooltip": true,
        "animate": true,
        "showGrid": true
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Bubble Chart

Set `z_axis` to a numeric field to scale each point's size proportionally, turning the scatter into a bubble chart. This encodes a third dimension directly in the visualization -- larger bubbles represent higher values of the z-axis field. Useful for comparing entities that have three measurable attributes.

<ComponentPreview json={{"view":{"type":"ScatterChart","data":[{"revenue":120,"growth":8,"employees":50},{"revenue":340,"growth":12,"employees":150},{"revenue":210,"growth":5,"employees":80},{"revenue":580,"growth":18,"employees":300},{"revenue":90,"growth":25,"employees":20},{"revenue":450,"growth":10,"employees":200},{"revenue":160,"growth":30,"employees":35},{"revenue":720,"growth":7,"employees":400}],"series":[{"dataKey":"companies","label":"Companies"}],"xAxis":"revenue","yAxis":"growth","zAxis":"employees","height":300,"showLegend":true,"showTooltip":true,"animate":true,"showGrid":true}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cy5jaGFydHMgaW1wb3J0IFNjYXR0ZXJDaGFydCwgQ2hhcnRTZXJpZXMKClNjYXR0ZXJDaGFydCgKICAgIGRhdGE9WwogICAgICAgIHsicmV2ZW51ZSI6IDEyMCwgImdyb3d0aCI6IDgsICJlbXBsb3llZXMiOiA1MH0sCiAgICAgICAgeyJyZXZlbnVlIjogMzQwLCAiZ3Jvd3RoIjogMTIsICJlbXBsb3llZXMiOiAxNTB9LAogICAgICAgIHsicmV2ZW51ZSI6IDIxMCwgImdyb3d0aCI6IDUsICJlbXBsb3llZXMiOiA4MH0sCiAgICAgICAgeyJyZXZlbnVlIjogNTgwLCAiZ3Jvd3RoIjogMTgsICJlbXBsb3llZXMiOiAzMDB9LAogICAgICAgIHsicmV2ZW51ZSI6IDkwLCAiZ3Jvd3RoIjogMjUsICJlbXBsb3llZXMiOiAyMH0sCiAgICAgICAgeyJyZXZlbnVlIjogNDUwLCAiZ3Jvd3RoIjogMTAsICJlbXBsb3llZXMiOiAyMDB9LAogICAgICAgIHsicmV2ZW51ZSI6IDE2MCwgImdyb3d0aCI6IDMwLCAiZW1wbG95ZWVzIjogMzV9LAogICAgICAgIHsicmV2ZW51ZSI6IDcyMCwgImdyb3d0aCI6IDcsICJlbXBsb3llZXMiOiA0MDB9LAogICAgXSwKICAgIHNlcmllcz1bQ2hhcnRTZXJpZXMoZGF0YV9rZXk9ImNvbXBhbmllcyIsIGxhYmVsPSJDb21wYW5pZXMiKV0sCiAgICB4X2F4aXM9InJldmVudWUiLAogICAgeV9heGlzPSJncm93dGgiLAogICAgel9heGlzPSJlbXBsb3llZXMiLAopCg">
  <CodeGroup>
    ```python Python {14} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components.charts import ScatterChart, ChartSeries

    ScatterChart(
        data=[
            {"revenue": 120, "growth": 8, "employees": 50},
            {"revenue": 340, "growth": 12, "employees": 150},
            {"revenue": 210, "growth": 5, "employees": 80},
            {"revenue": 580, "growth": 18, "employees": 300},
            {"revenue": 90, "growth": 25, "employees": 20},
            {"revenue": 450, "growth": 10, "employees": 200},
            {"revenue": 160, "growth": 30, "employees": 35},
            {"revenue": 720, "growth": 7, "employees": 400},
        ],
        series=[ChartSeries(data_key="companies", label="Companies")],
        x_axis="revenue",
        y_axis="growth",
        z_axis="employees",
    )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "ScatterChart",
        "data": [
          {"revenue": 120, "growth": 8, "employees": 50},
          {"revenue": 340, "growth": 12, "employees": 150},
          {"revenue": 210, "growth": 5, "employees": 80},
          {"revenue": 580, "growth": 18, "employees": 300},
          {"revenue": 90, "growth": 25, "employees": 20},
          {"revenue": 450, "growth": 10, "employees": 200},
          {"revenue": 160, "growth": 30, "employees": 35},
          {"revenue": 720, "growth": 7, "employees": 400}
        ],
        "series": [{"dataKey": "companies", "label": "Companies"}],
        "xAxis": "revenue",
        "yAxis": "growth",
        "zAxis": "employees",
        "height": 300,
        "showLegend": true,
        "showTooltip": true,
        "animate": true,
        "showGrid": true
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## API Reference

<Card icon="code" title="ScatterChart Parameters">
  <ParamField body="data" type="list[dict] | str" required>
    Data as a list of dicts, or a `{{ field }}` interpolation reference. For multiple series, include a `_series` field in each dict matching the series `data_key`.
  </ParamField>

  <ParamField body="series" type="list[ChartSeries]" required>
    Series definitions -- each becomes a group of scatter points on the chart.
  </ParamField>

  <ParamField body="x_axis" type="str" required>
    Data key for x-axis numeric values.
  </ParamField>

  <ParamField body="y_axis" type="str" required>
    Data key for y-axis numeric values.
  </ParamField>

  <ParamField body="z_axis" type="str | None" default="None">
    Data key for bubble size. When set, point radii scale proportionally to this field's values.
  </ParamField>

  <ParamField body="height" type="int" default="300">
    Chart height in pixels.
  </ParamField>

  <ParamField body="show_legend" type="bool" default="False">
    Show a legend below the chart.
  </ParamField>

  <ParamField body="show_tooltip" type="bool" default="True">
    Show tooltips on hover.
  </ParamField>

  <ParamField body="show_grid" type="bool" default="True">
    Show cartesian grid lines.
  </ParamField>

  <ParamField body="css_class" type="str | None" default="None">
    Additional Tailwind CSS classes.
  </ParamField>
</Card>

<Card icon="code" title="ChartSeries Parameters">
  <ParamField body="data_key" type="str" required>
    Identifier for the series -- used for color mapping and legend display. For multi-series scatter charts, this must match the `_series` values in the data.
  </ParamField>

  <ParamField body="label" type="str | None" default="None">
    Display label for legends and tooltips. Defaults to the `data_key` value.
  </ParamField>

  <ParamField body="color" type="str | None" default="None">
    CSS color override. By default, colors cycle through the theme's chart palette (`--chart-1` through `--chart-5`).
  </ParamField>
</Card>

## Protocol Reference

```json ScatterChart theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "ScatterChart",
  "data": "dict[] | string (required)",
  "series": "[ChartSeries] (required)",
  "xAxis": "string (required)",
  "yAxis": "string (required)",
  "zAxis?": "string",
  "height?": "300",
  "showLegend?": false,
  "showTooltip?": true,
  "showGrid?": true,
  "cssClass?": "string"
}
```

```json ChartSeries theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "dataKey": "string (required)",
  "label?": "string",
  "color?": "string"
}
```

For the complete protocol schema, see [ScatterChart](/protocol/scatter-chart), [ChartSeries](/protocol/chart-series).


Built with [Mintlify](https://mintlify.com).