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

# Row

> Horizontal flex container for arranging children side-by-side.

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

Row arranges children horizontally with flexbox. Use `gap` to control spacing between items.

## Basic Usage

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgKAogICAgRGl2LAogICAgUm93LAopCgp3aXRoIFJvdyhnYXA9NCk6CiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCg">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import (
        Div,
        Row,
    )

    with Row(gap=4):
        Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Row",
        "children": [
          {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
          {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
          {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"}
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Gap

Gap controls the spacing between children. Larger values give more visual separation.

<Tabs>
  <Tab title="gap=4">
    <ComponentPreview json={{"view":{"cssClass":"gap-4 p-3 border-3 border-dashed","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgRGl2LCBSb3cKCndpdGggUm93KGdhcD00LCBjc3NfY2xhc3M9InAtMyBib3JkZXItMyBib3JkZXItZGFzaGVkIik6CiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCg">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Div, Row

        with Row(gap=4, css_class="p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-4 p-3 border-3 border-dashed",
            "type": "Row",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="gap=8">
    <ComponentPreview json={{"view":{"cssClass":"gap-8 p-3 border-3 border-dashed","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgRGl2LCBSb3cKCndpdGggUm93KGdhcD04LCBjc3NfY2xhc3M9InAtMyBib3JkZXItMyBib3JkZXItZGFzaGVkIik6CiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCg">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Div, Row

        with Row(gap=8, css_class="p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-8 p-3 border-3 border-dashed",
            "type": "Row",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="gap=12">
    <ComponentPreview json={{"view":{"cssClass":"gap-12 p-3 border-3 border-dashed","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgRGl2LCBSb3cKCndpdGggUm93KGdhcD0xMiwgY3NzX2NsYXNzPSJwLTMgYm9yZGVyLTMgYm9yZGVyLWRhc2hlZCIpOgogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQo">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Div, Row

        with Row(gap=12, css_class="p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-12 p-3 border-3 border-dashed",
            "type": "Row",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>
</Tabs>

## Alignment

`align` controls vertical alignment of children. The difference is visible when children have different heights.

<Tabs>
  <Tab title="align=&#x22;start&#x22;">
    <ComponentPreview json={{"view":{"cssClass":"gap-4 items-start p-3 border-3 border-dashed","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md h-8 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-16 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgRGl2LCBSb3cKCndpdGggUm93KGdhcD00LCBhbGlnbj0ic3RhcnQiLCBjc3NfY2xhc3M9InAtMyBib3JkZXItMyBib3JkZXItZGFzaGVkIik6CiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtOCB3LTIwIikKICAgIERpdihjc3NfY2xhc3M9ImJnLWVtZXJhbGQtNTAwIHJvdW5kZWQtbWQgaC0xNiB3LTIwIikKICAgIERpdihjc3NfY2xhc3M9ImJnLWVtZXJhbGQtNTAwIHJvdW5kZWQtbWQgaC0xMCB3LTIwIikK">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Div, Row

        with Row(gap=4, align="start", css_class="p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-8 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-16 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-4 items-start p-3 border-3 border-dashed",
            "type": "Row",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-8 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-16 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="align=&#x22;center&#x22;">
    <ComponentPreview json={{"view":{"cssClass":"gap-4 items-center p-3 border-3 border-dashed","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md h-8 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-16 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgRGl2LCBSb3cKCndpdGggUm93KGdhcD00LCBhbGlnbj0iY2VudGVyIiwgY3NzX2NsYXNzPSJwLTMgYm9yZGVyLTMgYm9yZGVyLWRhc2hlZCIpOgogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTggdy0yMCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTYgdy0yMCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCg">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Div, Row

        with Row(gap=4, align="center", css_class="p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-8 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-16 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-4 items-center p-3 border-3 border-dashed",
            "type": "Row",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-8 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-16 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="align=&#x22;end&#x22;">
    <ComponentPreview json={{"view":{"cssClass":"gap-4 items-end p-3 border-3 border-dashed","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md h-8 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-16 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgRGl2LCBSb3cKCndpdGggUm93KGdhcD00LCBhbGlnbj0iZW5kIiwgY3NzX2NsYXNzPSJwLTMgYm9yZGVyLTMgYm9yZGVyLWRhc2hlZCIpOgogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTggdy0yMCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTYgdy0yMCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCg">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Div, Row

        with Row(gap=4, align="end", css_class="p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-8 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-16 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-4 items-end p-3 border-3 border-dashed",
            "type": "Row",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-8 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-16 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="align=&#x22;baseline&#x22;">
    Baseline aligns children along the invisible line that text sits on. Unlike `center`, which vertically centers boxes, `baseline` makes text of different sizes read naturally — as if on the same line of a page.

    <ComponentPreview json={{"view":{"cssClass":"gap-4 items-baseline p-3 border-3 border-dashed","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md px-3 py-1 text-white text-sm","content":"Small","code":false,"type":"Span"},{"cssClass":"bg-emerald-500 rounded-md px-3 py-2 text-white text-2xl","content":"Large","code":false,"type":"Span"},{"cssClass":"bg-emerald-500 rounded-md px-3 py-1 text-white text-base","content":"Medium","code":false,"type":"Span"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgUm93LCBTcGFuCgp3aXRoIFJvdyhnYXA9NCwgYWxpZ249ImJhc2VsaW5lIiwgY3NzX2NsYXNzPSJwLTMgYm9yZGVyLTMgYm9yZGVyLWRhc2hlZCIpOgogICAgU3BhbigKICAgICAgICAiU21hbGwiLAogICAgICAgIGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCAiCiAgICAgICAgInB4LTMgcHktMSB0ZXh0LXdoaXRlIHRleHQtc20iLAogICAgKQogICAgU3BhbigKICAgICAgICAiTGFyZ2UiLAogICAgICAgIGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCAiCiAgICAgICAgInB4LTMgcHktMiB0ZXh0LXdoaXRlIHRleHQtMnhsIiwKICAgICkKICAgIFNwYW4oCiAgICAgICAgIk1lZGl1bSIsCiAgICAgICAgY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kICIKICAgICAgICAicHgtMyBweS0xIHRleHQtd2hpdGUgdGV4dC1iYXNlIiwKICAgICkK">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Row, Span

        with Row(gap=4, align="baseline", css_class="p-3 border-3 border-dashed"):
            Span(
                "Small",
                css_class="bg-emerald-500 rounded-md "
                "px-3 py-1 text-white text-sm",
            )
            Span(
                "Large",
                css_class="bg-emerald-500 rounded-md "
                "px-3 py-2 text-white text-2xl",
            )
            Span(
                "Medium",
                css_class="bg-emerald-500 rounded-md "
                "px-3 py-1 text-white text-base",
            )
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-4 items-baseline p-3 border-3 border-dashed",
            "type": "Row",
            "children": [
              {
                "cssClass": "bg-emerald-500 rounded-md px-3 py-1 text-white text-sm",
                "content": "Small",
                "code": false,
                "type": "Span"
              },
              {
                "cssClass": "bg-emerald-500 rounded-md px-3 py-2 text-white text-2xl",
                "content": "Large",
                "code": false,
                "type": "Span"
              },
              {
                "cssClass": "bg-emerald-500 rounded-md px-3 py-1 text-white text-base",
                "content": "Medium",
                "code": false,
                "type": "Span"
              }
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>
</Tabs>

## Justification

`justify` controls how children are distributed along the horizontal axis.

<Tabs>
  <Tab title="justify=&#x22;start&#x22;">
    <ComponentPreview json={{"view":{"cssClass":"gap-1 justify-start w-full p-3 border-3 border-dashed","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgRGl2LCBSb3cKCndpdGggUm93KGdhcD0xLCBqdXN0aWZ5PSJzdGFydCIsIGNzc19jbGFzcz0idy1mdWxsIHAtMyBib3JkZXItMyBib3JkZXItZGFzaGVkIik6CiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0yMCIpCg">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Div, Row

        with Row(gap=1, justify="start", css_class="w-full p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-1 justify-start w-full p-3 border-3 border-dashed",
            "type": "Row",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="justify=&#x22;center&#x22;">
    <ComponentPreview json={{"view":{"cssClass":"gap-1 justify-center w-full p-3 border-3 border-dashed","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgRGl2LCBSb3cKCndpdGggUm93KGdhcD0xLCBqdXN0aWZ5PSJjZW50ZXIiLCBjc3NfY2xhc3M9InctZnVsbCBwLTMgYm9yZGVyLTMgYm9yZGVyLWRhc2hlZCIpOgogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQo">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Div, Row

        with Row(gap=1, justify="center", css_class="w-full p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-1 justify-center w-full p-3 border-3 border-dashed",
            "type": "Row",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="justify=&#x22;end&#x22;">
    <ComponentPreview json={{"view":{"cssClass":"gap-1 justify-end w-full p-3 border-3 border-dashed","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgRGl2LCBSb3cKCndpdGggUm93KGdhcD0xLCBqdXN0aWZ5PSJlbmQiLCBjc3NfY2xhc3M9InctZnVsbCBwLTMgYm9yZGVyLTMgYm9yZGVyLWRhc2hlZCIpOgogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQo">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Div, Row

        with Row(gap=1, justify="end", css_class="w-full p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-1 justify-end w-full p-3 border-3 border-dashed",
            "type": "Row",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="justify=&#x22;between&#x22;">
    <ComponentPreview json={{"view":{"cssClass":"gap-1 justify-between w-full p-3 border-3 border-dashed","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgRGl2LCBSb3cKCndpdGggUm93KGdhcD0xLCBqdXN0aWZ5PSJiZXR3ZWVuIiwgY3NzX2NsYXNzPSJ3LWZ1bGwgcC0zIGJvcmRlci0zIGJvcmRlci1kYXNoZWQiKToKICAgIERpdihjc3NfY2xhc3M9ImJnLWVtZXJhbGQtNTAwIHJvdW5kZWQtbWQgaC0xMCB3LTIwIikKICAgIERpdihjc3NfY2xhc3M9ImJnLWVtZXJhbGQtNTAwIHJvdW5kZWQtbWQgaC0xMCB3LTIwIikKICAgIERpdihjc3NfY2xhc3M9ImJnLWVtZXJhbGQtNTAwIHJvdW5kZWQtbWQgaC0xMCB3LTIwIikK">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Div, Row

        with Row(gap=1, justify="between", css_class="w-full p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-1 justify-between w-full p-3 border-3 border-dashed",
            "type": "Row",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="justify=&#x22;around&#x22;">
    <ComponentPreview json={{"view":{"cssClass":"gap-1 justify-around w-full p-3 border-3 border-dashed","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgRGl2LCBSb3cKCndpdGggUm93KGdhcD0xLCBqdXN0aWZ5PSJhcm91bmQiLCBjc3NfY2xhc3M9InctZnVsbCBwLTMgYm9yZGVyLTMgYm9yZGVyLWRhc2hlZCIpOgogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQo">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Div, Row

        with Row(gap=1, justify="around", css_class="w-full p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-1 justify-around w-full p-3 border-3 border-dashed",
            "type": "Row",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="justify=&#x22;evenly&#x22;">
    <ComponentPreview json={{"view":{"cssClass":"gap-1 justify-evenly w-full p-3 border-3 border-dashed","type":"Row","children":[{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-20","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgRGl2LCBSb3cKCndpdGggUm93KGdhcD0xLCBqdXN0aWZ5PSJldmVubHkiLCBjc3NfY2xhc3M9InctZnVsbCBwLTMgYm9yZGVyLTMgYm9yZGVyLWRhc2hlZCIpOgogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMjAiKQo">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Div, Row

        with Row(gap=1, justify="evenly", css_class="w-full p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-20")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-1 justify-evenly w-full p-3 border-3 border-dashed",
            "type": "Row",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-20", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>
</Tabs>

## API Reference

<Card icon="code" title="Row Parameters">
  <ParamField body="gap" type="int | tuple | Responsive | None" default="None">
    Gap between children. An int maps to `gap-{n}`. A tuple `(x, y)` sets per-axis gaps; use `None` to skip an axis. A `Responsive()` sets different gaps at different breakpoints.
  </ParamField>

  <ParamField body="align" type="str | None" default="None">
    Cross-axis alignment: `"start"`, `"center"`, `"end"`, `"stretch"`, `"baseline"`.
  </ParamField>

  <ParamField body="justify" type="str | None" default="None">
    Main-axis distribution: `"start"`, `"center"`, `"end"`, `"between"`, `"around"`, `"evenly"`, `"stretch"`.
  </ParamField>

  <ParamField body="css_class" type="str | Responsive | None" default="None">
    Additional Tailwind CSS classes. A `Responsive()` compiles breakpoint-prefixed classes.
  </ParamField>
</Card>

## Protocol Reference

```json Row theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "Row",
  "children?": "[Component]",
  "let?": "object",
  "gap?": "number | Action[]",
  "align?": "start | center | end | stretch | baseline",
  "justify?": "start | center | end | between | around | evenly | stretch",
  "cssClass?": "string"
}
```

For the complete protocol schema, see [Row](/protocol/row).


Built with [Mintlify](https://mintlify.com).