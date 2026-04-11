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

# Typography

> Text components for headings, body copy, and inline formatting.

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

Every text component accepts a content string as a positional argument and supports `{{ field }}` interpolation. Styles adapt automatically to dark mode.

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Column","children":[{"content":"Dashboard","type":"H1"},{"content":"Monitor your application metrics and performance.","type":"Lead"},{"content":"Everything you need to manage your MCP server, organized in one place.","type":"P"},{"content":"Last updated 5 minutes ago","type":"Muted"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgSDEsIExlYWQsIFAsIE11dGVkLCBDb2x1bW4KCndpdGggQ29sdW1uKGdhcD00KToKICAgIEgxKCJEYXNoYm9hcmQiKQogICAgTGVhZCgiTW9uaXRvciB5b3VyIGFwcGxpY2F0aW9uIG1ldHJpY3MgYW5kIHBlcmZvcm1hbmNlLiIpCiAgICBQKCJFdmVyeXRoaW5nIHlvdSBuZWVkIHRvIG1hbmFnZSB5b3VyIE1DUCBzZXJ2ZXIsIG9yZ2FuaXplZCBpbiBvbmUgcGxhY2UuIikKICAgIE11dGVkKCJMYXN0IHVwZGF0ZWQgNSBtaW51dGVzIGFnbyIpCg">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import H1, Lead, P, Muted, Column

    with Column(gap=4):
        H1("Dashboard")
        Lead("Monitor your application metrics and performance.")
        P("Everything you need to manage your MCP server, organized in one place.")
        Muted("Last updated 5 minutes ago")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Column",
        "children": [
          {"content": "Dashboard", "type": "H1"},
          {"content": "Monitor your application metrics and performance.", "type": "Lead"},
          {
            "content": "Everything you need to manage your MCP server, organized in one place.",
            "type": "P"
          },
          {"content": "Last updated 5 minutes ago", "type": "Muted"}
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Text Components

Prefab has a text component for every level of the visual hierarchy. They all share the same API: positional content, formatting kwargs (bold, italic, underline, etc.), and `css_class` for anything else.

| Component              | Purpose                                              |
| ---------------------- | ---------------------------------------------------- |
| `H1`, `H2`, `H3`, `H4` | Headings with decreasing size and weight             |
| `Heading(level=n)`     | Dynamic heading level from a variable                |
| `P`                    | Standard paragraph text                              |
| `Lead`                 | Larger, muted text for introductions                 |
| `Large`                | Emphasized text with bolder weight                   |
| `Small`                | Smaller text for metadata and fine print             |
| `Muted`                | Secondary-color text for less prominent information  |
| `Text`                 | Unstyled span, the most flexible building block      |
| `BlockQuote`           | Indented border for quotations                       |
| `Markdown`             | Renders markdown syntax (bold, links, lists, images) |

<ComponentPreview json={{"view":{"cssClass":"gap-3","type":"Column","children":[{"content":"Page Title","type":"H1"},{"content":"Section Heading","type":"H2"},{"content":"Subsection","type":"H3"},{"content":"Introductory text that sets context for what follows.","type":"Lead"},{"content":"Standard paragraph text for the main content of your UI.","type":"P"},{"content":"Key Takeaway: Components compose naturally.","type":"Large"},{"content":"Terms and conditions apply","type":"Small"},{"content":"Last updated 5 minutes ago","type":"Muted"},{"content":"The best way to predict the future is to invent it.","type":"BlockQuote"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgSDEsIEgyLCBIMywgUCwgTGVhZCwgTGFyZ2UsIFNtYWxsLCBNdXRlZCwgQmxvY2tRdW90ZSwgQ29sdW1uCgp3aXRoIENvbHVtbihnYXA9Myk6CiAgICBIMSgiUGFnZSBUaXRsZSIpCiAgICBIMigiU2VjdGlvbiBIZWFkaW5nIikKICAgIEgzKCJTdWJzZWN0aW9uIikKICAgIExlYWQoIkludHJvZHVjdG9yeSB0ZXh0IHRoYXQgc2V0cyBjb250ZXh0IGZvciB3aGF0IGZvbGxvd3MuIikKICAgIFAoIlN0YW5kYXJkIHBhcmFncmFwaCB0ZXh0IGZvciB0aGUgbWFpbiBjb250ZW50IG9mIHlvdXIgVUkuIikKICAgIExhcmdlKCJLZXkgVGFrZWF3YXk6IENvbXBvbmVudHMgY29tcG9zZSBuYXR1cmFsbHkuIikKICAgIFNtYWxsKCJUZXJtcyBhbmQgY29uZGl0aW9ucyBhcHBseSIpCiAgICBNdXRlZCgiTGFzdCB1cGRhdGVkIDUgbWludXRlcyBhZ28iKQogICAgQmxvY2tRdW90ZSgiVGhlIGJlc3Qgd2F5IHRvIHByZWRpY3QgdGhlIGZ1dHVyZSBpcyB0byBpbnZlbnQgaXQuIikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import H1, H2, H3, P, Lead, Large, Small, Muted, BlockQuote, Column

    with Column(gap=3):
        H1("Page Title")
        H2("Section Heading")
        H3("Subsection")
        Lead("Introductory text that sets context for what follows.")
        P("Standard paragraph text for the main content of your UI.")
        Large("Key Takeaway: Components compose naturally.")
        Small("Terms and conditions apply")
        Muted("Last updated 5 minutes ago")
        BlockQuote("The best way to predict the future is to invent it.")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-3",
        "type": "Column",
        "children": [
          {"content": "Page Title", "type": "H1"},
          {"content": "Section Heading", "type": "H2"},
          {"content": "Subsection", "type": "H3"},
          {
            "content": "Introductory text that sets context for what follows.",
            "type": "Lead"
          },
          {
            "content": "Standard paragraph text for the main content of your UI.",
            "type": "P"
          },
          {"content": "Key Takeaway: Components compose naturally.", "type": "Large"},
          {"content": "Terms and conditions apply", "type": "Small"},
          {"content": "Last updated 5 minutes ago", "type": "Muted"},
          {
            "content": "The best way to predict the future is to invent it.",
            "type": "BlockQuote"
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Inline Formatting

### Modifiers

All text components accept formatting kwargs that compile to Tailwind classes: `bold`, `italic`, `underline`, `strikethrough`, `uppercase`, `lowercase`, and `align`.

<ComponentPreview json={{"view":{"cssClass":"gap-2","type":"Column","children":[{"cssClass":"font-bold","content":"Bold text","type":"Text"},{"cssClass":"italic","content":"Italic text","type":"Text"},{"cssClass":"underline","content":"Underlined","type":"Text"},{"cssClass":"line-through","content":"Strikethrough","type":"Text"},{"cssClass":"uppercase","content":"UPPERCASE","type":"Text"},{"cssClass":"text-center","content":"Centered","type":"Text"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgVGV4dCwgQ29sdW1uCgp3aXRoIENvbHVtbihnYXA9Mik6CiAgICBUZXh0KCJCb2xkIHRleHQiLCBib2xkPVRydWUpCiAgICBUZXh0KCJJdGFsaWMgdGV4dCIsIGl0YWxpYz1UcnVlKQogICAgVGV4dCgiVW5kZXJsaW5lZCIsIHVuZGVybGluZT1UcnVlKQogICAgVGV4dCgiU3RyaWtldGhyb3VnaCIsIHN0cmlrZXRocm91Z2g9VHJ1ZSkKICAgIFRleHQoIlVQUEVSQ0FTRSIsIHVwcGVyY2FzZT1UcnVlKQogICAgVGV4dCgiQ2VudGVyZWQiLCBhbGlnbj0iY2VudGVyIikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Text, Column

    with Column(gap=2):
        Text("Bold text", bold=True)
        Text("Italic text", italic=True)
        Text("Underlined", underline=True)
        Text("Strikethrough", strikethrough=True)
        Text("UPPERCASE", uppercase=True)
        Text("Centered", align="center")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-2",
        "type": "Column",
        "children": [
          {"cssClass": "font-bold", "content": "Bold text", "type": "Text"},
          {"cssClass": "italic", "content": "Italic text", "type": "Text"},
          {"cssClass": "underline", "content": "Underlined", "type": "Text"},
          {"cssClass": "line-through", "content": "Strikethrough", "type": "Text"},
          {"cssClass": "uppercase", "content": "UPPERCASE", "type": "Text"},
          {"cssClass": "text-center", "content": "Centered", "type": "Text"}
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

### Span and Link

`Span` is the inline formatting primitive. It carries all the same modifiers as Text, plus `code` for monospace styling and `style` for inline CSS. `Link` works the same way but renders as an anchor tag with `href`.

Pass mixed strings, Spans, and Links to `Text` as positional arguments. Strings auto-wrap as plain spans:

<ComponentPreview json={{"view":{"cssClass":"gap-2","type":"Column","children":[{"type":"Text","children":[{"content":"Click ","code":false,"type":"Span"},{"cssClass":"font-bold underline","content":"here","code":false,"type":"Span"},{"content":" to continue","code":false,"type":"Span"}]},{"type":"Text","children":[{"content":"Price: ","code":false,"type":"Span"},{"cssClass":"line-through","content":"$9.99","code":false,"type":"Span"},{"content":" ","code":false,"type":"Span"},{"cssClass":"font-bold","content":"$4.99","code":false,"type":"Span"}]},{"type":"Text","children":[{"content":"Run ","code":false,"type":"Span"},{"cssClass":"font-mono","content":"pip install prefab-ui","code":true,"type":"Span"},{"content":" to get started","code":false,"type":"Span"}]},{"type":"Text","children":[{"content":"Read the ","code":false,"type":"Span"},{"content":"documentation","code":false,"type":"Link","href":"https://prefab.prefect.io","target":"_blank"},{"content":" for more","code":false,"type":"Span"}]}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgVGV4dCwgU3BhbiwgTGluaywgQ29sdW1uCgp3aXRoIENvbHVtbihnYXA9Mik6CiAgICBUZXh0KCJDbGljayAiLCBTcGFuKCJoZXJlIiwgYm9sZD1UcnVlLCB1bmRlcmxpbmU9VHJ1ZSksICIgdG8gY29udGludWUiKQogICAgVGV4dCgiUHJpY2U6ICIsIFNwYW4oIiQ5Ljk5Iiwgc3RyaWtldGhyb3VnaD1UcnVlKSwgIiAiLCBTcGFuKCIkNC45OSIsIGJvbGQ9VHJ1ZSkpCiAgICBUZXh0KCJSdW4gIiwgU3BhbigicGlwIGluc3RhbGwgcHJlZmFiLXVpIiwgY29kZT1UcnVlKSwgIiB0byBnZXQgc3RhcnRlZCIpCiAgICBUZXh0KCJSZWFkIHRoZSAiLCBMaW5rKCJkb2N1bWVudGF0aW9uIiwgaHJlZj0iaHR0cHM6Ly9wcmVmYWIucHJlZmVjdC5pbyIpLCAiIGZvciBtb3JlIikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Text, Span, Link, Column

    with Column(gap=2):
        Text("Click ", Span("here", bold=True, underline=True), " to continue")
        Text("Price: ", Span("$9.99", strikethrough=True), " ", Span("$4.99", bold=True))
        Text("Run ", Span("pip install prefab-ui", code=True), " to get started")
        Text("Read the ", Link("documentation", href="https://prefab.prefect.io"), " for more")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-2",
        "type": "Column",
        "children": [
          {
            "type": "Text",
            "children": [
              {"content": "Click ", "code": false, "type": "Span"},
              {
                "cssClass": "font-bold underline",
                "content": "here",
                "code": false,
                "type": "Span"
              },
              {"content": " to continue", "code": false, "type": "Span"}
            ]
          },
          {
            "type": "Text",
            "children": [
              {"content": "Price: ", "code": false, "type": "Span"},
              {"cssClass": "line-through", "content": "$9.99", "code": false, "type": "Span"},
              {"content": " ", "code": false, "type": "Span"},
              {"cssClass": "font-bold", "content": "$4.99", "code": false, "type": "Span"}
            ]
          },
          {
            "type": "Text",
            "children": [
              {"content": "Run ", "code": false, "type": "Span"},
              {
                "cssClass": "font-mono",
                "content": "pip install prefab-ui",
                "code": true,
                "type": "Span"
              },
              {"content": " to get started", "code": false, "type": "Span"}
            ]
          },
          {
            "type": "Text",
            "children": [
              {"content": "Read the ", "code": false, "type": "Span"},
              {
                "content": "documentation",
                "code": false,
                "type": "Link",
                "href": "https://prefab.prefect.io",
                "target": "_blank"
              },
              {"content": " for more", "code": false, "type": "Span"}
            ]
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## API Reference

<Card icon="code" title="Common Parameters">
  All text components share this interface:

  <ParamField body="content" type="str" required>
    Text content. Accepts `{{ field }}` interpolation. Can be passed as a positional argument.
  </ParamField>

  <ParamField body="bold" type="bool | None" default="None">
    Bold weight.
  </ParamField>

  <ParamField body="italic" type="bool | None" default="None">
    Italic style.
  </ParamField>

  <ParamField body="underline" type="bool | None" default="None">
    Underline decoration.
  </ParamField>

  <ParamField body="strikethrough" type="bool | None" default="None">
    Strikethrough decoration.
  </ParamField>

  <ParamField body="uppercase" type="bool | None" default="None">
    Transform text to uppercase.
  </ParamField>

  <ParamField body="lowercase" type="bool | None" default="None">
    Transform text to lowercase.
  </ParamField>

  <ParamField body="align" type="&#x22;left&#x22; | &#x22;center&#x22; | &#x22;right&#x22; | &#x22;justify&#x22; | None" default="None">
    Horizontal text alignment.
  </ParamField>

  <ParamField body="css_class" type="str | None" default="None">
    Additional Tailwind CSS classes.
  </ParamField>
</Card>

<Card icon="code" title="Text">
  Accepts mixed positional args for inline formatting:

  ```python  theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
  Text("plain string")
  Text("Click ", Span("here", bold=True), " to continue")
  ```
</Card>

<Card icon="code" title="Heading">
  <ParamField body="level" type="int" default="1">
    Heading level: `1` (h1), `2` (h2), `3` (h3), or `4` (h4).
  </ParamField>
</Card>

<Card icon="code" title="Span">
  <ParamField body="code" type="bool" default="False">
    Render as inline code with monospace font and background.
  </ParamField>

  <ParamField body="style" type="dict[str, str] | None" default="None">
    Inline CSS styles as a dict of property/value pairs.
  </ParamField>
</Card>

<Card icon="code" title="Link">
  <ParamField body="href" type="str" required>
    URL to navigate to.
  </ParamField>

  <ParamField body="target" type="str | None" default="'_blank'">
    Link target: `_blank` (new tab) or `_self` (same tab).
  </ParamField>

  <ParamField body="code" type="bool" default="False">
    Render as inline code link.
  </ParamField>

  <ParamField body="style" type="dict[str, str] | None" default="None">
    Inline CSS styles.
  </ParamField>
</Card>

## Protocol Reference

```json Text theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "Text",
  "content?": "string",
  "children?": [{"type": "Span", "content": "...", "code?": true}],
  "bold?": "boolean",
  "italic?": "boolean",
  "align?": "left | center | right | justify",
  "cssClass?": "string"
}
```

```json Heading theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "Heading",
  "content": "string (required)",
  "level?": "1 | 2 | 3 | 4",
  "bold?": "boolean",
  "italic?": "boolean",
  "cssClass?": "string"
}
```

For the complete protocol schema, see [Text](/protocol/text), [Heading](/protocol/heading), [Span](/protocol/span), [Markdown](/protocol/markdown).


Built with [Mintlify](https://mintlify.com).