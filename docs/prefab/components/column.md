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

# Column

> Vertical flex container for stacking children top-to-bottom.

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

Column arranges children vertically. Use `gap` to control spacing between items.

## Basic Usage

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Column","children":[{"cssClass":"bg-emerald-500 rounded-md h-10","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgKAogICAgQ29sdW1uLAogICAgRGl2LAopCgp3aXRoIENvbHVtbihnYXA9NCk6CiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIikKICAgIERpdihjc3NfY2xhc3M9ImJnLWVtZXJhbGQtNTAwIHJvdW5kZWQtbWQgaC0xMCIpCg">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import (
        Column,
        Div,
    )

    with Column(gap=4):
        Div(css_class="bg-emerald-500 rounded-md h-10")
        Div(css_class="bg-emerald-500 rounded-md h-10")
        Div(css_class="bg-emerald-500 rounded-md h-10")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Column",
        "children": [
          {"cssClass": "bg-emerald-500 rounded-md h-10", "type": "Div"},
          {"cssClass": "bg-emerald-500 rounded-md h-10", "type": "Div"},
          {"cssClass": "bg-emerald-500 rounded-md h-10", "type": "Div"}
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Gap

<Tabs>
  <Tab title="gap=4">
    <ComponentPreview json={{"view":{"cssClass":"gap-4 p-3 border-3 border-dashed","type":"Column","children":[{"cssClass":"bg-emerald-500 rounded-md h-10","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBEaXYKCndpdGggQ29sdW1uKGdhcD00LCBjc3NfY2xhc3M9InAtMyBib3JkZXItMyBib3JkZXItZGFzaGVkIik6CiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIikKICAgIERpdihjc3NfY2xhc3M9ImJnLWVtZXJhbGQtNTAwIHJvdW5kZWQtbWQgaC0xMCIpCg">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Column, Div

        with Column(gap=4, css_class="p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10")
            Div(css_class="bg-emerald-500 rounded-md h-10")
            Div(css_class="bg-emerald-500 rounded-md h-10")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-4 p-3 border-3 border-dashed",
            "type": "Column",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="gap=8">
    <ComponentPreview json={{"view":{"cssClass":"gap-8 p-3 border-3 border-dashed","type":"Column","children":[{"cssClass":"bg-emerald-500 rounded-md h-10","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBEaXYKCndpdGggQ29sdW1uKGdhcD04LCBjc3NfY2xhc3M9InAtMyBib3JkZXItMyBib3JkZXItZGFzaGVkIik6CiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIikKICAgIERpdihjc3NfY2xhc3M9ImJnLWVtZXJhbGQtNTAwIHJvdW5kZWQtbWQgaC0xMCIpCg">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Column, Div

        with Column(gap=8, css_class="p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10")
            Div(css_class="bg-emerald-500 rounded-md h-10")
            Div(css_class="bg-emerald-500 rounded-md h-10")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-8 p-3 border-3 border-dashed",
            "type": "Column",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="gap=12">
    <ComponentPreview json={{"view":{"cssClass":"gap-12 p-3 border-3 border-dashed","type":"Column","children":[{"cssClass":"bg-emerald-500 rounded-md h-10","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBEaXYKCndpdGggQ29sdW1uKGdhcD0xMiwgY3NzX2NsYXNzPSJwLTMgYm9yZGVyLTMgYm9yZGVyLWRhc2hlZCIpOgogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIikKICAgIERpdihjc3NfY2xhc3M9ImJnLWVtZXJhbGQtNTAwIHJvdW5kZWQtbWQgaC0xMCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAiKQo">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Column, Div

        with Column(gap=12, css_class="p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10")
            Div(css_class="bg-emerald-500 rounded-md h-10")
            Div(css_class="bg-emerald-500 rounded-md h-10")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-12 p-3 border-3 border-dashed",
            "type": "Column",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>
</Tabs>

## Alignment

In a Column, `align` controls horizontal alignment. The difference is visible when children have different widths.

<Tabs>
  <Tab title="align=&#x22;start&#x22;">
    <ComponentPreview json={{"view":{"cssClass":"gap-4 items-start p-3 border-3 border-dashed","type":"Column","children":[{"cssClass":"bg-emerald-500 rounded-md h-10 w-full","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-3/4","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-1/2","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBEaXYKCndpdGggQ29sdW1uKGdhcD00LCBhbGlnbj0ic3RhcnQiLCBjc3NfY2xhc3M9InAtMyBib3JkZXItMyBib3JkZXItZGFzaGVkIik6CiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy1mdWxsIikKICAgIERpdihjc3NfY2xhc3M9ImJnLWVtZXJhbGQtNTAwIHJvdW5kZWQtbWQgaC0xMCB3LTMvNCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0xLzIiKQo">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Column, Div

        with Column(gap=4, align="start", css_class="p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10 w-full")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-3/4")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-1/2")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-4 items-start p-3 border-3 border-dashed",
            "type": "Column",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-full", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-3/4", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-1/2", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="align=&#x22;center&#x22;">
    <ComponentPreview json={{"view":{"cssClass":"gap-4 items-center p-3 border-3 border-dashed","type":"Column","children":[{"cssClass":"bg-emerald-500 rounded-md h-10 w-full","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-3/4","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-1/2","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBEaXYKCndpdGggQ29sdW1uKGdhcD00LCBhbGlnbj0iY2VudGVyIiwgY3NzX2NsYXNzPSJwLTMgYm9yZGVyLTMgYm9yZGVyLWRhc2hlZCIpOgogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctZnVsbCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0zLzQiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMS8yIikK">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Column, Div

        with Column(gap=4, align="center", css_class="p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10 w-full")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-3/4")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-1/2")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-4 items-center p-3 border-3 border-dashed",
            "type": "Column",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-full", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-3/4", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-1/2", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>

  <Tab title="align=&#x22;end&#x22;">
    <ComponentPreview json={{"view":{"cssClass":"gap-4 items-end p-3 border-3 border-dashed","type":"Column","children":[{"cssClass":"bg-emerald-500 rounded-md h-10 w-full","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-3/4","type":"Div"},{"cssClass":"bg-emerald-500 rounded-md h-10 w-1/2","type":"Div"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBEaXYKCndpdGggQ29sdW1uKGdhcD00LCBhbGlnbj0iZW5kIiwgY3NzX2NsYXNzPSJwLTMgYm9yZGVyLTMgYm9yZGVyLWRhc2hlZCIpOgogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctZnVsbCIpCiAgICBEaXYoY3NzX2NsYXNzPSJiZy1lbWVyYWxkLTUwMCByb3VuZGVkLW1kIGgtMTAgdy0zLzQiKQogICAgRGl2KGNzc19jbGFzcz0iYmctZW1lcmFsZC01MDAgcm91bmRlZC1tZCBoLTEwIHctMS8yIikK">
      <CodeGroup>
        ```python Python highlight={3} icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        from prefab_ui.components import Column, Div

        with Column(gap=4, align="end", css_class="p-3 border-3 border-dashed"):
            Div(css_class="bg-emerald-500 rounded-md h-10 w-full")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-3/4")
            Div(css_class="bg-emerald-500 rounded-md h-10 w-1/2")
        ```

        ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
        {
          "view": {
            "cssClass": "gap-4 items-end p-3 border-3 border-dashed",
            "type": "Column",
            "children": [
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-full", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-3/4", "type": "Div"},
              {"cssClass": "bg-emerald-500 rounded-md h-10 w-1/2", "type": "Div"}
            ]
          }
        }
        ```
      </CodeGroup>
    </ComponentPreview>
  </Tab>
</Tabs>

## API Reference

<Card icon="code" title="Column Parameters">
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

```json Column theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "Column",
  "children?": "[Component]",
  "let?": "object",
  "gap?": "number | Action[]",
  "align?": "start | center | end | stretch | baseline",
  "justify?": "start | center | end | between | around | evenly | stretch",
  "cssClass?": "string"
}
```

For the complete protocol schema, see [Column](/protocol/column).


Built with [Mintlify](https://mintlify.com).