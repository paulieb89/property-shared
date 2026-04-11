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

# Input

> Text input fields for user data entry.

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

Inputs collect text, email, passwords, and other single-line data from users.

## Basic Usage

<ComponentPreview json={{"view":{"name":"input_6","type":"Input","inputType":"text","placeholder":"Enter your email...","disabled":false,"readOnly":false,"required":false}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgSW5wdXQKCklucHV0KHBsYWNlaG9sZGVyPSJFbnRlciB5b3VyIGVtYWlsLi4uIikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Input

    Input(placeholder="Enter your email...")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "name": "input_6",
        "type": "Input",
        "inputType": "text",
        "placeholder": "Enter your email...",
        "disabled": false,
        "readOnly": false,
        "required": false
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Input Types

Different input types provide appropriate keyboards and validation on mobile devices:

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Column","children":[{"name":"input_7","type":"Input","inputType":"email","placeholder":"Email","disabled":false,"readOnly":false,"required":false},{"name":"input_8","type":"Input","inputType":"password","placeholder":"Password","disabled":false,"readOnly":false,"required":false},{"name":"input_9","type":"Input","inputType":"number","placeholder":"Age","disabled":false,"readOnly":false,"required":false},{"name":"input_10","type":"Input","inputType":"tel","placeholder":"Phone","disabled":false,"readOnly":false,"required":false}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgKAogICAgSW5wdXQsCiAgICBDb2x1bW4sCikKCndpdGggQ29sdW1uKGdhcD00KToKICAgIElucHV0KGlucHV0X3R5cGU9ImVtYWlsIiwgcGxhY2Vob2xkZXI9IkVtYWlsIikKICAgIElucHV0KGlucHV0X3R5cGU9InBhc3N3b3JkIiwgcGxhY2Vob2xkZXI9IlBhc3N3b3JkIikKICAgIElucHV0KGlucHV0X3R5cGU9Im51bWJlciIsIHBsYWNlaG9sZGVyPSJBZ2UiKQogICAgSW5wdXQoaW5wdXRfdHlwZT0idGVsIiwgcGxhY2Vob2xkZXI9IlBob25lIikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import (
        Input,
        Column,
    )

    with Column(gap=4):
        Input(input_type="email", placeholder="Email")
        Input(input_type="password", placeholder="Password")
        Input(input_type="number", placeholder="Age")
        Input(input_type="tel", placeholder="Phone")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Column",
        "children": [
          {
            "name": "input_7",
            "type": "Input",
            "inputType": "email",
            "placeholder": "Email",
            "disabled": false,
            "readOnly": false,
            "required": false
          },
          {
            "name": "input_8",
            "type": "Input",
            "inputType": "password",
            "placeholder": "Password",
            "disabled": false,
            "readOnly": false,
            "required": false
          },
          {
            "name": "input_9",
            "type": "Input",
            "inputType": "number",
            "placeholder": "Age",
            "disabled": false,
            "readOnly": false,
            "required": false
          },
          {
            "name": "input_10",
            "type": "Input",
            "inputType": "tel",
            "placeholder": "Phone",
            "disabled": false,
            "readOnly": false,
            "required": false
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## With Labels

Pair inputs with labels for accessible forms:

<ComponentPreview json={{"view":{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Email address","optional":false},{"name":"input_11","type":"Input","inputType":"email","placeholder":"you@example.com","disabled":false,"readOnly":false,"required":true}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgKAogICAgQ29sdW1uLAogICAgSW5wdXQsCiAgICBMYWJlbCwKKQoKd2l0aCBDb2x1bW4oZ2FwPTIpOgogICAgTGFiZWwoIkVtYWlsIGFkZHJlc3MiKQogICAgSW5wdXQoaW5wdXRfdHlwZT0iZW1haWwiLCBwbGFjZWhvbGRlcj0ieW91QGV4YW1wbGUuY29tIiwgcmVxdWlyZWQ9VHJ1ZSkK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import (
        Column,
        Input,
        Label,
    )

    with Column(gap=2):
        Label("Email address")
        Input(input_type="email", placeholder="you@example.com", required=True)
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-2",
        "type": "Column",
        "children": [
          {"type": "Label", "text": "Email address", "optional": false},
          {
            "name": "input_11",
            "type": "Input",
            "inputType": "email",
            "placeholder": "you@example.com",
            "disabled": false,
            "readOnly": false,
            "required": true
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Date & Time Inputs

Native date and time pickers use the browser's built-in UI:

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Row","children":[{"cssClass":"gap-2 flex-1","type":"Column","children":[{"type":"Label","text":"Date","optional":false},{"name":"date","type":"Input","inputType":"date","disabled":false,"readOnly":false,"required":false}]},{"cssClass":"gap-2 flex-1","type":"Column","children":[{"type":"Label","text":"Time","optional":false},{"name":"time","type":"Input","inputType":"time","disabled":false,"readOnly":false,"required":false}]},{"cssClass":"gap-2 flex-1","type":"Column","children":[{"type":"Label","text":"Date & Time","optional":false},{"name":"datetime","type":"Input","inputType":"datetime-local","disabled":false,"readOnly":false,"required":false}]}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgKAogICAgQ29sdW1uLAogICAgSW5wdXQsCiAgICBMYWJlbCwKICAgIFJvdywKKQoKd2l0aCBSb3coZ2FwPTQpOgogICAgd2l0aCBDb2x1bW4oZ2FwPTIsIGNzc19jbGFzcz0iZmxleC0xIik6CiAgICAgICAgTGFiZWwoIkRhdGUiKQogICAgICAgIElucHV0KGlucHV0X3R5cGU9ImRhdGUiLCBuYW1lPSJkYXRlIikKICAgIHdpdGggQ29sdW1uKGdhcD0yLCBjc3NfY2xhc3M9ImZsZXgtMSIpOgogICAgICAgIExhYmVsKCJUaW1lIikKICAgICAgICBJbnB1dChpbnB1dF90eXBlPSJ0aW1lIiwgbmFtZT0idGltZSIpCiAgICB3aXRoIENvbHVtbihnYXA9MiwgY3NzX2NsYXNzPSJmbGV4LTEiKToKICAgICAgICBMYWJlbCgiRGF0ZSAmIFRpbWUiKQogICAgICAgIElucHV0KGlucHV0X3R5cGU9ImRhdGV0aW1lLWxvY2FsIiwgbmFtZT0iZGF0ZXRpbWUiKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import (
        Column,
        Input,
        Label,
        Row,
    )

    with Row(gap=4):
        with Column(gap=2, css_class="flex-1"):
            Label("Date")
            Input(input_type="date", name="date")
        with Column(gap=2, css_class="flex-1"):
            Label("Time")
            Input(input_type="time", name="time")
        with Column(gap=2, css_class="flex-1"):
            Label("Date & Time")
            Input(input_type="datetime-local", name="datetime")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Row",
        "children": [
          {
            "cssClass": "gap-2 flex-1",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Date", "optional": false},
              {
                "name": "date",
                "type": "Input",
                "inputType": "date",
                "disabled": false,
                "readOnly": false,
                "required": false
              }
            ]
          },
          {
            "cssClass": "gap-2 flex-1",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Time", "optional": false},
              {
                "name": "time",
                "type": "Input",
                "inputType": "time",
                "disabled": false,
                "readOnly": false,
                "required": false
              }
            ]
          },
          {
            "cssClass": "gap-2 flex-1",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Date & Time", "optional": false},
              {
                "name": "datetime",
                "type": "Input",
                "inputType": "datetime-local",
                "disabled": false,
                "readOnly": false,
                "required": false
              }
            ]
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Disabled State

<ComponentPreview json={{"view":{"name":"input_12","type":"Input","inputType":"text","placeholder":"Disabled input","disabled":true,"readOnly":false,"required":false}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgSW5wdXQKCklucHV0KHBsYWNlaG9sZGVyPSJEaXNhYmxlZCBpbnB1dCIsIGRpc2FibGVkPVRydWUpCg">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Input

    Input(placeholder="Disabled input", disabled=True)
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "name": "input_12",
        "type": "Input",
        "inputType": "text",
        "placeholder": "Disabled input",
        "disabled": true,
        "readOnly": false,
        "required": false
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Read-Only

A read-only input displays its value and allows users to select and copy the text, but prevents editing. Unlike `disabled`, the input retains its normal visual appearance -- it doesn't grey out or signal that interaction is blocked.

<ComponentPreview json={{"view":{"name":"input_13","value":"api_key_91x8z3...","type":"Input","inputType":"text","disabled":false,"readOnly":true,"required":false},"state":{"input_13":"api_key_91x8z3..."}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgSW5wdXQKCklucHV0KHZhbHVlPSJhcGlfa2V5XzkxeDh6My4uLiIsIHJlYWRfb25seT1UcnVlKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Input

    Input(value="api_key_91x8z3...", read_only=True)
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "name": "input_13",
        "value": "api_key_91x8z3...",
        "type": "Input",
        "inputType": "text",
        "disabled": false,
        "readOnly": true,
        "required": false
      },
      "state": {"input_13": "api_key_91x8z3..."}
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Reading the Value

Use `.rx` to get a reactive reference to the input's current text. As the user types, any component that references `.rx` updates automatically:

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Column","children":[{"name":"input_14","type":"Input","inputType":"text","placeholder":"What is your name, traveler?","disabled":false,"readOnly":false,"required":false},{"content":"Hello, {{ input_14 | default:stranger }}!","type":"Text"}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBJbnB1dCwgVGV4dAoKd2l0aCBDb2x1bW4oZ2FwPTQpOgogICAgaW5wID0gSW5wdXQocGxhY2Vob2xkZXI9IldoYXQgaXMgeW91ciBuYW1lLCB0cmF2ZWxlcj8iKQogICAgVGV4dChmIkhlbGxvLCB7aW5wLnJ4LmRlZmF1bHQoJ3N0cmFuZ2VyJyl9ISIpCg">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Column, Input, Text

    with Column(gap=4):
        inp = Input(placeholder="What is your name, traveler?")
        Text(f"Hello, {inp.rx.default('stranger')}!")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Column",
        "children": [
          {
            "name": "input_14",
            "type": "Input",
            "inputType": "text",
            "placeholder": "What is your name, traveler?",
            "disabled": false,
            "readOnly": false,
            "required": false
          },
          {"content": "Hello, {{ input_14 | default:stranger }}!", "type": "Text"}
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

Type a name and the greeting updates with each keystroke.

## API Reference

<Card icon="code" title="Input Parameters">
  <ParamField body="input_type" type="str" default="text">
    Input type: `"text"`, `"email"`, `"password"`, `"number"`, `"tel"`, `"url"`, `"search"`, `"date"`, `"time"`, `"datetime-local"`, `"file"`.
  </ParamField>

  <ParamField body="placeholder" type="str | None" default="None">
    Placeholder text shown when the input is empty.
  </ParamField>

  <ParamField body="value" type="str | None" default="None">
    Initial value.
  </ParamField>

  <ParamField body="name" type="str | None" default="None">
    State key for the input's current value. Auto-generated if not provided. Set this to bind the input to a known key, or use `.rx` to reference the auto-generated key without knowing it.
  </ParamField>

  <ParamField body="disabled" type="bool" default="False">
    Whether the input is non-interactive.
  </ParamField>

  <ParamField body="read_only" type="bool" default="False">
    Whether the input is read-only. The value is visible and selectable but cannot be edited.
  </ParamField>

  <ParamField body="required" type="bool" default="False">
    Whether the input is required for form submission.
  </ParamField>

  <ParamField body="css_class" type="str | None" default="None">
    Additional Tailwind CSS classes appended to the component's built-in styles.
  </ParamField>
</Card>

## Protocol Reference

```json Input theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "Input",
  "name?": "string",
  "inputType?": "text | email | password | number | tel | url | search | date | time | datetime-local | file",
  "placeholder?": "string",
  "value?": "string",
  "disabled?": false,
  "readOnly?": false,
  "required?": false,
  "minLength?": "number",
  "maxLength?": "number",
  "min?": "number",
  "max?": "number",
  "step?": "number",
  "pattern?": "string",
  "onChange?": "Action | Action[]",
  "cssClass?": "string"
}
```

For the complete protocol schema, see [Input](/protocol/input).


Built with [Mintlify](https://mintlify.com).