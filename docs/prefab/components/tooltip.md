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

# Tooltip

> Hover text that appears on any component.

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

Tooltips show brief helper text when users hover over a component. Wrap any single element to add a tooltip. For richer hover content like status previews or structured data, use [HoverCard](/components/hover-card). For interactive content that stays open until dismissed, use [Popover](/components/popover).

## Basic Usage

<ComponentPreview height="140px" json={{"view":{"cssClass":"gap-4","type":"Row","children":[{"type":"Tooltip","content":"Save your current work","children":[{"type":"Button","label":"Save","variant":"default","size":"default","disabled":false}]},{"type":"Tooltip","content":"Discard unsaved changes","side":"bottom","children":[{"type":"Button","label":"Reset","variant":"outline","size":"default","disabled":false}]}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQnV0dG9uLCBSb3csIFRvb2x0aXAKCndpdGggUm93KGdhcD00KToKICAgIHdpdGggVG9vbHRpcCgiU2F2ZSB5b3VyIGN1cnJlbnQgd29yayIpOgogICAgICAgIEJ1dHRvbigiU2F2ZSIpCiAgICB3aXRoIFRvb2x0aXAoIkRpc2NhcmQgdW5zYXZlZCBjaGFuZ2VzIiwgc2lkZT0iYm90dG9tIik6CiAgICAgICAgQnV0dG9uKCJSZXNldCIsIHZhcmlhbnQ9Im91dGxpbmUiKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Button, Row, Tooltip

    with Row(gap=4):
        with Tooltip("Save your current work"):
            Button("Save")
        with Tooltip("Discard unsaved changes", side="bottom"):
            Button("Reset", variant="outline")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Row",
        "children": [
          {
            "type": "Tooltip",
            "content": "Save your current work",
            "children": [
              {
                "type": "Button",
                "label": "Save",
                "variant": "default",
                "size": "default",
                "disabled": false
              }
            ]
          },
          {
            "type": "Tooltip",
            "content": "Discard unsaved changes",
            "side": "bottom",
            "children": [
              {
                "type": "Button",
                "label": "Reset",
                "variant": "outline",
                "size": "default",
                "disabled": false
              }
            ]
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Side Placement

Control which side the tooltip appears on with the `side` parameter.

<ComponentPreview height="140px" json={{"view":{"cssClass":"gap-4","type":"Row","children":[{"type":"Tooltip","content":"Top","side":"top","children":[{"type":"Button","label":"Top","variant":"outline","size":"default","disabled":false}]},{"type":"Tooltip","content":"Right","side":"right","children":[{"type":"Button","label":"Right","variant":"outline","size":"default","disabled":false}]},{"type":"Tooltip","content":"Bottom","side":"bottom","children":[{"type":"Button","label":"Bottom","variant":"outline","size":"default","disabled":false}]},{"type":"Tooltip","content":"Left","side":"left","children":[{"type":"Button","label":"Left","variant":"outline","size":"default","disabled":false}]}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQnV0dG9uLCBSb3csIFRvb2x0aXAKCndpdGggUm93KGdhcD00KToKICAgIHdpdGggVG9vbHRpcCgiVG9wIiwgc2lkZT0idG9wIik6CiAgICAgICAgQnV0dG9uKCJUb3AiLCB2YXJpYW50PSJvdXRsaW5lIikKICAgIHdpdGggVG9vbHRpcCgiUmlnaHQiLCBzaWRlPSJyaWdodCIpOgogICAgICAgIEJ1dHRvbigiUmlnaHQiLCB2YXJpYW50PSJvdXRsaW5lIikKICAgIHdpdGggVG9vbHRpcCgiQm90dG9tIiwgc2lkZT0iYm90dG9tIik6CiAgICAgICAgQnV0dG9uKCJCb3R0b20iLCB2YXJpYW50PSJvdXRsaW5lIikKICAgIHdpdGggVG9vbHRpcCgiTGVmdCIsIHNpZGU9ImxlZnQiKToKICAgICAgICBCdXR0b24oIkxlZnQiLCB2YXJpYW50PSJvdXRsaW5lIikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Button, Row, Tooltip

    with Row(gap=4):
        with Tooltip("Top", side="top"):
            Button("Top", variant="outline")
        with Tooltip("Right", side="right"):
            Button("Right", variant="outline")
        with Tooltip("Bottom", side="bottom"):
            Button("Bottom", variant="outline")
        with Tooltip("Left", side="left"):
            Button("Left", variant="outline")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Row",
        "children": [
          {
            "type": "Tooltip",
            "content": "Top",
            "side": "top",
            "children": [
              {
                "type": "Button",
                "label": "Top",
                "variant": "outline",
                "size": "default",
                "disabled": false
              }
            ]
          },
          {
            "type": "Tooltip",
            "content": "Right",
            "side": "right",
            "children": [
              {
                "type": "Button",
                "label": "Right",
                "variant": "outline",
                "size": "default",
                "disabled": false
              }
            ]
          },
          {
            "type": "Tooltip",
            "content": "Bottom",
            "side": "bottom",
            "children": [
              {
                "type": "Button",
                "label": "Bottom",
                "variant": "outline",
                "size": "default",
                "disabled": false
              }
            ]
          },
          {
            "type": "Tooltip",
            "content": "Left",
            "side": "left",
            "children": [
              {
                "type": "Button",
                "label": "Left",
                "variant": "outline",
                "size": "default",
                "disabled": false
              }
            ]
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Instant Tooltips

By default, tooltips wait 700ms before appearing. Set `delay=0` for immediate feedback — useful in dashboards or status displays where users are scanning quickly.

<ComponentPreview height="140px" json={{"view":{"cssClass":"gap-4","type":"Row","children":[{"type":"Tooltip","content":"Deployed 2h ago","delay":0,"children":[{"type":"Badge","label":"In Orbit","variant":"default"}]},{"type":"Tooltip","content":"64% \u2014 ETA 12 min","delay":0,"children":[{"type":"Badge","label":"Deploying","variant":"secondary"}]},{"type":"Tooltip","content":"Position 3 of 8","delay":0,"children":[{"type":"Badge","label":"Queued","variant":"outline"}]}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQmFkZ2UsIFJvdywgVG9vbHRpcAoKd2l0aCBSb3coZ2FwPTQpOgogICAgd2l0aCBUb29sdGlwKCJEZXBsb3llZCAyaCBhZ28iLCBkZWxheT0wKToKICAgICAgICBCYWRnZSgiSW4gT3JiaXQiKQogICAgd2l0aCBUb29sdGlwKCI2NCUg4oCUIEVUQSAxMiBtaW4iLCBkZWxheT0wKToKICAgICAgICBCYWRnZSgiRGVwbG95aW5nIiwgdmFyaWFudD0ic2Vjb25kYXJ5IikKICAgIHdpdGggVG9vbHRpcCgiUG9zaXRpb24gMyBvZiA4IiwgZGVsYXk9MCk6CiAgICAgICAgQmFkZ2UoIlF1ZXVlZCIsIHZhcmlhbnQ9Im91dGxpbmUiKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Badge, Row, Tooltip

    with Row(gap=4):
        with Tooltip("Deployed 2h ago", delay=0):
            Badge("In Orbit")
        with Tooltip("64% — ETA 12 min", delay=0):
            Badge("Deploying", variant="secondary")
        with Tooltip("Position 3 of 8", delay=0):
            Badge("Queued", variant="outline")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Row",
        "children": [
          {
            "type": "Tooltip",
            "content": "Deployed 2h ago",
            "delay": 0,
            "children": [{"type": "Badge", "label": "In Orbit", "variant": "default"}]
          },
          {
            "type": "Tooltip",
            "content": "64% \u2014 ETA 12 min",
            "delay": 0,
            "children": [{"type": "Badge", "label": "Deploying", "variant": "secondary"}]
          },
          {
            "type": "Tooltip",
            "content": "Position 3 of 8",
            "delay": 0,
            "children": [{"type": "Badge", "label": "Queued", "variant": "outline"}]
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## API Reference

<Card icon="code" title="Tooltip Parameters">
  <ParamField body="content" type="str" required>
    Tooltip text. Can be passed as a positional argument.
  </ParamField>

  <ParamField body="side" type="str | None" default="None">
    Which side to show the tooltip: `"top"`, `"right"`, `"bottom"`, `"left"`.
  </ParamField>

  <ParamField body="delay" type="int | None" default="None">
    Delay in milliseconds before showing the tooltip. Defaults to 700ms. Set to `0` for instant display.
  </ParamField>

  <ParamField body="css_class" type="str | None" default="None">
    Additional Tailwind CSS classes.
  </ParamField>
</Card>

## Protocol Reference

```json Tooltip theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "Tooltip",
  "children?": "[Component]",
  "let?": "object",
  "content": "string (required)",
  "side?": "top | right | bottom | left",
  "delay?": "number",
  "cssClass?": "string"
}
```

For the complete protocol schema, see [Tooltip](/protocol/tooltip).


Built with [Mintlify](https://mintlify.com).