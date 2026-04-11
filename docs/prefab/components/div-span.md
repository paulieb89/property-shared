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

# Div & Span

> Unstyled block and inline containers for custom layouts and inline text.

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

Div and Span are unstyled primitives — the escape hatches for when Row, Column, and Grid don't express what you need. Both support `css_class` for Tailwind and `style` for arbitrary inline CSS.

## Div

A block container with no default styling. Style it through `css_class` or `style`:

<ComponentPreview json={{"view":{"cssClass":"flex items-center gap-3 rounded-lg border p-4","type":"Div","children":[{"cssClass":"bg-emerald-500 rounded-md h-8 w-8","type":"Div"},{"content":"Custom layout with Div","type":"P"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgKAogICAgRGl2LAogICAgUCwKKQoKd2l0aCBEaXYoY3NzX2NsYXNzPSJmbGV4IGl0ZW1zLWNlbnRlciBnYXAtMyByb3VuZGVkLWxnIGJvcmRlciBwLTQiKToKICAgIERpdihjc3NfY2xhc3M9ImJnLWVtZXJhbGQtNTAwIHJvdW5kZWQtbWQgaC04IHctOCIpCiAgICBQKCJDdXN0b20gbGF5b3V0IHdpdGggRGl2IikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import (
        Div,
        P,
    )

    with Div(css_class="flex items-center gap-3 rounded-lg border p-4"):
        Div(css_class="bg-emerald-500 rounded-md h-8 w-8")
        P("Custom layout with Div")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "flex items-center gap-3 rounded-lg border p-4",
        "type": "Div",
        "children": [
          {"cssClass": "bg-emerald-500 rounded-md h-8 w-8", "type": "Div"},
          {"content": "Custom layout with Div", "type": "P"}
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

For CSS that Tailwind can't express — vendor prefixes, `clamp()`, `mask-image`, etc. — use the `style` prop:

<ComponentPreview json={{"view":{"type":"Div","style":{"background":"linear-gradient(135deg, #667eea 0%, #764ba2 100%)","border-radius":"12px","padding":"24px"},"children":[{"cssClass":"text-white font-medium","content":"Styled with inline CSS","type":"P"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgKAogICAgRGl2LAogICAgUCwKKQoKd2l0aCBEaXYoc3R5bGU9ewogICAgImJhY2tncm91bmQiOiAibGluZWFyLWdyYWRpZW50KDEzNWRlZywgIzY2N2VlYSAwJSwgIzc2NGJhMiAxMDAlKSIsCiAgICAiYm9yZGVyLXJhZGl1cyI6ICIxMnB4IiwKICAgICJwYWRkaW5nIjogIjI0cHgiLAp9KToKICAgIFAoIlN0eWxlZCB3aXRoIGlubGluZSBDU1MiLCBjc3NfY2xhc3M9InRleHQtd2hpdGUgZm9udC1tZWRpdW0iKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import (
        Div,
        P,
    )

    with Div(style={
        "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
        "border-radius": "12px",
        "padding": "24px",
    }):
        P("Styled with inline CSS", css_class="text-white font-medium")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "Div",
        "style": {
          "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
          "border-radius": "12px",
          "padding": "24px"
        },
        "children": [
          {
            "cssClass": "text-white font-medium",
            "content": "Styled with inline CSS",
            "type": "P"
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Span

An inline text element with no default styling. Useful for inline annotations or colored text:

<ComponentPreview json={{"view":{"cssClass":"gap-2 items-baseline","type":"Row","children":[{"content":"Status:","type":"P"},{"cssClass":"text-sm text-success font-medium","content":"Online","code":false,"type":"Span"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgKAogICAgUCwKICAgIFJvdywKICAgIFNwYW4sCikKCndpdGggUm93KGdhcD0yLCBhbGlnbj0iYmFzZWxpbmUiKToKICAgIFAoIlN0YXR1czoiKQogICAgU3BhbigiT25saW5lIiwgY3NzX2NsYXNzPSJ0ZXh0LXNtIHRleHQtc3VjY2VzcyBmb250LW1lZGl1bSIpCg">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import (
        P,
        Row,
        Span,
    )

    with Row(gap=2, align="baseline"):
        P("Status:")
        Span("Online", css_class="text-sm text-success font-medium")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-2 items-baseline",
        "type": "Row",
        "children": [
          {"content": "Status:", "type": "P"},
          {
            "cssClass": "text-sm text-success font-medium",
            "content": "Online",
            "code": false,
            "type": "Span"
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## API Reference

<Card icon="code" title="Div Parameters">
  <ParamField body="css_class" type="str | None" default="None">
    Tailwind CSS classes. Div has no built-in styling.
  </ParamField>

  <ParamField body="style" type="dict[str, str] | None" default="None">
    Inline CSS styles for properties that Tailwind can't express.
  </ParamField>
</Card>

<Card icon="code" title="Span Parameters">
  <ParamField body="content" type="str" required>
    Text content. Can be passed as a positional argument.
  </ParamField>

  <ParamField body="css_class" type="str | None" default="None">
    Tailwind CSS classes. Span has no built-in styling.
  </ParamField>

  <ParamField body="style" type="dict[str, str] | None" default="None">
    Inline CSS styles for properties that Tailwind can't express.
  </ParamField>
</Card>

## Protocol Reference

```json Div theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "Div",
  "children?": "[Component]",
  "let?": "object",
  "style?": "object",
  "cssClass?": "string"
}
```

```json Span theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "Span",
  "content": "string (required)",
  "style?": "object",
  "cssClass?": "string"
}
```

For the complete protocol schema, see [Div](/protocol/div), [Span](/protocol/span).


Built with [Mintlify](https://mintlify.com).