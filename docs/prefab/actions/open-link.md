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

# Open Link

> Open a URL from a UI interaction.

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

`OpenLink` opens a URL through the host application's link handler. Use it for navigation buttons, "View docs" links, or any action that should take the user to an external resource.

<ComponentPreview json={{"view":{"type":"Button","label":"View Documentation","variant":"link","size":"default","disabled":false,"onClick":{"action":"openLink","url":"https://prefab-ui.dev"}}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQnV0dG9uCmZyb20gcHJlZmFiX3VpLmFjdGlvbnMgaW1wb3J0IE9wZW5MaW5rCgpCdXR0b24oIlZpZXcgRG9jdW1lbnRhdGlvbiIsIHZhcmlhbnQ9ImxpbmsiLAogICAgICAgb25fY2xpY2s9T3BlbkxpbmsoImh0dHBzOi8vcHJlZmFiLXVpLmRldiIpKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Button
    from prefab_ui.actions import OpenLink

    Button("View Documentation", variant="link",
           on_click=OpenLink("https://prefab-ui.dev"))
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "Button",
        "label": "View Documentation",
        "variant": "link",
        "size": "default",
        "disabled": false,
        "onClick": {"action": "openLink", "url": "https://prefab-ui.dev"}
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Link Buttons

Pair `OpenLink` with the `link` button variant for a natural look:

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Row","children":[{"type":"Button","label":"GitHub","variant":"link","size":"default","disabled":false,"onClick":{"action":"openLink","url":"https://github.com/prefecthq/prefab"}},{"type":"Button","label":"PyPI","variant":"link","size":"default","disabled":false,"onClick":{"action":"openLink","url":"https://pypi.org/project/prefab-ui"}}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQnV0dG9uLCBSb3cKZnJvbSBwcmVmYWJfdWkuYWN0aW9ucyBpbXBvcnQgT3BlbkxpbmsKCndpdGggUm93KGdhcD00KToKICAgIEJ1dHRvbigiR2l0SHViIiwgdmFyaWFudD0ibGluayIsCiAgICAgICAgICAgb25fY2xpY2s9T3BlbkxpbmsoImh0dHBzOi8vZ2l0aHViLmNvbS9wcmVmZWN0aHEvcHJlZmFiIikpCiAgICBCdXR0b24oIlB5UEkiLCB2YXJpYW50PSJsaW5rIiwKICAgICAgICAgICBvbl9jbGljaz1PcGVuTGluaygiaHR0cHM6Ly9weXBpLm9yZy9wcm9qZWN0L3ByZWZhYi11aSIpKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Button, Row
    from prefab_ui.actions import OpenLink

    with Row(gap=4):
        Button("GitHub", variant="link",
               on_click=OpenLink("https://github.com/prefecthq/prefab"))
        Button("PyPI", variant="link",
               on_click=OpenLink("https://pypi.org/project/prefab-ui"))
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Row",
        "children": [
          {
            "type": "Button",
            "label": "GitHub",
            "variant": "link",
            "size": "default",
            "disabled": false,
            "onClick": {"action": "openLink", "url": "https://github.com/prefecthq/prefab"}
          },
          {
            "type": "Button",
            "label": "PyPI",
            "variant": "link",
            "size": "default",
            "disabled": false,
            "onClick": {"action": "openLink", "url": "https://pypi.org/project/prefab-ui"}
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Dynamic URLs with State

Build URLs from client state using interpolation:

<ComponentPreview json={{"view":{"cssClass":"gap-3","type":"Column","children":[{"name":"repo","type":"Input","inputType":"text","placeholder":"owner/repo","disabled":false,"readOnly":false,"required":false},{"type":"Button","label":"Open on GitHub","variant":"default","size":"default","disabled":false,"onClick":{"action":"openLink","url":"https://github.com/{{ repo }}"}}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgSW5wdXQsIEJ1dHRvbiwgQ29sdW1uCmZyb20gcHJlZmFiX3VpLmFjdGlvbnMgaW1wb3J0IE9wZW5MaW5rCgp3aXRoIENvbHVtbihnYXA9Myk6CiAgICByZXBvID0gSW5wdXQobmFtZT0icmVwbyIsIHBsYWNlaG9sZGVyPSJvd25lci9yZXBvIikKICAgIEJ1dHRvbigKICAgICAgICAiT3BlbiBvbiBHaXRIdWIiLAogICAgICAgIG9uX2NsaWNrPU9wZW5MaW5rKGYiaHR0cHM6Ly9naXRodWIuY29tL3tyZXBvLnJ4fSIpLAogICAgKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Input, Button, Column
    from prefab_ui.actions import OpenLink

    with Column(gap=3):
        repo = Input(name="repo", placeholder="owner/repo")
        Button(
            "Open on GitHub",
            on_click=OpenLink(f"https://github.com/{repo.rx}"),
        )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-3",
        "type": "Column",
        "children": [
          {
            "name": "repo",
            "type": "Input",
            "inputType": "text",
            "placeholder": "owner/repo",
            "disabled": false,
            "readOnly": false,
            "required": false
          },
          {
            "type": "Button",
            "label": "Open on GitHub",
            "variant": "default",
            "size": "default",
            "disabled": false,
            "onClick": {"action": "openLink", "url": "https://github.com/{{ repo }}"}
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## API Reference

<Card icon="code" title="OpenLink Parameters">
  <ParamField body="url" type="str" required>
    URL to open. Can be passed as a positional argument. Supports `{{ key }}` interpolation.
  </ParamField>
</Card>

## Protocol Reference

```json OpenLink theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "action": "openLink",
  "url": "string (required)"
}
```

For the complete protocol schema, see [OpenLink](/protocol/open-link).


Built with [Mintlify](https://mintlify.com).