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

# Action Chains

> Chain multiple actions from a single click.

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

Each button fires one or more actions in sequence. The counter increments, a toast appears, the progress bar fills, and a save badge replaces a button, all from declarative action lists.

<ComponentPreview json={{"view":{"cssClass":"pf-app-root max-w-none p-0","type":"Div","children":[{"cssClass":"w-full","type":"Card","children":[{"type":"CardHeader","children":[{"type":"CardTitle","content":"Actions Demo"},{"content":"Chain multiple actions from a single click.","type":"Muted"}]},{"type":"CardContent","children":[{"cssClass":"gap-4","type":"Column","children":[{"cssClass":"gap-2 items-center","type":"Row","children":[{"type":"Button","label":"Count + 1","variant":"default","size":"default","disabled":false,"onClick":{"action":"setState","key":"count","value":"{{ count + 1 }}"}},{"type":"Button","label":"Count + 10","variant":"secondary","size":"default","disabled":false,"onClick":[{"action":"setState","key":"count","value":"{{ count + 10 }}"},{"action":"showToast","message":"Jumped ahead by 10!"}]},{"type":"Button","label":"Reset","variant":"outline","size":"default","disabled":false,"onClick":[{"action":"setState","key":"count","value":0},{"action":"setState","key":"saved","value":false}]}]},{"type":"Progress","value":"{{ count }}","max":100.0,"variant":"{{ count >= 100 ? 'success' : 'default' }}","size":"default"},{"cssClass":"gap-2 items-center justify-between","type":"Row","children":[{"content":"Count: {{ count }}","type":"Text"},{"type":"Condition","cases":[{"when":"{{ saved }}","children":[{"type":"Badge","label":"Saved","variant":"success"}]}],"else":[{"type":"Button","label":"Save","variant":"default","size":"sm","disabled":false,"onClick":[{"action":"toggleState","key":"saved"},{"action":"showToast","message":"Saved at {{ count }}!"}]}]}]}]}]}]}]},"state":{"count":0,"saved":false}}} playground="ZnJvbSBwcmVmYWJfdWkgaW1wb3J0IFByZWZhYkFwcApmcm9tIHByZWZhYl91aS5hY3Rpb25zIGltcG9ydCBTZXRTdGF0ZSwgU2hvd1RvYXN0LCBUb2dnbGVTdGF0ZQpmcm9tIHByZWZhYl91aS5jb21wb25lbnRzIGltcG9ydCAoCiAgICBCYWRnZSwgQnV0dG9uLCBDYXJkLCBDYXJkQ29udGVudCwgQ2FyZEhlYWRlciwgQ2FyZFRpdGxlLAogICAgQ29sdW1uLCBNdXRlZCwgUHJvZ3Jlc3MsIFJvdywgVGV4dCwKKQpmcm9tIHByZWZhYl91aS5jb21wb25lbnRzLmNvbnRyb2xfZmxvdyBpbXBvcnQgRWxzZSwgSWYKZnJvbSBwcmVmYWJfdWkucnggaW1wb3J0IFJ4Cgpjb3VudCA9IFJ4KCJjb3VudCIpCnNhdmVkID0gUngoInNhdmVkIikKCndpdGggUHJlZmFiQXBwKHN0YXRlPXsiY291bnQiOiAwLCAic2F2ZWQiOiBGYWxzZX0sIGNzc19jbGFzcz0ibWF4LXctbm9uZSBwLTAiKToKICAgIHdpdGggQ2FyZChjc3NfY2xhc3M9InctZnVsbCIpOgogICAgICAgIHdpdGggQ2FyZEhlYWRlcigpOgogICAgICAgICAgICBDYXJkVGl0bGUoIkFjdGlvbnMgRGVtbyIpCiAgICAgICAgICAgIE11dGVkKCJDaGFpbiBtdWx0aXBsZSBhY3Rpb25zIGZyb20gYSBzaW5nbGUgY2xpY2suIikKICAgICAgICB3aXRoIENhcmRDb250ZW50KCk6CiAgICAgICAgICAgIHdpdGggQ29sdW1uKGdhcD00KToKICAgICAgICAgICAgICAgIHdpdGggUm93KGdhcD0yLCBhbGlnbj0iY2VudGVyIik6CiAgICAgICAgICAgICAgICAgICAgQnV0dG9uKCJDb3VudCArIDEiLCBvbl9jbGljaz1TZXRTdGF0ZSgiY291bnQiLCBjb3VudCArIDEpKQogICAgICAgICAgICAgICAgICAgIEJ1dHRvbigKICAgICAgICAgICAgICAgICAgICAgICAgIkNvdW50ICsgMTAiLCB2YXJpYW50PSJzZWNvbmRhcnkiLAogICAgICAgICAgICAgICAgICAgICAgICBvbl9jbGljaz1bCiAgICAgICAgICAgICAgICAgICAgICAgICAgICBTZXRTdGF0ZSgiY291bnQiLCBjb3VudCArIDEwKSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgIFNob3dUb2FzdCgiSnVtcGVkIGFoZWFkIGJ5IDEwISIpLAogICAgICAgICAgICAgICAgICAgICAgICBdLAogICAgICAgICAgICAgICAgICAgICkKICAgICAgICAgICAgICAgICAgICBCdXR0b24oCiAgICAgICAgICAgICAgICAgICAgICAgICJSZXNldCIsIHZhcmlhbnQ9Im91dGxpbmUiLAogICAgICAgICAgICAgICAgICAgICAgICBvbl9jbGljaz1bU2V0U3RhdGUoImNvdW50IiwgMCksIFNldFN0YXRlKCJzYXZlZCIsIEZhbHNlKV0sCiAgICAgICAgICAgICAgICAgICAgKQogICAgICAgICAgICAgICAgUHJvZ3Jlc3MoCiAgICAgICAgICAgICAgICAgICAgdmFsdWU9Y291bnQsIG1heD0xMDAsCiAgICAgICAgICAgICAgICAgICAgdmFyaWFudD0oY291bnQgPj0gMTAwKS50aGVuKCJzdWNjZXNzIiwgImRlZmF1bHQiKSwKICAgICAgICAgICAgICAgICkKICAgICAgICAgICAgICAgIHdpdGggUm93KGdhcD0yLCBhbGlnbj0iY2VudGVyIiwgY3NzX2NsYXNzPSJqdXN0aWZ5LWJldHdlZW4iKToKICAgICAgICAgICAgICAgICAgICBUZXh0KGYiQ291bnQ6IHtjb3VudH0iKQogICAgICAgICAgICAgICAgICAgIHdpdGggSWYoc2F2ZWQpOgogICAgICAgICAgICAgICAgICAgICAgICBCYWRnZSgiU2F2ZWQiLCB2YXJpYW50PSJzdWNjZXNzIikKICAgICAgICAgICAgICAgICAgICB3aXRoIEVsc2UoKToKICAgICAgICAgICAgICAgICAgICAgICAgQnV0dG9uKAogICAgICAgICAgICAgICAgICAgICAgICAgICAgIlNhdmUiLCBzaXplPSJzbSIsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICBvbl9jbGljaz1bCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgVG9nZ2xlU3RhdGUoInNhdmVkIiksCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgU2hvd1RvYXN0KGYiU2F2ZWQgYXQge2NvdW50fSEiKSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgIF0sCiAgICAgICAgICAgICAgICAgICAgICAgICkK">
  <CodeGroup>
    ```python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui import PrefabApp
    from prefab_ui.actions import SetState, ShowToast, ToggleState
    from prefab_ui.components import (
        Badge, Button, Card, CardContent, CardHeader, CardTitle,
        Column, Muted, Progress, Row, Text,
    )
    from prefab_ui.components.control_flow import Else, If
    from prefab_ui.rx import Rx

    count = Rx("count")
    saved = Rx("saved")

    with PrefabApp(state={"count": 0, "saved": False}, css_class="max-w-none p-0"):
        with Card(css_class="w-full"):
            with CardHeader():
                CardTitle("Actions Demo")
                Muted("Chain multiple actions from a single click.")
            with CardContent():
                with Column(gap=4):
                    with Row(gap=2, align="center"):
                        Button("Count + 1", on_click=SetState("count", count + 1))
                        Button(
                            "Count + 10", variant="secondary",
                            on_click=[
                                SetState("count", count + 10),
                                ShowToast("Jumped ahead by 10!"),
                            ],
                        )
                        Button(
                            "Reset", variant="outline",
                            on_click=[SetState("count", 0), SetState("saved", False)],
                        )
                    Progress(
                        value=count, max=100,
                        variant=(count >= 100).then("success", "default"),
                    )
                    with Row(gap=2, align="center", css_class="justify-between"):
                        Text(f"Count: {count}")
                        with If(saved):
                            Badge("Saved", variant="success")
                        with Else():
                            Button(
                                "Save", size="sm",
                                on_click=[
                                    ToggleState("saved"),
                                    ShowToast(f"Saved at {count}!"),
                                ],
                            )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "pf-app-root max-w-none p-0",
        "type": "Div",
        "children": [
          {
            "cssClass": "w-full",
            "type": "Card",
            "children": [
              {
                "type": "CardHeader",
                "children": [
                  {"type": "CardTitle", "content": "Actions Demo"},
                  {"content": "Chain multiple actions from a single click.", "type": "Muted"}
                ]
              },
              {
                "type": "CardContent",
                "children": [
                  {
                    "cssClass": "gap-4",
                    "type": "Column",
                    "children": [
                      {
                        "cssClass": "gap-2 items-center",
                        "type": "Row",
                        "children": [
                          {
                            "type": "Button",
                            "label": "Count + 1",
                            "variant": "default",
                            "size": "default",
                            "disabled": false,
                            "onClick": {"action": "setState", "key": "count", "value": "{{ count + 1 }}"}
                          },
                          {
                            "type": "Button",
                            "label": "Count + 10",
                            "variant": "secondary",
                            "size": "default",
                            "disabled": false,
                            "onClick": [
                              {"action": "setState", "key": "count", "value": "{{ count + 10 }}"},
                              {"action": "showToast", "message": "Jumped ahead by 10!"}
                            ]
                          },
                          {
                            "type": "Button",
                            "label": "Reset",
                            "variant": "outline",
                            "size": "default",
                            "disabled": false,
                            "onClick": [
                              {"action": "setState", "key": "count", "value": 0},
                              {"action": "setState", "key": "saved", "value": false}
                            ]
                          }
                        ]
                      },
                      {
                        "type": "Progress",
                        "value": "{{ count }}",
                        "max": 100.0,
                        "variant": "{{ count >= 100 ? 'success' : 'default' }}",
                        "size": "default"
                      },
                      {
                        "cssClass": "gap-2 items-center justify-between",
                        "type": "Row",
                        "children": [
                          {"content": "Count: {{ count }}", "type": "Text"},
                          {
                            "type": "Condition",
                            "cases": [
                              {
                                "when": "{{ saved }}",
                                "children": [{"type": "Badge", "label": "Saved", "variant": "success"}]
                              }
                            ],
                            "else": [
                              {
                                "type": "Button",
                                "label": "Save",
                                "variant": "default",
                                "size": "sm",
                                "disabled": false,
                                "onClick": [
                                  {"action": "toggleState", "key": "saved"},
                                  {"action": "showToast", "message": "Saved at {{ count }}!"}
                                ]
                              }
                            ]
                          }
                        ]
                      }
                    ]
                  }
                ]
              }
            ]
          }
        ]
      },
      "state": {"count": 0, "saved": false}
    }
    ```
  </CodeGroup>
</ComponentPreview>


Built with [Mintlify](https://mintlify.com).