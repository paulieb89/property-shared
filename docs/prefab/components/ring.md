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

# Ring

> Circular progress indicator with centered label.

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

Ring displays a value as a circular arc that fills clockwise from 12 o'clock. A centered label shows the value or any custom text. It shares the same `value`/`min`/`max`/`variant` API as Progress but takes up less horizontal space, making it ideal for dashboards and status panels.

## Basic Usage

<ComponentPreview json={{"view":{"type":"Ring","value":72.0,"min":0,"max":100,"label":"72%","variant":"default","size":"default","thickness":6}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgUmluZwoKUmluZyh2YWx1ZT03MiwgbGFiZWw9IjcyJSIpCg">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Ring

    Ring(value=72, label="72%")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "Ring",
        "value": 72.0,
        "min": 0,
        "max": 100,
        "label": "72%",
        "variant": "default",
        "size": "default",
        "thickness": 6
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Sizes

Three sizes control the ring diameter: `sm` (64px), `default` (96px), and `lg` (128px).

<ComponentPreview json={{"view":{"cssClass":"gap-6 items-end","type":"Row","children":[{"type":"Ring","value":60.0,"min":0,"max":100,"label":"sm","variant":"default","size":"sm","thickness":6},{"type":"Ring","value":60.0,"min":0,"max":100,"label":"default","variant":"default","size":"default","thickness":6},{"type":"Ring","value":60.0,"min":0,"max":100,"label":"lg","variant":"default","size":"lg","thickness":6}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgUmluZywgUm93Cgp3aXRoIFJvdyhjc3NfY2xhc3M9ImdhcC02IGl0ZW1zLWVuZCIpOgogICAgUmluZyh2YWx1ZT02MCwgc2l6ZT0ic20iLCBsYWJlbD0ic20iKQogICAgUmluZyh2YWx1ZT02MCwgc2l6ZT0iZGVmYXVsdCIsIGxhYmVsPSJkZWZhdWx0IikKICAgIFJpbmcodmFsdWU9NjAsIHNpemU9ImxnIiwgbGFiZWw9ImxnIikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Ring, Row

    with Row(css_class="gap-6 items-end"):
        Ring(value=60, size="sm", label="sm")
        Ring(value=60, size="default", label="default")
        Ring(value=60, size="lg", label="lg")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-6 items-end",
        "type": "Row",
        "children": [
          {
            "type": "Ring",
            "value": 60.0,
            "min": 0,
            "max": 100,
            "label": "sm",
            "variant": "default",
            "size": "sm",
            "thickness": 6
          },
          {
            "type": "Ring",
            "value": 60.0,
            "min": 0,
            "max": 100,
            "label": "default",
            "variant": "default",
            "size": "default",
            "thickness": 6
          },
          {
            "type": "Ring",
            "value": 60.0,
            "min": 0,
            "max": 100,
            "label": "lg",
            "variant": "default",
            "size": "lg",
            "thickness": 6
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Variants

Semantic variants color the filled arc to communicate meaning at a glance:

<ComponentPreview json={{"view":{"cssClass":"gap-4 flex-wrap","type":"Row","children":[{"type":"Ring","value":60.0,"min":0,"max":100,"label":"60%","variant":"default","size":"default","thickness":6},{"type":"Ring","value":100.0,"min":0,"max":100,"label":"100%","variant":"success","size":"default","thickness":6},{"type":"Ring","value":72.0,"min":0,"max":100,"label":"72%","variant":"warning","size":"default","thickness":6},{"type":"Ring","value":90.0,"min":0,"max":100,"label":"90%","variant":"destructive","size":"default","thickness":6},{"type":"Ring","value":45.0,"min":0,"max":100,"label":"45%","variant":"info","size":"default","thickness":6},{"type":"Ring","value":30.0,"min":0,"max":100,"label":"30%","variant":"muted","size":"default","thickness":6}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgUmluZywgUm93Cgp3aXRoIFJvdyhjc3NfY2xhc3M9ImdhcC00IGZsZXgtd3JhcCIpOgogICAgUmluZyh2YWx1ZT02MCwgbGFiZWw9IjYwJSIpCiAgICBSaW5nKHZhbHVlPTEwMCwgdmFyaWFudD0ic3VjY2VzcyIsIGxhYmVsPSIxMDAlIikKICAgIFJpbmcodmFsdWU9NzIsIHZhcmlhbnQ9Indhcm5pbmciLCBsYWJlbD0iNzIlIikKICAgIFJpbmcodmFsdWU9OTAsIHZhcmlhbnQ9ImRlc3RydWN0aXZlIiwgbGFiZWw9IjkwJSIpCiAgICBSaW5nKHZhbHVlPTQ1LCB2YXJpYW50PSJpbmZvIiwgbGFiZWw9IjQ1JSIpCiAgICBSaW5nKHZhbHVlPTMwLCB2YXJpYW50PSJtdXRlZCIsIGxhYmVsPSIzMCUiKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Ring, Row

    with Row(css_class="gap-4 flex-wrap"):
        Ring(value=60, label="60%")
        Ring(value=100, variant="success", label="100%")
        Ring(value=72, variant="warning", label="72%")
        Ring(value=90, variant="destructive", label="90%")
        Ring(value=45, variant="info", label="45%")
        Ring(value=30, variant="muted", label="30%")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4 flex-wrap",
        "type": "Row",
        "children": [
          {
            "type": "Ring",
            "value": 60.0,
            "min": 0,
            "max": 100,
            "label": "60%",
            "variant": "default",
            "size": "default",
            "thickness": 6
          },
          {
            "type": "Ring",
            "value": 100.0,
            "min": 0,
            "max": 100,
            "label": "100%",
            "variant": "success",
            "size": "default",
            "thickness": 6
          },
          {
            "type": "Ring",
            "value": 72.0,
            "min": 0,
            "max": 100,
            "label": "72%",
            "variant": "warning",
            "size": "default",
            "thickness": 6
          },
          {
            "type": "Ring",
            "value": 90.0,
            "min": 0,
            "max": 100,
            "label": "90%",
            "variant": "destructive",
            "size": "default",
            "thickness": 6
          },
          {
            "type": "Ring",
            "value": 45.0,
            "min": 0,
            "max": 100,
            "label": "45%",
            "variant": "info",
            "size": "default",
            "thickness": 6
          },
          {
            "type": "Ring",
            "value": 30.0,
            "min": 0,
            "max": 100,
            "label": "30%",
            "variant": "muted",
            "size": "default",
            "thickness": 6
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Thickness

The `thickness` prop controls the stroke width of the ring arc. The default is 6.

<ComponentPreview json={{"view":{"cssClass":"gap-6 items-end","type":"Row","children":[{"type":"Ring","value":75.0,"min":0,"max":100,"label":"3","variant":"default","size":"default","thickness":3.0},{"type":"Ring","value":75.0,"min":0,"max":100,"label":"6","variant":"default","size":"default","thickness":6.0},{"type":"Ring","value":75.0,"min":0,"max":100,"label":"12","variant":"default","size":"default","thickness":12.0}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgUmluZywgUm93Cgp3aXRoIFJvdyhjc3NfY2xhc3M9ImdhcC02IGl0ZW1zLWVuZCIpOgogICAgUmluZyh2YWx1ZT03NSwgdGhpY2tuZXNzPTMsIGxhYmVsPSIzIikKICAgIFJpbmcodmFsdWU9NzUsIHRoaWNrbmVzcz02LCBsYWJlbD0iNiIpCiAgICBSaW5nKHZhbHVlPTc1LCB0aGlja25lc3M9MTIsIGxhYmVsPSIxMiIpCg">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Ring, Row

    with Row(css_class="gap-6 items-end"):
        Ring(value=75, thickness=3, label="3")
        Ring(value=75, thickness=6, label="6")
        Ring(value=75, thickness=12, label="12")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-6 items-end",
        "type": "Row",
        "children": [
          {
            "type": "Ring",
            "value": 75.0,
            "min": 0,
            "max": 100,
            "label": "3",
            "variant": "default",
            "size": "default",
            "thickness": 3.0
          },
          {
            "type": "Ring",
            "value": 75.0,
            "min": 0,
            "max": 100,
            "label": "6",
            "variant": "default",
            "size": "default",
            "thickness": 6.0
          },
          {
            "type": "Ring",
            "value": 75.0,
            "min": 0,
            "max": 100,
            "label": "12",
            "variant": "default",
            "size": "default",
            "thickness": 12.0
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Indicator Class

`indicator_class` applies Tailwind classes directly to the filled arc, just like Progress's `indicator_class` targets the bar. The Ring wrapper acts as a `group`, so `group-hover:` classes let you trigger effects when hovering anywhere on the ring.

Because the Ring arc is an SVG stroke, use `stroke-*` classes (not `bg-*`) to override colors.

<ComponentPreview json={{"view":{"cssClass":"gap-6","type":"Row","children":[{"type":"Ring","value":72.0,"min":0,"max":100,"label":"72%","variant":"info","size":"default","thickness":6,"indicatorClass":"group-hover:drop-shadow-[0_0_20px_rgba(59,130,246,0.8)]"},{"type":"Ring","value":90.0,"min":0,"max":100,"label":"90%","variant":"default","size":"default","thickness":6,"indicatorClass":"stroke-emerald-500 group-hover:drop-shadow-[0_0_20px_rgba(16,185,129,0.8)]"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgUmluZywgUm93Cgp3aXRoIFJvdyhjc3NfY2xhc3M9ImdhcC02Iik6CiAgICBSaW5nKAogICAgICAgIHZhbHVlPTcyLCBsYWJlbD0iNzIlIiwgdmFyaWFudD0iaW5mbyIsCiAgICAgICAgaW5kaWNhdG9yX2NsYXNzPSgKICAgICAgICAgICAgImdyb3VwLWhvdmVyOmRyb3Atc2hhZG93LVswXzBfMjBweF9yZ2JhKDU5LDEzMCwyNDYsMC44KV0iCiAgICAgICAgKSwKICAgICkKICAgIFJpbmcoCiAgICAgICAgdmFsdWU9OTAsIGxhYmVsPSI5MCUiLAogICAgICAgIGluZGljYXRvcl9jbGFzcz0oCiAgICAgICAgICAgICJzdHJva2UtZW1lcmFsZC01MDAiCiAgICAgICAgICAgICIgZ3JvdXAtaG92ZXI6ZHJvcC1zaGFkb3ctWzBfMF8yMHB4X3JnYmEoMTYsMTg1LDEyOSwwLjgpXSIKICAgICAgICApLAogICAgKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Ring, Row

    with Row(css_class="gap-6"):
        Ring(
            value=72, label="72%", variant="info",
            indicator_class=(
                "group-hover:drop-shadow-[0_0_20px_rgba(59,130,246,0.8)]"
            ),
        )
        Ring(
            value=90, label="90%",
            indicator_class=(
                "stroke-emerald-500"
                " group-hover:drop-shadow-[0_0_20px_rgba(16,185,129,0.8)]"
            ),
        )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-6",
        "type": "Row",
        "children": [
          {
            "type": "Ring",
            "value": 72.0,
            "min": 0,
            "max": 100,
            "label": "72%",
            "variant": "info",
            "size": "default",
            "thickness": 6,
            "indicatorClass": "group-hover:drop-shadow-[0_0_20px_rgba(59,130,246,0.8)]"
          },
          {
            "type": "Ring",
            "value": 90.0,
            "min": 0,
            "max": 100,
            "label": "90%",
            "variant": "default",
            "size": "default",
            "thickness": 6,
            "indicatorClass": "stroke-emerald-500 group-hover:drop-shadow-[0_0_20px_rgba(16,185,129,0.8)]"
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Target Marker

The `target` prop renders a tick mark on the ring at a specific position. Use `target_class` to style it.

<ComponentPreview json={{"view":{"cssClass":"gap-6","type":"Row","children":[{"type":"Ring","value":55.0,"min":0,"max":100,"label":"55%","variant":"default","size":"default","thickness":6,"target":75.0},{"type":"Ring","value":90.0,"min":0,"max":100,"label":"90%","variant":"success","size":"default","thickness":6,"target":75.0},{"type":"Ring","value":60.0,"min":0,"max":100,"label":"60%","variant":"info","size":"default","thickness":6,"target":80.0,"targetClass":"stroke-red-500"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgUmluZywgUm93Cgp3aXRoIFJvdyhjc3NfY2xhc3M9ImdhcC02Iik6CiAgICBSaW5nKHZhbHVlPTU1LCB0YXJnZXQ9NzUsIGxhYmVsPSI1NSUiKQogICAgUmluZyh2YWx1ZT05MCwgdGFyZ2V0PTc1LCB2YXJpYW50PSJzdWNjZXNzIiwgbGFiZWw9IjkwJSIpCiAgICBSaW5nKAogICAgICAgIHZhbHVlPTYwLCB0YXJnZXQ9ODAsIHZhcmlhbnQ9ImluZm8iLAogICAgICAgIGxhYmVsPSI2MCUiLCB0YXJnZXRfY2xhc3M9InN0cm9rZS1yZWQtNTAwIiwKICAgICkK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Ring, Row

    with Row(css_class="gap-6"):
        Ring(value=55, target=75, label="55%")
        Ring(value=90, target=75, variant="success", label="90%")
        Ring(
            value=60, target=80, variant="info",
            label="60%", target_class="stroke-red-500",
        )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-6",
        "type": "Row",
        "children": [
          {
            "type": "Ring",
            "value": 55.0,
            "min": 0,
            "max": 100,
            "label": "55%",
            "variant": "default",
            "size": "default",
            "thickness": 6,
            "target": 75.0
          },
          {
            "type": "Ring",
            "value": 90.0,
            "min": 0,
            "max": 100,
            "label": "90%",
            "variant": "success",
            "size": "default",
            "thickness": 6,
            "target": 75.0
          },
          {
            "type": "Ring",
            "value": 60.0,
            "min": 0,
            "max": 100,
            "label": "60%",
            "variant": "info",
            "size": "default",
            "thickness": 6,
            "target": 80.0,
            "targetClass": "stroke-red-500"
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Custom Range

Set `min` and `max` to define a range other than 0–100. The renderer normalizes the value to a percentage automatically.

<ComponentPreview json={{"view":{"cssClass":"gap-6","type":"Row","children":[{"type":"Ring","value":72.0,"min":60.0,"max":100.0,"label":"72\u00b0F","variant":"warning","size":"default","thickness":6},{"type":"Ring","value":3.0,"min":0,"max":5.0,"label":"3/5","variant":"info","size":"default","thickness":6}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgUmluZywgUm93Cgp3aXRoIFJvdyhjc3NfY2xhc3M9ImdhcC02Iik6CiAgICBSaW5nKHZhbHVlPTcyLCBtaW49NjAsIG1heD0xMDAsIHZhcmlhbnQ9Indhcm5pbmciLCBsYWJlbD0iNzLCsEYiKQogICAgUmluZyh2YWx1ZT0zLCBtYXg9NSwgdmFyaWFudD0iaW5mbyIsIGxhYmVsPSIzLzUiKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Ring, Row

    with Row(css_class="gap-6"):
        Ring(value=72, min=60, max=100, variant="warning", label="72°F")
        Ring(value=3, max=5, variant="info", label="3/5")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-6",
        "type": "Row",
        "children": [
          {
            "type": "Ring",
            "value": 72.0,
            "min": 60.0,
            "max": 100.0,
            "label": "72\u00b0F",
            "variant": "warning",
            "size": "default",
            "thickness": 6
          },
          {
            "type": "Ring",
            "value": 3.0,
            "min": 0,
            "max": 5.0,
            "label": "3/5",
            "variant": "info",
            "size": "default",
            "thickness": 6
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Custom Center Content

Use Ring as a container to place arbitrary components in the center. When children are present, they replace the `label` text.

<ComponentPreview json={{"view":{"cssClass":"gap-6","type":"Row","children":[{"type":"Ring","value":75.0,"min":0,"max":100,"variant":"success","size":"lg","thickness":8.0,"children":[{"cssClass":"text-3xl font-bold","content":"75%","type":"Text"}]},{"type":"Ring","value":3.0,"min":0,"max":5.0,"variant":"info","size":"lg","thickness":8.0,"children":[{"cssClass":"text-center","type":"Column","children":[{"cssClass":"text-2xl font-bold","content":"3/5","type":"Text"},{"cssClass":"text-xs text-muted-foreground","content":"steps","type":"Text"}]}]}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBSaW5nLCBSb3csIFRleHQKCndpdGggUm93KGNzc19jbGFzcz0iZ2FwLTYiKToKICAgIHdpdGggUmluZyh2YWx1ZT03NSwgdmFyaWFudD0ic3VjY2VzcyIsIHNpemU9ImxnIiwgdGhpY2tuZXNzPTgpOgogICAgICAgIFRleHQoIjc1JSIsIGNzc19jbGFzcz0idGV4dC0zeGwgZm9udC1ib2xkIikKICAgIHdpdGggUmluZyh2YWx1ZT0zLCBtYXg9NSwgdmFyaWFudD0iaW5mbyIsIHNpemU9ImxnIiwgdGhpY2tuZXNzPTgpOgogICAgICAgIHdpdGggQ29sdW1uKGNzc19jbGFzcz0idGV4dC1jZW50ZXIiKToKICAgICAgICAgICAgVGV4dCgiMy81IiwgY3NzX2NsYXNzPSJ0ZXh0LTJ4bCBmb250LWJvbGQiKQogICAgICAgICAgICBUZXh0KCJzdGVwcyIsIGNzc19jbGFzcz0idGV4dC14cyB0ZXh0LW11dGVkLWZvcmVncm91bmQiKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Column, Ring, Row, Text

    with Row(css_class="gap-6"):
        with Ring(value=75, variant="success", size="lg", thickness=8):
            Text("75%", css_class="text-3xl font-bold")
        with Ring(value=3, max=5, variant="info", size="lg", thickness=8):
            with Column(css_class="text-center"):
                Text("3/5", css_class="text-2xl font-bold")
                Text("steps", css_class="text-xs text-muted-foreground")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-6",
        "type": "Row",
        "children": [
          {
            "type": "Ring",
            "value": 75.0,
            "min": 0,
            "max": 100,
            "variant": "success",
            "size": "lg",
            "thickness": 8.0,
            "children": [{"cssClass": "text-3xl font-bold", "content": "75%", "type": "Text"}]
          },
          {
            "type": "Ring",
            "value": 3.0,
            "min": 0,
            "max": 5.0,
            "variant": "info",
            "size": "lg",
            "thickness": 8.0,
            "children": [
              {
                "cssClass": "text-center",
                "type": "Column",
                "children": [
                  {"cssClass": "text-2xl font-bold", "content": "3/5", "type": "Text"},
                  {
                    "cssClass": "text-xs text-muted-foreground",
                    "content": "steps",
                    "type": "Text"
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

## API Reference

<Card icon="code" title="Ring Parameters">
  <ParamField body="value" type="float | str" default="0">
    Current value. Can be a template expression for dynamic binding.
  </ParamField>

  <ParamField body="min" type="float" default="0">
    Minimum value. The renderer normalizes `(value - min) / (max - min)` to a 0–100 percentage.
  </ParamField>

  <ParamField body="max" type="float" default="100">
    Maximum value.
  </ParamField>

  <ParamField body="label" type="str | None" default="None">
    Text displayed in the center of the ring. Supports template expressions. Ignored when children are present.
  </ParamField>

  <ParamField body="children" type="list[Component]" default="[]">
    Arbitrary components rendered in the center of the ring, replacing the label.
  </ParamField>

  <ParamField body="variant" type="str" default="default">
    Visual variant: `"default"`, `"success"`, `"warning"`, `"destructive"`, `"info"`, `"muted"`.
  </ParamField>

  <ParamField body="size" type="str" default="default">
    Ring diameter: `"sm"` (64px), `"default"` (96px), `"lg"` (128px).
  </ParamField>

  <ParamField body="thickness" type="float" default="6">
    Stroke width of the ring arc in pixels.
  </ParamField>

  <ParamField body="target" type="float | str | None" default="None">
    Target marker position. Renders a tick mark on the ring at this value.
  </ParamField>

  <ParamField body="indicator_class" type="str | None" default="None">
    Tailwind classes applied to the filled arc. The Ring wrapper is a `group`, so `group-hover:` classes trigger on hover anywhere on the ring.
  </ParamField>

  <ParamField body="target_class" type="str | None" default="None">
    Tailwind classes for the target tick mark.
  </ParamField>

  <ParamField body="css_class" type="str | None" default="None">
    Tailwind classes for the outer container.
  </ParamField>
</Card>

## Protocol Reference

```json Ring theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "Ring",
  "children?": "[Component]",
  "let?": "object",
  "value?": "number | string",
  "min?": 0,
  "max?": 100,
  "label?": "string",
  "variant?": "default | success | warning | destructive | info | muted",
  "size?": "sm | default | lg",
  "thickness?": 6,
  "indicatorClass?": "string",
  "cssClass?": "string"
}
```

For the complete protocol schema, see [Ring](/protocol/ring).


Built with [Mintlify](https://mintlify.com).