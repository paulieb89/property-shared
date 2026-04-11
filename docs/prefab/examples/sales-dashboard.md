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

# Sales Dashboard

> A complete analytics dashboard with metrics, charts, and a sortable data table.

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

A full analytics dashboard built entirely client-side. Four KPI metrics across the top, a revenue trend chart alongside a category breakdown donut, and a searchable orders table at the bottom — all composed in a single Python script using the [Dashboard](/components/dashboard-grid) grid.

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Dashboard","columns":12,"rowHeight":"auto","children":[{"type":"DashboardItem","col":1,"row":1,"colSpan":3,"rowSpan":1,"children":[{"type":"Card","children":[{"type":"CardContent","children":[{"type":"Metric","label":"Revenue","value":"$284,750","delta":"+12.5%","trend":"up","trendSentiment":"positive"}]}]}]},{"type":"DashboardItem","col":4,"row":1,"colSpan":3,"rowSpan":1,"children":[{"type":"Card","children":[{"type":"CardContent","children":[{"type":"Metric","label":"Orders","value":"1,842","delta":"+8.2%","trend":"up","trendSentiment":"positive"}]}]}]},{"type":"DashboardItem","col":7,"row":1,"colSpan":3,"rowSpan":1,"children":[{"type":"Card","children":[{"type":"CardContent","children":[{"type":"Metric","label":"Avg Order","value":"$154.59","delta":"-3.1%","trend":"down","trendSentiment":"negative"}]}]}]},{"type":"DashboardItem","col":10,"row":1,"colSpan":3,"rowSpan":1,"children":[{"type":"Card","children":[{"type":"CardContent","children":[{"type":"Metric","label":"Growth","value":"12.5%","delta":"+2.4pp","trend":"up","trendSentiment":"positive"}]}]}]},{"type":"DashboardItem","col":1,"row":2,"colSpan":8,"rowSpan":1,"children":[{"cssClass":"h-full","type":"Card","children":[{"type":"CardHeader","children":[{"type":"CardTitle","content":"Revenue Over Time"}]},{"type":"CardContent","children":[{"type":"AreaChart","data":[{"month":"Sep","revenue":38200,"costs":22100},{"month":"Oct","revenue":41500,"costs":23400},{"month":"Nov","revenue":45800,"costs":24800},{"month":"Dec","revenue":52100,"costs":27200},{"month":"Jan","revenue":48900,"costs":25600},{"month":"Feb","revenue":58250,"costs":28900}],"series":[{"dataKey":"revenue","label":"Revenue","color":"#2563eb"},{"dataKey":"costs","label":"Costs","color":"#e76e50"}],"xAxis":"month","height":250,"stacked":false,"curve":"smooth","showDots":false,"showLegend":true,"showTooltip":true,"animate":true,"showGrid":true,"showYAxis":true,"yAxisFormat":"compact"}]}]}]},{"type":"DashboardItem","col":9,"row":2,"colSpan":4,"rowSpan":1,"children":[{"cssClass":"h-full","type":"Card","children":[{"type":"CardHeader","children":[{"type":"CardTitle","content":"Revenue by Category"}]},{"type":"CardContent","children":[{"type":"PieChart","data":[{"category":"Electronics","revenue":98600},{"category":"Clothing","revenue":67200},{"category":"Home","revenue":54300},{"category":"Books","revenue":38400},{"category":"Sports","revenue":26250}],"dataKey":"revenue","nameKey":"category","height":250,"innerRadius":60,"showLabel":false,"paddingAngle":0,"showLegend":true,"showTooltip":true,"animate":true}]}]}]},{"type":"DashboardItem","col":1,"row":3,"colSpan":12,"rowSpan":1,"children":[{"type":"Card","children":[{"type":"CardHeader","children":[{"cssClass":"items-center justify-between","type":"Row","children":[{"type":"CardTitle","content":"Recent Orders"},{"content":"Last 7 days","type":"Muted"}]}]},{"type":"CardContent","children":[{"type":"DataTable","columns":[{"key":"id","header":"Order ID","sortable":true},{"key":"customer","header":"Customer","sortable":true},{"key":"product","header":"Product","sortable":false},{"key":"total","header":"Total","sortable":true},{"key":"status","header":"Status","sortable":false},{"key":"date","header":"Date","sortable":true}],"rows":[{"id":"ORD-7842","customer":"Acme Corp","product":"Laptop Pro","total":"$1,249.99","status":"Shipped","date":"Feb 18"},{"id":"ORD-7841","customer":"Globex Inc","product":"Wireless Mouse","total":"$42.00","status":"Delivered","date":"Feb 17"},{"id":"ORD-7840","customer":"Initech","product":"Standing Desk","total":"$599.00","status":"Processing","date":"Feb 17"},{"id":"ORD-7839","customer":"Umbrella LLC","product":"Monitor 27\"","total":"$389.99","status":"Shipped","date":"Feb 16"},{"id":"ORD-7838","customer":"Stark Industries","product":"Keyboard MX","total":"$179.00","status":"Delivered","date":"Feb 16"},{"id":"ORD-7837","customer":"Wayne Enterprises","product":"Webcam HD","total":"$89.99","status":"Delivered","date":"Feb 15"},{"id":"ORD-7836","customer":"Cyberdyne","product":"USB Hub","total":"$34.99","status":"Shipped","date":"Feb 15"},{"id":"ORD-7835","customer":"Oscorp","product":"Headphones Pro","total":"$299.00","status":"Processing","date":"Feb 14"}],"search":true,"paginated":true,"pageSize":5}]}]}]}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgKAogICAgQ2FyZCwgQ2FyZENvbnRlbnQsIENhcmRIZWFkZXIsIENhcmRUaXRsZSwKICAgIERhc2hib2FyZCwgRGFzaGJvYXJkSXRlbSwKICAgIERhdGFUYWJsZSwgRGF0YVRhYmxlQ29sdW1uLAogICAgTXV0ZWQsIFJvdywKKQpmcm9tIHByZWZhYl91aS5jb21wb25lbnRzLmNoYXJ0cyBpbXBvcnQgQXJlYUNoYXJ0LCBDaGFydFNlcmllcywgUGllQ2hhcnQKZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cy5tZXRyaWMgaW1wb3J0IE1ldHJpYwoKbW9udGhseSA9IFsKICAgIHsibW9udGgiOiAiU2VwIiwgInJldmVudWUiOiAzODIwMCwgImNvc3RzIjogMjIxMDB9LAogICAgeyJtb250aCI6ICJPY3QiLCAicmV2ZW51ZSI6IDQxNTAwLCAiY29zdHMiOiAyMzQwMH0sCiAgICB7Im1vbnRoIjogIk5vdiIsICJyZXZlbnVlIjogNDU4MDAsICJjb3N0cyI6IDI0ODAwfSwKICAgIHsibW9udGgiOiAiRGVjIiwgInJldmVudWUiOiA1MjEwMCwgImNvc3RzIjogMjcyMDB9LAogICAgeyJtb250aCI6ICJKYW4iLCAicmV2ZW51ZSI6IDQ4OTAwLCAiY29zdHMiOiAyNTYwMH0sCiAgICB7Im1vbnRoIjogIkZlYiIsICJyZXZlbnVlIjogNTgyNTAsICJjb3N0cyI6IDI4OTAwfSwKXQoKY2F0ZWdvcmllcyA9IFsKICAgIHsiY2F0ZWdvcnkiOiAiRWxlY3Ryb25pY3MiLCAicmV2ZW51ZSI6IDk4NjAwfSwKICAgIHsiY2F0ZWdvcnkiOiAiQ2xvdGhpbmciLCAicmV2ZW51ZSI6IDY3MjAwfSwKICAgIHsiY2F0ZWdvcnkiOiAiSG9tZSIsICJyZXZlbnVlIjogNTQzMDB9LAogICAgeyJjYXRlZ29yeSI6ICJCb29rcyIsICJyZXZlbnVlIjogMzg0MDB9LAogICAgeyJjYXRlZ29yeSI6ICJTcG9ydHMiLCAicmV2ZW51ZSI6IDI2MjUwfSwKXQoKb3JkZXJzID0gWwogICAgeyJpZCI6ICJPUkQtNzg0MiIsICJjdXN0b21lciI6ICJBY21lIENvcnAiLCAicHJvZHVjdCI6ICJMYXB0b3AgUHJvIiwgInRvdGFsIjogIiQxLDI0OS45OSIsICJzdGF0dXMiOiAiU2hpcHBlZCIsICJkYXRlIjogIkZlYiAxOCJ9LAogICAgeyJpZCI6ICJPUkQtNzg0MSIsICJjdXN0b21lciI6ICJHbG9iZXggSW5jIiwgInByb2R1Y3QiOiAiV2lyZWxlc3MgTW91c2UiLCAidG90YWwiOiAiJDQyLjAwIiwgInN0YXR1cyI6ICJEZWxpdmVyZWQiLCAiZGF0ZSI6ICJGZWIgMTcifSwKICAgIHsiaWQiOiAiT1JELTc4NDAiLCAiY3VzdG9tZXIiOiAiSW5pdGVjaCIsICJwcm9kdWN0IjogIlN0YW5kaW5nIERlc2siLCAidG90YWwiOiAiJDU5OS4wMCIsICJzdGF0dXMiOiAiUHJvY2Vzc2luZyIsICJkYXRlIjogIkZlYiAxNyJ9LAogICAgeyJpZCI6ICJPUkQtNzgzOSIsICJjdXN0b21lciI6ICJVbWJyZWxsYSBMTEMiLCAicHJvZHVjdCI6ICJNb25pdG9yIDI3XCIiLCAidG90YWwiOiAiJDM4OS45OSIsICJzdGF0dXMiOiAiU2hpcHBlZCIsICJkYXRlIjogIkZlYiAxNiJ9LAogICAgeyJpZCI6ICJPUkQtNzgzOCIsICJjdXN0b21lciI6ICJTdGFyayBJbmR1c3RyaWVzIiwgInByb2R1Y3QiOiAiS2V5Ym9hcmQgTVgiLCAidG90YWwiOiAiJDE3OS4wMCIsICJzdGF0dXMiOiAiRGVsaXZlcmVkIiwgImRhdGUiOiAiRmViIDE2In0sCiAgICB7ImlkIjogIk9SRC03ODM3IiwgImN1c3RvbWVyIjogIldheW5lIEVudGVycHJpc2VzIiwgInByb2R1Y3QiOiAiV2ViY2FtIEhEIiwgInRvdGFsIjogIiQ4OS45OSIsICJzdGF0dXMiOiAiRGVsaXZlcmVkIiwgImRhdGUiOiAiRmViIDE1In0sCiAgICB7ImlkIjogIk9SRC03ODM2IiwgImN1c3RvbWVyIjogIkN5YmVyZHluZSIsICJwcm9kdWN0IjogIlVTQiBIdWIiLCAidG90YWwiOiAiJDM0Ljk5IiwgInN0YXR1cyI6ICJTaGlwcGVkIiwgImRhdGUiOiAiRmViIDE1In0sCiAgICB7ImlkIjogIk9SRC03ODM1IiwgImN1c3RvbWVyIjogIk9zY29ycCIsICJwcm9kdWN0IjogIkhlYWRwaG9uZXMgUHJvIiwgInRvdGFsIjogIiQyOTkuMDAiLCAic3RhdHVzIjogIlByb2Nlc3NpbmciLCAiZGF0ZSI6ICJGZWIgMTQifSwKXQoKd2l0aCBEYXNoYm9hcmQoY29sdW1ucz0xMiwgcm93X2hlaWdodD0iYXV0byIsIGdhcD00KToKICAgICMgUm93IDE6IEtQSSBtZXRyaWNzIGluIGNhcmRzCiAgICB3aXRoIERhc2hib2FyZEl0ZW0oY29sPTEsIHJvdz0xLCBjb2xfc3Bhbj0zKToKICAgICAgICB3aXRoIENhcmQoKToKICAgICAgICAgICAgd2l0aCBDYXJkQ29udGVudCgpOgogICAgICAgICAgICAgICAgTWV0cmljKGxhYmVsPSJSZXZlbnVlIiwgdmFsdWU9IiQyODQsNzUwIiwgZGVsdGE9IisxMi41JSIsIHRyZW5kPSJ1cCIsIHRyZW5kX3NlbnRpbWVudD0icG9zaXRpdmUiKQogICAgd2l0aCBEYXNoYm9hcmRJdGVtKGNvbD00LCByb3c9MSwgY29sX3NwYW49Myk6CiAgICAgICAgd2l0aCBDYXJkKCk6CiAgICAgICAgICAgIHdpdGggQ2FyZENvbnRlbnQoKToKICAgICAgICAgICAgICAgIE1ldHJpYyhsYWJlbD0iT3JkZXJzIiwgdmFsdWU9IjEsODQyIiwgZGVsdGE9Iis4LjIlIiwgdHJlbmQ9InVwIiwgdHJlbmRfc2VudGltZW50PSJwb3NpdGl2ZSIpCiAgICB3aXRoIERhc2hib2FyZEl0ZW0oY29sPTcsIHJvdz0xLCBjb2xfc3Bhbj0zKToKICAgICAgICB3aXRoIENhcmQoKToKICAgICAgICAgICAgd2l0aCBDYXJkQ29udGVudCgpOgogICAgICAgICAgICAgICAgTWV0cmljKGxhYmVsPSJBdmcgT3JkZXIiLCB2YWx1ZT0iJDE1NC41OSIsIGRlbHRhPSItMy4xJSIsIHRyZW5kPSJkb3duIiwgdHJlbmRfc2VudGltZW50PSJuZWdhdGl2ZSIpCiAgICB3aXRoIERhc2hib2FyZEl0ZW0oY29sPTEwLCByb3c9MSwgY29sX3NwYW49Myk6CiAgICAgICAgd2l0aCBDYXJkKCk6CiAgICAgICAgICAgIHdpdGggQ2FyZENvbnRlbnQoKToKICAgICAgICAgICAgICAgIE1ldHJpYyhsYWJlbD0iR3Jvd3RoIiwgdmFsdWU9IjEyLjUlIiwgZGVsdGE9IisyLjRwcCIsIHRyZW5kPSJ1cCIsIHRyZW5kX3NlbnRpbWVudD0icG9zaXRpdmUiKQoKICAgICMgUm93IDI6IFJldmVudWUgdHJlbmQgKyBjYXRlZ29yeSBicmVha2Rvd24KICAgIHdpdGggRGFzaGJvYXJkSXRlbShjb2w9MSwgcm93PTIsIGNvbF9zcGFuPTgpOgogICAgICAgIHdpdGggQ2FyZChjc3NfY2xhc3M9ImgtZnVsbCIpOgogICAgICAgICAgICB3aXRoIENhcmRIZWFkZXIoKToKICAgICAgICAgICAgICAgIENhcmRUaXRsZSgiUmV2ZW51ZSBPdmVyIFRpbWUiKQogICAgICAgICAgICB3aXRoIENhcmRDb250ZW50KCk6CiAgICAgICAgICAgICAgICBBcmVhQ2hhcnQoCiAgICAgICAgICAgICAgICAgICAgZGF0YT1tb250aGx5LAogICAgICAgICAgICAgICAgICAgIHNlcmllcz1bCiAgICAgICAgICAgICAgICAgICAgICAgIENoYXJ0U2VyaWVzKGRhdGFfa2V5PSJyZXZlbnVlIiwgbGFiZWw9IlJldmVudWUiLCBjb2xvcj0iIzI1NjNlYiIpLAogICAgICAgICAgICAgICAgICAgICAgICBDaGFydFNlcmllcyhkYXRhX2tleT0iY29zdHMiLCBsYWJlbD0iQ29zdHMiLCBjb2xvcj0iI2U3NmU1MCIpLAogICAgICAgICAgICAgICAgICAgIF0sCiAgICAgICAgICAgICAgICAgICAgeF9heGlzPSJtb250aCIsCiAgICAgICAgICAgICAgICAgICAgY3VydmU9InNtb290aCIsCiAgICAgICAgICAgICAgICAgICAgc2hvd19sZWdlbmQ9VHJ1ZSwKICAgICAgICAgICAgICAgICAgICB5X2F4aXNfZm9ybWF0PSJjb21wYWN0IiwKICAgICAgICAgICAgICAgICAgICBoZWlnaHQ9MjUwLAogICAgICAgICAgICAgICAgKQoKICAgIHdpdGggRGFzaGJvYXJkSXRlbShjb2w9OSwgcm93PTIsIGNvbF9zcGFuPTQpOgogICAgICAgIHdpdGggQ2FyZChjc3NfY2xhc3M9ImgtZnVsbCIpOgogICAgICAgICAgICB3aXRoIENhcmRIZWFkZXIoKToKICAgICAgICAgICAgICAgIENhcmRUaXRsZSgiUmV2ZW51ZSBieSBDYXRlZ29yeSIpCiAgICAgICAgICAgIHdpdGggQ2FyZENvbnRlbnQoKToKICAgICAgICAgICAgICAgIFBpZUNoYXJ0KAogICAgICAgICAgICAgICAgICAgIGRhdGE9Y2F0ZWdvcmllcywKICAgICAgICAgICAgICAgICAgICBkYXRhX2tleT0icmV2ZW51ZSIsCiAgICAgICAgICAgICAgICAgICAgbmFtZV9rZXk9ImNhdGVnb3J5IiwKICAgICAgICAgICAgICAgICAgICBpbm5lcl9yYWRpdXM9NjAsCiAgICAgICAgICAgICAgICAgICAgc2hvd19sZWdlbmQ9VHJ1ZSwKICAgICAgICAgICAgICAgICAgICBoZWlnaHQ9MjUwLAogICAgICAgICAgICAgICAgKQoKICAgICMgUm93IDM6IE9yZGVycyB0YWJsZQogICAgd2l0aCBEYXNoYm9hcmRJdGVtKGNvbD0xLCByb3c9MywgY29sX3NwYW49MTIpOgogICAgICAgIHdpdGggQ2FyZCgpOgogICAgICAgICAgICB3aXRoIENhcmRIZWFkZXIoKToKICAgICAgICAgICAgICAgIHdpdGggUm93KGFsaWduPSJjZW50ZXIiLCBjc3NfY2xhc3M9Imp1c3RpZnktYmV0d2VlbiIpOgogICAgICAgICAgICAgICAgICAgIENhcmRUaXRsZSgiUmVjZW50IE9yZGVycyIpCiAgICAgICAgICAgICAgICAgICAgTXV0ZWQoIkxhc3QgNyBkYXlzIikKICAgICAgICAgICAgd2l0aCBDYXJkQ29udGVudCgpOgogICAgICAgICAgICAgICAgRGF0YVRhYmxlKAogICAgICAgICAgICAgICAgICAgIGNvbHVtbnM9WwogICAgICAgICAgICAgICAgICAgICAgICBEYXRhVGFibGVDb2x1bW4oa2V5PSJpZCIsIGhlYWRlcj0iT3JkZXIgSUQiLCBzb3J0YWJsZT1UcnVlKSwKICAgICAgICAgICAgICAgICAgICAgICAgRGF0YVRhYmxlQ29sdW1uKGtleT0iY3VzdG9tZXIiLCBoZWFkZXI9IkN1c3RvbWVyIiwgc29ydGFibGU9VHJ1ZSksCiAgICAgICAgICAgICAgICAgICAgICAgIERhdGFUYWJsZUNvbHVtbihrZXk9InByb2R1Y3QiLCBoZWFkZXI9IlByb2R1Y3QiKSwKICAgICAgICAgICAgICAgICAgICAgICAgRGF0YVRhYmxlQ29sdW1uKGtleT0idG90YWwiLCBoZWFkZXI9IlRvdGFsIiwgc29ydGFibGU9VHJ1ZSksCiAgICAgICAgICAgICAgICAgICAgICAgIERhdGFUYWJsZUNvbHVtbihrZXk9InN0YXR1cyIsIGhlYWRlcj0iU3RhdHVzIiksCiAgICAgICAgICAgICAgICAgICAgICAgIERhdGFUYWJsZUNvbHVtbihrZXk9ImRhdGUiLCBoZWFkZXI9IkRhdGUiLCBzb3J0YWJsZT1UcnVlKSwKICAgICAgICAgICAgICAgICAgICBdLAogICAgICAgICAgICAgICAgICAgIHJvd3M9b3JkZXJzLAogICAgICAgICAgICAgICAgICAgIHNlYXJjaD1UcnVlLAogICAgICAgICAgICAgICAgICAgIHBhZ2luYXRlZD1UcnVlLAogICAgICAgICAgICAgICAgICAgIHBhZ2Vfc2l6ZT01LAogICAgICAgICAgICAgICAgKQo">
  <CodeGroup>
    ```python Python icon="python" expandable theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import (
        Card, CardContent, CardHeader, CardTitle,
        Dashboard, DashboardItem,
        DataTable, DataTableColumn,
        Muted, Row,
    )
    from prefab_ui.components.charts import AreaChart, ChartSeries, PieChart
    from prefab_ui.components.metric import Metric

    monthly = [
        {"month": "Sep", "revenue": 38200, "costs": 22100},
        {"month": "Oct", "revenue": 41500, "costs": 23400},
        {"month": "Nov", "revenue": 45800, "costs": 24800},
        {"month": "Dec", "revenue": 52100, "costs": 27200},
        {"month": "Jan", "revenue": 48900, "costs": 25600},
        {"month": "Feb", "revenue": 58250, "costs": 28900},
    ]

    categories = [
        {"category": "Electronics", "revenue": 98600},
        {"category": "Clothing", "revenue": 67200},
        {"category": "Home", "revenue": 54300},
        {"category": "Books", "revenue": 38400},
        {"category": "Sports", "revenue": 26250},
    ]

    orders = [
        {"id": "ORD-7842", "customer": "Acme Corp", "product": "Laptop Pro", "total": "$1,249.99", "status": "Shipped", "date": "Feb 18"},
        {"id": "ORD-7841", "customer": "Globex Inc", "product": "Wireless Mouse", "total": "$42.00", "status": "Delivered", "date": "Feb 17"},
        {"id": "ORD-7840", "customer": "Initech", "product": "Standing Desk", "total": "$599.00", "status": "Processing", "date": "Feb 17"},
        {"id": "ORD-7839", "customer": "Umbrella LLC", "product": "Monitor 27\"", "total": "$389.99", "status": "Shipped", "date": "Feb 16"},
        {"id": "ORD-7838", "customer": "Stark Industries", "product": "Keyboard MX", "total": "$179.00", "status": "Delivered", "date": "Feb 16"},
        {"id": "ORD-7837", "customer": "Wayne Enterprises", "product": "Webcam HD", "total": "$89.99", "status": "Delivered", "date": "Feb 15"},
        {"id": "ORD-7836", "customer": "Cyberdyne", "product": "USB Hub", "total": "$34.99", "status": "Shipped", "date": "Feb 15"},
        {"id": "ORD-7835", "customer": "Oscorp", "product": "Headphones Pro", "total": "$299.00", "status": "Processing", "date": "Feb 14"},
    ]

    with Dashboard(columns=12, row_height="auto", gap=4):
        # Row 1: KPI metrics in cards
        with DashboardItem(col=1, row=1, col_span=3):
            with Card():
                with CardContent():
                    Metric(label="Revenue", value="$284,750", delta="+12.5%", trend="up", trend_sentiment="positive")
        with DashboardItem(col=4, row=1, col_span=3):
            with Card():
                with CardContent():
                    Metric(label="Orders", value="1,842", delta="+8.2%", trend="up", trend_sentiment="positive")
        with DashboardItem(col=7, row=1, col_span=3):
            with Card():
                with CardContent():
                    Metric(label="Avg Order", value="$154.59", delta="-3.1%", trend="down", trend_sentiment="negative")
        with DashboardItem(col=10, row=1, col_span=3):
            with Card():
                with CardContent():
                    Metric(label="Growth", value="12.5%", delta="+2.4pp", trend="up", trend_sentiment="positive")

        # Row 2: Revenue trend + category breakdown
        with DashboardItem(col=1, row=2, col_span=8):
            with Card(css_class="h-full"):
                with CardHeader():
                    CardTitle("Revenue Over Time")
                with CardContent():
                    AreaChart(
                        data=monthly,
                        series=[
                            ChartSeries(data_key="revenue", label="Revenue", color="#2563eb"),
                            ChartSeries(data_key="costs", label="Costs", color="#e76e50"),
                        ],
                        x_axis="month",
                        curve="smooth",
                        show_legend=True,
                        y_axis_format="compact",
                        height=250,
                    )

        with DashboardItem(col=9, row=2, col_span=4):
            with Card(css_class="h-full"):
                with CardHeader():
                    CardTitle("Revenue by Category")
                with CardContent():
                    PieChart(
                        data=categories,
                        data_key="revenue",
                        name_key="category",
                        inner_radius=60,
                        show_legend=True,
                        height=250,
                    )

        # Row 3: Orders table
        with DashboardItem(col=1, row=3, col_span=12):
            with Card():
                with CardHeader():
                    with Row(align="center", css_class="justify-between"):
                        CardTitle("Recent Orders")
                        Muted("Last 7 days")
                with CardContent():
                    DataTable(
                        columns=[
                            DataTableColumn(key="id", header="Order ID", sortable=True),
                            DataTableColumn(key="customer", header="Customer", sortable=True),
                            DataTableColumn(key="product", header="Product"),
                            DataTableColumn(key="total", header="Total", sortable=True),
                            DataTableColumn(key="status", header="Status"),
                            DataTableColumn(key="date", header="Date", sortable=True),
                        ],
                        rows=orders,
                        search=True,
                        paginated=True,
                        page_size=5,
                    )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Dashboard",
        "columns": 12,
        "rowHeight": "auto",
        "children": [
          {
            "type": "DashboardItem",
            "col": 1,
            "row": 1,
            "colSpan": 3,
            "rowSpan": 1,
            "children": [
              {
                "type": "Card",
                "children": [
                  {
                    "type": "CardContent",
                    "children": [
                      {
                        "type": "Metric",
                        "label": "Revenue",
                        "value": "$284,750",
                        "delta": "+12.5%",
                        "trend": "up",
                        "trendSentiment": "positive"
                      }
                    ]
                  }
                ]
              }
            ]
          },
          {
            "type": "DashboardItem",
            "col": 4,
            "row": 1,
            "colSpan": 3,
            "rowSpan": 1,
            "children": [
              {
                "type": "Card",
                "children": [
                  {
                    "type": "CardContent",
                    "children": [
                      {
                        "type": "Metric",
                        "label": "Orders",
                        "value": "1,842",
                        "delta": "+8.2%",
                        "trend": "up",
                        "trendSentiment": "positive"
                      }
                    ]
                  }
                ]
              }
            ]
          },
          {
            "type": "DashboardItem",
            "col": 7,
            "row": 1,
            "colSpan": 3,
            "rowSpan": 1,
            "children": [
              {
                "type": "Card",
                "children": [
                  {
                    "type": "CardContent",
                    "children": [
                      {
                        "type": "Metric",
                        "label": "Avg Order",
                        "value": "$154.59",
                        "delta": "-3.1%",
                        "trend": "down",
                        "trendSentiment": "negative"
                      }
                    ]
                  }
                ]
              }
            ]
          },
          {
            "type": "DashboardItem",
            "col": 10,
            "row": 1,
            "colSpan": 3,
            "rowSpan": 1,
            "children": [
              {
                "type": "Card",
                "children": [
                  {
                    "type": "CardContent",
                    "children": [
                      {
                        "type": "Metric",
                        "label": "Growth",
                        "value": "12.5%",
                        "delta": "+2.4pp",
                        "trend": "up",
                        "trendSentiment": "positive"
                      }
                    ]
                  }
                ]
              }
            ]
          },
          {
            "type": "DashboardItem",
            "col": 1,
            "row": 2,
            "colSpan": 8,
            "rowSpan": 1,
            "children": [
              {
                "cssClass": "h-full",
                "type": "Card",
                "children": [
                  {
                    "type": "CardHeader",
                    "children": [{"type": "CardTitle", "content": "Revenue Over Time"}]
                  },
                  {
                    "type": "CardContent",
                    "children": [
                      {
                        "type": "AreaChart",
                        "data": [
                          {"month": "Sep", "revenue": 38200, "costs": 22100},
                          {"month": "Oct", "revenue": 41500, "costs": 23400},
                          {"month": "Nov", "revenue": 45800, "costs": 24800},
                          {"month": "Dec", "revenue": 52100, "costs": 27200},
                          {"month": "Jan", "revenue": 48900, "costs": 25600},
                          {"month": "Feb", "revenue": 58250, "costs": 28900}
                        ],
                        "series": [
                          {"dataKey": "revenue", "label": "Revenue", "color": "#2563eb"},
                          {"dataKey": "costs", "label": "Costs", "color": "#e76e50"}
                        ],
                        "xAxis": "month",
                        "height": 250,
                        "stacked": false,
                        "curve": "smooth",
                        "showDots": false,
                        "showLegend": true,
                        "showTooltip": true,
                        "animate": true,
                        "showGrid": true,
                        "showYAxis": true,
                        "yAxisFormat": "compact"
                      }
                    ]
                  }
                ]
              }
            ]
          },
          {
            "type": "DashboardItem",
            "col": 9,
            "row": 2,
            "colSpan": 4,
            "rowSpan": 1,
            "children": [
              {
                "cssClass": "h-full",
                "type": "Card",
                "children": [
                  {
                    "type": "CardHeader",
                    "children": [{"type": "CardTitle", "content": "Revenue by Category"}]
                  },
                  {
                    "type": "CardContent",
                    "children": [
                      {
                        "type": "PieChart",
                        "data": [
                          {"category": "Electronics", "revenue": 98600},
                          {"category": "Clothing", "revenue": 67200},
                          {"category": "Home", "revenue": 54300},
                          {"category": "Books", "revenue": 38400},
                          {"category": "Sports", "revenue": 26250}
                        ],
                        "dataKey": "revenue",
                        "nameKey": "category",
                        "height": 250,
                        "innerRadius": 60,
                        "showLabel": false,
                        "paddingAngle": 0,
                        "showLegend": true,
                        "showTooltip": true,
                        "animate": true
                      }
                    ]
                  }
                ]
              }
            ]
          },
          {
            "type": "DashboardItem",
            "col": 1,
            "row": 3,
            "colSpan": 12,
            "rowSpan": 1,
            "children": [
              {
                "type": "Card",
                "children": [
                  {
                    "type": "CardHeader",
                    "children": [
                      {
                        "cssClass": "items-center justify-between",
                        "type": "Row",
                        "children": [
                          {"type": "CardTitle", "content": "Recent Orders"},
                          {"content": "Last 7 days", "type": "Muted"}
                        ]
                      }
                    ]
                  },
                  {
                    "type": "CardContent",
                    "children": [
                      {
                        "type": "DataTable",
                        "columns": [
                          {"key": "id", "header": "Order ID", "sortable": true},
                          {"key": "customer", "header": "Customer", "sortable": true},
                          {"key": "product", "header": "Product", "sortable": false},
                          {"key": "total", "header": "Total", "sortable": true},
                          {"key": "status", "header": "Status", "sortable": false},
                          {"key": "date", "header": "Date", "sortable": true}
                        ],
                        "rows": [
                          {
                            "id": "ORD-7842",
                            "customer": "Acme Corp",
                            "product": "Laptop Pro",
                            "total": "$1,249.99",
                            "status": "Shipped",
                            "date": "Feb 18"
                          },
                          {
                            "id": "ORD-7841",
                            "customer": "Globex Inc",
                            "product": "Wireless Mouse",
                            "total": "$42.00",
                            "status": "Delivered",
                            "date": "Feb 17"
                          },
                          {
                            "id": "ORD-7840",
                            "customer": "Initech",
                            "product": "Standing Desk",
                            "total": "$599.00",
                            "status": "Processing",
                            "date": "Feb 17"
                          },
                          {
                            "id": "ORD-7839",
                            "customer": "Umbrella LLC",
                            "product": "Monitor 27\"",
                            "total": "$389.99",
                            "status": "Shipped",
                            "date": "Feb 16"
                          },
                          {
                            "id": "ORD-7838",
                            "customer": "Stark Industries",
                            "product": "Keyboard MX",
                            "total": "$179.00",
                            "status": "Delivered",
                            "date": "Feb 16"
                          },
                          {
                            "id": "ORD-7837",
                            "customer": "Wayne Enterprises",
                            "product": "Webcam HD",
                            "total": "$89.99",
                            "status": "Delivered",
                            "date": "Feb 15"
                          },
                          {
                            "id": "ORD-7836",
                            "customer": "Cyberdyne",
                            "product": "USB Hub",
                            "total": "$34.99",
                            "status": "Shipped",
                            "date": "Feb 15"
                          },
                          {
                            "id": "ORD-7835",
                            "customer": "Oscorp",
                            "product": "Headphones Pro",
                            "total": "$299.00",
                            "status": "Processing",
                            "date": "Feb 14"
                          }
                        ],
                        "search": true,
                        "paginated": true,
                        "pageSize": 5
                      }
                    ]
                  }
                ]
              }
            ]
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## How It Works

The entire layout is a 12-column [Dashboard](/components/dashboard-grid) grid with `row_height="auto"` so each row sizes to its content. The top row splits evenly into four [Metric](/components/metric) cards, each spanning 3 columns. The `trend` and `trend_sentiment` props add colored arrows and delta badges — green for positive metrics, red for the declining average order value.

The middle row pairs an [AreaChart](/components/area-chart) (8 columns) with a [PieChart](/components/pie-chart) donut (4 columns). The area chart uses `curve="smooth"` for a polished look and overlays revenue against costs with two series. The donut chart uses `inner_radius=60` to create the hole and `show_legend=True` so categories are labeled.

The bottom row is a full-width [DataTable](/components/data-table) with sortable columns, a search bar, and pagination at 5 rows per page. Click any sortable column header to reorder, or type in the search box to filter across all fields.

Every piece of data here is embedded directly in the Python script — no server, no API calls. The renderer handles all interactivity (sorting, searching, pagination, tooltips) client-side.


Built with [Mintlify](https://mintlify.com).