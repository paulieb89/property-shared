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

# HoverCard

> Rich content panel that appears on hover.

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

HoverCards display rich content in a floating panel when users hover over a trigger element. The first child becomes the trigger; all remaining children become the panel content. For plain-text hover labels, [Tooltip](/components/tooltip) is simpler. For interactive content that needs to stay open (forms, menus), use [Popover](/components/popover) instead — it requires a click and stays open until dismissed.

## Basic Usage

<ComponentPreview height="200px" json={{"view":{"type":"HoverCard","children":[{"type":"Button","label":"@heart-of-gold","variant":"link","size":"default","disabled":false},{"cssClass":"gap-2","type":"Column","children":[{"content":"heart-of-gold","type":"Text"},{"content":"Infinite Improbability Drive vessel. Currently in orbit around Magrathea.","type":"Muted"},{"cssClass":"gap-4","type":"Row","children":[{"content":"Status: In Orbit","type":"Muted"},{"content":"Deployed 2h ago","type":"Muted"}]}]}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQnV0dG9uLCBDb2x1bW4sIEhvdmVyQ2FyZCwgTXV0ZWQsIFJvdywgVGV4dAoKd2l0aCBIb3ZlckNhcmQoKToKICAgIEJ1dHRvbigiQGhlYXJ0LW9mLWdvbGQiLCB2YXJpYW50PSJsaW5rIikKICAgIHdpdGggQ29sdW1uKGdhcD0yKToKICAgICAgICBUZXh0KCJoZWFydC1vZi1nb2xkIikKICAgICAgICBNdXRlZCgiSW5maW5pdGUgSW1wcm9iYWJpbGl0eSBEcml2ZSB2ZXNzZWwuIEN1cnJlbnRseSBpbiBvcmJpdCBhcm91bmQgTWFncmF0aGVhLiIpCiAgICAgICAgd2l0aCBSb3coZ2FwPTQpOgogICAgICAgICAgICBNdXRlZCgiU3RhdHVzOiBJbiBPcmJpdCIpCiAgICAgICAgICAgIE11dGVkKCJEZXBsb3llZCAyaCBhZ28iKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Button, Column, HoverCard, Muted, Row, Text

    with HoverCard():
        Button("@heart-of-gold", variant="link")
        with Column(gap=2):
            Text("heart-of-gold")
            Muted("Infinite Improbability Drive vessel. Currently in orbit around Magrathea.")
            with Row(gap=4):
                Muted("Status: In Orbit")
                Muted("Deployed 2h ago")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "HoverCard",
        "children": [
          {
            "type": "Button",
            "label": "@heart-of-gold",
            "variant": "link",
            "size": "default",
            "disabled": false
          },
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"content": "heart-of-gold", "type": "Text"},
              {
                "content": "Infinite Improbability Drive vessel. Currently in orbit around Magrathea.",
                "type": "Muted"
              },
              {
                "cssClass": "gap-4",
                "type": "Row",
                "children": [
                  {"content": "Status: In Orbit", "type": "Muted"},
                  {"content": "Deployed 2h ago", "type": "Muted"}
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

## Instant Hover

Set `open_delay=0` for immediate feedback, useful in dashboards and status displays where users are scanning quickly.

<ComponentPreview height="200px" json={{"view":{"type":"HoverCard","openDelay":0,"closeDelay":200,"children":[{"type":"Badge","label":"Healthy","variant":"default"},{"cssClass":"gap-2","type":"Column","children":[{"content":"weather-api","type":"Text"},{"content":"Uptime: 99.97%","type":"Muted"}]}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQmFkZ2UsIENvbHVtbiwgSG92ZXJDYXJkLCBNdXRlZCwgVGV4dAoKd2l0aCBIb3ZlckNhcmQob3Blbl9kZWxheT0wLCBjbG9zZV9kZWxheT0yMDApOgogICAgQmFkZ2UoIkhlYWx0aHkiKQogICAgd2l0aCBDb2x1bW4oZ2FwPTIpOgogICAgICAgIFRleHQoIndlYXRoZXItYXBpIikKICAgICAgICBNdXRlZCgiVXB0aW1lOiA5OS45NyUiKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Badge, Column, HoverCard, Muted, Text

    with HoverCard(open_delay=0, close_delay=200):
        Badge("Healthy")
        with Column(gap=2):
            Text("weather-api")
            Muted("Uptime: 99.97%")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "HoverCard",
        "openDelay": 0,
        "closeDelay": 200,
        "children": [
          {"type": "Badge", "label": "Healthy", "variant": "default"},
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"content": "weather-api", "type": "Text"},
              {"content": "Uptime: 99.97%", "type": "Muted"}
            ]
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Side Placement

Control which side the panel appears on. The renderer auto-adjusts if the card would overflow the viewport.

```python  theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
from prefab_ui.components import Badge, HoverCard, Text

with HoverCard(side="right"):
    Badge("Details")
    Text("Panel appears to the right of the trigger.")
```

## API Reference

<Card icon="code" title="HoverCard Parameters">
  <ParamField body="side" type="str | None" default="None">
    Preferred side to show the card: `"top"`, `"right"`, `"bottom"`, `"left"`.
  </ParamField>

  <ParamField body="open_delay" type="int | None" default="None">
    Delay in milliseconds before the card appears. Defaults to the Radix default (700ms). Set to `0` for instant hover.
  </ParamField>

  <ParamField body="close_delay" type="int | None" default="None">
    Delay in milliseconds before the card dismisses after the cursor leaves.
  </ParamField>

  <ParamField body="css_class" type="str | None" default="None">
    Additional Tailwind CSS classes.
  </ParamField>
</Card>

## Protocol Reference

```json HoverCard theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "HoverCard",
  "children?": "[Component]",
  "let?": "object",
  "side?": "top | right | bottom | left",
  "openDelay?": "number",
  "closeDelay?": "number",
  "cssClass?": "string"
}
```

For the complete protocol schema, see [HoverCard](/protocol/hover-card).


Built with [Mintlify](https://mintlify.com).