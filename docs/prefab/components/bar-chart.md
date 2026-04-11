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

# BarChart

> Visualize categorical data with vertical bars.

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

BarChart renders one or more data series as vertical bars. Each `ChartSeries` maps a key from your data to a set of bars, and `x_axis` controls the category labels along the bottom. Colors are automatically assigned from the theme's chart palette.

## Basic Usage

<ComponentPreview json={{"view":{"type":"BarChart","data":[{"month":"Jan","desktop":186,"mobile":80},{"month":"Feb","desktop":305,"mobile":200},{"month":"Mar","desktop":237,"mobile":120},{"month":"Apr","desktop":73,"mobile":190},{"month":"May","desktop":209,"mobile":130},{"month":"Jun","desktop":214,"mobile":140}],"series":[{"dataKey":"desktop","label":"Desktop"},{"dataKey":"mobile","label":"Mobile"}],"xAxis":"month","height":300,"stacked":false,"horizontal":false,"barRadius":4,"showLegend":true,"showTooltip":true,"animate":true,"showGrid":true,"showYAxis":true,"yAxisFormat":"auto"}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cy5jaGFydHMgaW1wb3J0IEJhckNoYXJ0LCBDaGFydFNlcmllcwoKZGF0YSA9IFsKICAgIHsibW9udGgiOiAiSmFuIiwgImRlc2t0b3AiOiAxODYsICJtb2JpbGUiOiA4MH0sCiAgICB7Im1vbnRoIjogIkZlYiIsICJkZXNrdG9wIjogMzA1LCAibW9iaWxlIjogMjAwfSwKICAgIHsibW9udGgiOiAiTWFyIiwgImRlc2t0b3AiOiAyMzcsICJtb2JpbGUiOiAxMjB9LAogICAgeyJtb250aCI6ICJBcHIiLCAiZGVza3RvcCI6IDczLCAibW9iaWxlIjogMTkwfSwKICAgIHsibW9udGgiOiAiTWF5IiwgImRlc2t0b3AiOiAyMDksICJtb2JpbGUiOiAxMzB9LAogICAgeyJtb250aCI6ICJKdW4iLCAiZGVza3RvcCI6IDIxNCwgIm1vYmlsZSI6IDE0MH0sCl0KCkJhckNoYXJ0KAogICAgZGF0YT1kYXRhLAogICAgc2VyaWVzPVsKICAgICAgICBDaGFydFNlcmllcyhkYXRhX2tleT0iZGVza3RvcCIsIGxhYmVsPSJEZXNrdG9wIiksCiAgICAgICAgQ2hhcnRTZXJpZXMoZGF0YV9rZXk9Im1vYmlsZSIsIGxhYmVsPSJNb2JpbGUiKSwKICAgIF0sCiAgICB4X2F4aXM9Im1vbnRoIiwKICAgIHNob3dfbGVnZW5kPVRydWUsCikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components.charts import BarChart, ChartSeries

    data = [
        {"month": "Jan", "desktop": 186, "mobile": 80},
        {"month": "Feb", "desktop": 305, "mobile": 200},
        {"month": "Mar", "desktop": 237, "mobile": 120},
        {"month": "Apr", "desktop": 73, "mobile": 190},
        {"month": "May", "desktop": 209, "mobile": 130},
        {"month": "Jun", "desktop": 214, "mobile": 140},
    ]

    BarChart(
        data=data,
        series=[
            ChartSeries(data_key="desktop", label="Desktop"),
            ChartSeries(data_key="mobile", label="Mobile"),
        ],
        x_axis="month",
        show_legend=True,
    )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "BarChart",
        "data": [
          {"month": "Jan", "desktop": 186, "mobile": 80},
          {"month": "Feb", "desktop": 305, "mobile": 200},
          {"month": "Mar", "desktop": 237, "mobile": 120},
          {"month": "Apr", "desktop": 73, "mobile": 190},
          {"month": "May", "desktop": 209, "mobile": 130},
          {"month": "Jun", "desktop": 214, "mobile": 140}
        ],
        "series": [
          {"dataKey": "desktop", "label": "Desktop"},
          {"dataKey": "mobile", "label": "Mobile"}
        ],
        "xAxis": "month",
        "height": 300,
        "stacked": false,
        "horizontal": false,
        "barRadius": 4,
        "showLegend": true,
        "showTooltip": true,
        "animate": true,
        "showGrid": true,
        "showYAxis": true,
        "yAxisFormat": "auto"
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Stacked

Set `stacked=True` to stack series on top of each other instead of placing them side by side. This is useful when you want to show both individual values and the total.

<ComponentPreview json={{"view":{"type":"BarChart","data":[{"month":"Jan","desktop":186,"mobile":80},{"month":"Feb","desktop":305,"mobile":200},{"month":"Mar","desktop":237,"mobile":120},{"month":"Apr","desktop":73,"mobile":190},{"month":"May","desktop":209,"mobile":130},{"month":"Jun","desktop":214,"mobile":140}],"series":[{"dataKey":"desktop","label":"Desktop"},{"dataKey":"mobile","label":"Mobile"}],"xAxis":"month","height":300,"stacked":true,"horizontal":false,"barRadius":4,"showLegend":true,"showTooltip":true,"animate":true,"showGrid":true,"showYAxis":true,"yAxisFormat":"auto"}}} playground="QmFyQ2hhcnQoCiAgICBkYXRhPWRhdGEsCiAgICBzZXJpZXM9WwogICAgICAgIENoYXJ0U2VyaWVzKGRhdGFfa2V5PSJkZXNrdG9wIiwgbGFiZWw9IkRlc2t0b3AiKSwKICAgICAgICBDaGFydFNlcmllcyhkYXRhX2tleT0ibW9iaWxlIiwgbGFiZWw9Ik1vYmlsZSIpLAogICAgXSwKICAgIHhfYXhpcz0ibW9udGgiLAogICAgc3RhY2tlZD1UcnVlLAogICAgc2hvd19sZWdlbmQ9VHJ1ZSwKKQo">
  <CodeGroup>
    ```python Python {8} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    BarChart(
        data=data,
        series=[
            ChartSeries(data_key="desktop", label="Desktop"),
            ChartSeries(data_key="mobile", label="Mobile"),
        ],
        x_axis="month",
        stacked=True,
        show_legend=True,
    )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "BarChart",
        "data": [
          {"month": "Jan", "desktop": 186, "mobile": 80},
          {"month": "Feb", "desktop": 305, "mobile": 200},
          {"month": "Mar", "desktop": 237, "mobile": 120},
          {"month": "Apr", "desktop": 73, "mobile": 190},
          {"month": "May", "desktop": 209, "mobile": 130},
          {"month": "Jun", "desktop": 214, "mobile": 140}
        ],
        "series": [
          {"dataKey": "desktop", "label": "Desktop"},
          {"dataKey": "mobile", "label": "Mobile"}
        ],
        "xAxis": "month",
        "height": 300,
        "stacked": true,
        "horizontal": false,
        "barRadius": 4,
        "showLegend": true,
        "showTooltip": true,
        "animate": true,
        "showGrid": true,
        "showYAxis": true,
        "yAxisFormat": "auto"
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Minimal

Turn off the grid for a cleaner look.

<ComponentPreview json={{"view":{"type":"BarChart","data":[{"month":"Jan","desktop":186,"mobile":80},{"month":"Feb","desktop":305,"mobile":200},{"month":"Mar","desktop":237,"mobile":120},{"month":"Apr","desktop":73,"mobile":190},{"month":"May","desktop":209,"mobile":130},{"month":"Jun","desktop":214,"mobile":140}],"series":[{"dataKey":"revenue","label":"Revenue"}],"xAxis":"month","height":300,"stacked":false,"horizontal":false,"barRadius":4,"showLegend":true,"showTooltip":true,"animate":true,"showGrid":false,"showYAxis":true,"yAxisFormat":"auto"}}} playground="QmFyQ2hhcnQoCiAgICBkYXRhPWRhdGEsCiAgICBzZXJpZXM9W0NoYXJ0U2VyaWVzKGRhdGFfa2V5PSJyZXZlbnVlIiwgbGFiZWw9IlJldmVudWUiKV0sCiAgICB4X2F4aXM9Im1vbnRoIiwKICAgIHNob3dfZ3JpZD1GYWxzZSwKKQo">
  <CodeGroup>
    ```python Python {5} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    BarChart(
        data=data,
        series=[ChartSeries(data_key="revenue", label="Revenue")],
        x_axis="month",
        show_grid=False,
    )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "BarChart",
        "data": [
          {"month": "Jan", "desktop": 186, "mobile": 80},
          {"month": "Feb", "desktop": 305, "mobile": 200},
          {"month": "Mar", "desktop": 237, "mobile": 120},
          {"month": "Apr", "desktop": 73, "mobile": 190},
          {"month": "May", "desktop": 209, "mobile": 130},
          {"month": "Jun", "desktop": 214, "mobile": 140}
        ],
        "series": [{"dataKey": "revenue", "label": "Revenue"}],
        "xAxis": "month",
        "height": 300,
        "stacked": false,
        "horizontal": false,
        "barRadius": 4,
        "showLegend": true,
        "showTooltip": true,
        "animate": true,
        "showGrid": false,
        "showYAxis": true,
        "yAxisFormat": "auto"
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Horizontal

Set `horizontal=True` to render bars horizontally. Categories appear along the y-axis and values extend to the right.

<ComponentPreview json={{"view":{"type":"BarChart","data":[{"month":"Jan","desktop":186,"mobile":80},{"month":"Feb","desktop":305,"mobile":200},{"month":"Mar","desktop":237,"mobile":120},{"month":"Apr","desktop":73,"mobile":190},{"month":"May","desktop":209,"mobile":130},{"month":"Jun","desktop":214,"mobile":140}],"series":[{"dataKey":"desktop","label":"Desktop"},{"dataKey":"mobile","label":"Mobile"}],"xAxis":"month","height":300,"stacked":false,"horizontal":true,"barRadius":4,"showLegend":true,"showTooltip":true,"animate":true,"showGrid":true,"showYAxis":true,"yAxisFormat":"auto"}}} playground="QmFyQ2hhcnQoCiAgICBkYXRhPWRhdGEsCiAgICBzZXJpZXM9WwogICAgICAgIENoYXJ0U2VyaWVzKGRhdGFfa2V5PSJkZXNrdG9wIiwgbGFiZWw9IkRlc2t0b3AiKSwKICAgICAgICBDaGFydFNlcmllcyhkYXRhX2tleT0ibW9iaWxlIiwgbGFiZWw9Ik1vYmlsZSIpLAogICAgXSwKICAgIHhfYXhpcz0ibW9udGgiLAogICAgaG9yaXpvbnRhbD1UcnVlLAogICAgc2hvd19sZWdlbmQ9VHJ1ZSwKKQo">
  <CodeGroup>
    ```python Python {8} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    BarChart(
        data=data,
        series=[
            ChartSeries(data_key="desktop", label="Desktop"),
            ChartSeries(data_key="mobile", label="Mobile"),
        ],
        x_axis="month",
        horizontal=True,
        show_legend=True,
    )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "BarChart",
        "data": [
          {"month": "Jan", "desktop": 186, "mobile": 80},
          {"month": "Feb", "desktop": 305, "mobile": 200},
          {"month": "Mar", "desktop": 237, "mobile": 120},
          {"month": "Apr", "desktop": 73, "mobile": 190},
          {"month": "May", "desktop": 209, "mobile": 130},
          {"month": "Jun", "desktop": 214, "mobile": 140}
        ],
        "series": [
          {"dataKey": "desktop", "label": "Desktop"},
          {"dataKey": "mobile", "label": "Mobile"}
        ],
        "xAxis": "month",
        "height": 300,
        "stacked": false,
        "horizontal": true,
        "barRadius": 4,
        "showLegend": true,
        "showTooltip": true,
        "animate": true,
        "showGrid": true,
        "showYAxis": true,
        "yAxisFormat": "auto"
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## API Reference

<Card icon="code" title="BarChart Parameters">
  <ParamField body="data" type="list[dict] | str" required>
    Data as a list of dicts, or a `{{ field }}` interpolation reference.
  </ParamField>

  <ParamField body="series" type="list[ChartSeries]" required>
    Series definitions — each becomes a group of bars on the chart.
  </ParamField>

  <ParamField body="x_axis" type="str | None" default="None">
    Data key for x-axis category labels.
  </ParamField>

  <ParamField body="height" type="int" default="300">
    Chart height in pixels.
  </ParamField>

  <ParamField body="stacked" type="bool" default="False">
    Stack series on top of each other.
  </ParamField>

  <ParamField body="horizontal" type="bool" default="False">
    Render bars horizontally instead of vertically.
  </ParamField>

  <ParamField body="bar_radius" type="int" default="4">
    Corner radius of each bar in pixels.
  </ParamField>

  <ParamField body="show_legend" type="bool" default="False">
    Show a legend below the chart.
  </ParamField>

  <ParamField body="show_tooltip" type="bool" default="True">
    Show tooltips on hover.
  </ParamField>

  <ParamField body="show_grid" type="bool" default="True">
    Show horizontal grid lines.
  </ParamField>

  <ParamField body="css_class" type="str | None" default="None">
    Additional Tailwind CSS classes.
  </ParamField>
</Card>

<Card icon="code" title="ChartSeries Parameters">
  <ParamField body="data_key" type="str" required>
    Data field to plot — must match a key in the data dicts.
  </ParamField>

  <ParamField body="label" type="str | None" default="None">
    Display label for legends and tooltips. Defaults to the `data_key` value.
  </ParamField>

  <ParamField body="color" type="str | None" default="None">
    CSS color override. By default, colors cycle through the theme's chart palette (`--chart-1` through `--chart-5`).
  </ParamField>
</Card>

## Protocol Reference

```json BarChart theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "BarChart",
  "data": "Action[] | string (required)",
  "series": "[ChartSeries] (required)",
  "xAxis?": "string",
  "height?": "300",
  "stacked?": false,
  "horizontal?": false,
  "barRadius?": 4,
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

For the complete protocol schema, see [BarChart](/protocol/bar-chart), [ChartSeries](/protocol/chart-series).


Built with [Mintlify](https://mintlify.com).