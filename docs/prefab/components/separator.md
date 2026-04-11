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

# Separator

> Visual divider between content sections.

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

Separators create visual divisions between content areas.

## Basic Usage

<ComponentPreview json={{"view":{"type":"Column","children":[{"content":"Content above the separator","type":"P"},{"cssClass":"my-4","type":"Separator","orientation":"horizontal"},{"content":"Content below the separator","type":"P"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgKAogICAgQ29sdW1uLAogICAgUCwKICAgIFNlcGFyYXRvciwKKQoKd2l0aCBDb2x1bW4oKToKICAgIFAoIkNvbnRlbnQgYWJvdmUgdGhlIHNlcGFyYXRvciIpCiAgICBTZXBhcmF0b3Ioc3BhY2luZz00KQogICAgUCgiQ29udGVudCBiZWxvdyB0aGUgc2VwYXJhdG9yIikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import (
        Column,
        P,
        Separator,
    )

    with Column():
        P("Content above the separator")
        Separator(spacing=4)
        P("Content below the separator")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "Column",
        "children": [
          {"content": "Content above the separator", "type": "P"},
          {"cssClass": "my-4", "type": "Separator", "orientation": "horizontal"},
          {"content": "Content below the separator", "type": "P"}
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Vertical Orientation

<ComponentPreview json={{"view":{"cssClass":"gap-4 items-center","type":"Row","children":[{"content":"Left","code":false,"type":"Span"},{"cssClass":"h-4","type":"Separator","orientation":"vertical"},{"content":"Middle","code":false,"type":"Span"},{"cssClass":"h-4","type":"Separator","orientation":"vertical"},{"content":"Right","code":false,"type":"Span"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgKAogICAgUm93LAogICAgU2VwYXJhdG9yLAogICAgU3BhbiwKKQoKd2l0aCBSb3coZ2FwPTQsIGNzc19jbGFzcz0iaXRlbXMtY2VudGVyIik6CiAgICBTcGFuKCJMZWZ0IikKICAgIFNlcGFyYXRvcihvcmllbnRhdGlvbj0idmVydGljYWwiLCBjc3NfY2xhc3M9ImgtNCIpCiAgICBTcGFuKCJNaWRkbGUiKQogICAgU2VwYXJhdG9yKG9yaWVudGF0aW9uPSJ2ZXJ0aWNhbCIsIGNzc19jbGFzcz0iaC00IikKICAgIFNwYW4oIlJpZ2h0IikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import (
        Row,
        Separator,
        Span,
    )

    with Row(gap=4, css_class="items-center"):
        Span("Left")
        Separator(orientation="vertical", css_class="h-4")
        Span("Middle")
        Separator(orientation="vertical", css_class="h-4")
        Span("Right")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4 items-center",
        "type": "Row",
        "children": [
          {"content": "Left", "code": false, "type": "Span"},
          {"cssClass": "h-4", "type": "Separator", "orientation": "vertical"},
          {"content": "Middle", "code": false, "type": "Span"},
          {"cssClass": "h-4", "type": "Separator", "orientation": "vertical"},
          {"content": "Right", "code": false, "type": "Span"}
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## In Card Content

<ComponentPreview json={{"view":{"type":"Card","children":[{"type":"CardContent","children":[{"content":"First section","type":"P"},{"cssClass":"my-4","type":"Separator","orientation":"horizontal"},{"content":"Second section","type":"P"},{"cssClass":"my-4","type":"Separator","orientation":"horizontal"},{"content":"Third section","type":"P"}]}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgKAogICAgQ2FyZCwKICAgIENhcmRDb250ZW50LAogICAgUCwKICAgIFNlcGFyYXRvciwKKQoKd2l0aCBDYXJkKCk6CiAgICB3aXRoIENhcmRDb250ZW50KCk6CiAgICAgICAgUCgiRmlyc3Qgc2VjdGlvbiIpCiAgICAgICAgU2VwYXJhdG9yKHNwYWNpbmc9NCkKICAgICAgICBQKCJTZWNvbmQgc2VjdGlvbiIpCiAgICAgICAgU2VwYXJhdG9yKHNwYWNpbmc9NCkKICAgICAgICBQKCJUaGlyZCBzZWN0aW9uIikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import (
        Card,
        CardContent,
        P,
        Separator,
    )

    with Card():
        with CardContent():
            P("First section")
            Separator(spacing=4)
            P("Second section")
            Separator(spacing=4)
            P("Third section")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "Card",
        "children": [
          {
            "type": "CardContent",
            "children": [
              {"content": "First section", "type": "P"},
              {"cssClass": "my-4", "type": "Separator", "orientation": "horizontal"},
              {"content": "Second section", "type": "P"},
              {"cssClass": "my-4", "type": "Separator", "orientation": "horizontal"},
              {"content": "Third section", "type": "P"}
            ]
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## API Reference

<Card icon="code" title="Separator Parameters">
  <ParamField body="orientation" type="str" default="horizontal">
    Separator direction: `"horizontal"`, `"vertical"`.
  </ParamField>

  <ParamField body="spacing" type="int | None" default="None">
    Space around the separator using the Tailwind spacing scale. Adds vertical margin (`my-N`) for horizontal separators and horizontal margin (`mx-N`) for vertical separators.
  </ParamField>

  <ParamField body="css_class" type="str | None" default="None">
    Additional Tailwind CSS classes. Useful for controlling height/width.
  </ParamField>
</Card>

## Protocol Reference

```json Separator theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "Separator",
  "orientation?": "horizontal | vertical",
  "spacing?": "number",
  "cssClass?": "string"
}
```

For the complete protocol schema, see [Separator](/protocol/separator).


Built with [Mintlify](https://mintlify.com).