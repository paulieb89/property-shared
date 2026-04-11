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

# Slider

> Range input for selecting numeric values.

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

Sliders let users select a numeric value from a range by dragging a handle. The default range is 0–100.

## Basic Usage

<ComponentPreview json={{"view":{"name":"slider_2","value":50.0,"type":"Slider","min":0,"max":100,"disabled":false,"size":"default"},"state":{"slider_2":50.0}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgU2xpZGVyCgpTbGlkZXIodmFsdWU9NTApCg">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Slider

    Slider(value=50)
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "name": "slider_2",
        "value": 50.0,
        "type": "Slider",
        "min": 0,
        "max": 100,
        "disabled": false,
        "size": "default"
      },
      "state": {"slider_2": 50.0}
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Displaying the Value

Every form control has an `.rx` property — a reactive reference to its current value. For a slider, `.rx` is a number you can format with pipes like `.percent()` or use in expressions:

<ComponentPreview json={{"view":{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Volume","optional":false},{"name":"slider_3","value":0.75,"type":"Slider","min":0.0,"max":1.0,"disabled":false,"size":"default"},{"cssClass":"font-bold","content":"{{ slider_3 | percent }}","type":"Text"}]},"state":{"slider_3":0.75}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBMYWJlbCwgU2xpZGVyLCBUZXh0Cgp3aXRoIENvbHVtbihnYXA9Mik6CiAgICBMYWJlbCgiVm9sdW1lIikKICAgIHZvbHVtZSA9IFNsaWRlcih2YWx1ZT0wLjc1LCBtaW49MCwgbWF4PTEpCiAgICBUZXh0KHZvbHVtZS5yeC5wZXJjZW50KCksIGJvbGQ9VHJ1ZSkK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Column, Label, Slider, Text

    with Column(gap=2):
        Label("Volume")
        volume = Slider(value=0.75, min=0, max=1)
        Text(volume.rx.percent(), bold=True)
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-2",
        "type": "Column",
        "children": [
          {"type": "Label", "text": "Volume", "optional": false},
          {
            "name": "slider_3",
            "value": 0.75,
            "type": "Slider",
            "min": 0.0,
            "max": 1.0,
            "disabled": false,
            "size": "default"
          },
          {"cssClass": "font-bold", "content": "{{ slider_3 | percent }}", "type": "Text"}
        ]
      },
      "state": {"slider_3": 0.75}
    }
    ```
  </CodeGroup>
</ComponentPreview>

When the display needs to appear *above* the slider in the layout, forward-declare the reference with `Rx(lambda: ...)` so it resolves at render time:

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Column","children":[{"cssClass":"justify-between","type":"Row","children":[{"type":"Label","text":"Brightness","optional":false},{"cssClass":"font-bold","content":"{{ slider_4 | percent }}","type":"Text"}]},{"type":"Progress","value":"{{ slider_4 }}","min":0.0,"max":1.0,"variant":"default","size":"default"},{"name":"slider_4","value":0.42,"type":"Slider","min":0.0,"max":1.0,"disabled":false,"size":"default"}]},"state":{"slider_4":0.42}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBMYWJlbCwgUHJvZ3Jlc3MsIFJvdywgU2xpZGVyLCBUZXh0CmZyb20gcHJlZmFiX3VpLnJ4IGltcG9ydCBSeAoKdmFsID0gUngobGFtYmRhOiBzKQoKd2l0aCBDb2x1bW4oZ2FwPTQpOgogICAgd2l0aCBSb3coY3NzX2NsYXNzPSJqdXN0aWZ5LWJldHdlZW4iKToKICAgICAgICBMYWJlbCgiQnJpZ2h0bmVzcyIpCiAgICAgICAgVGV4dCh2YWwucGVyY2VudCgpLCBib2xkPVRydWUpCiAgICBQcm9ncmVzcyh2YWx1ZT12YWwsIG1pbj0wLCBtYXg9MSkKICAgIHMgPSBTbGlkZXIodmFsdWU9MC40MiwgbWluPTAsIG1heD0xKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Column, Label, Progress, Row, Slider, Text
    from prefab_ui.rx import Rx

    val = Rx(lambda: s)

    with Column(gap=4):
        with Row(css_class="justify-between"):
            Label("Brightness")
            Text(val.percent(), bold=True)
        Progress(value=val, min=0, max=1)
        s = Slider(value=0.42, min=0, max=1)
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Column",
        "children": [
          {
            "cssClass": "justify-between",
            "type": "Row",
            "children": [
              {"type": "Label", "text": "Brightness", "optional": false},
              {"cssClass": "font-bold", "content": "{{ slider_4 | percent }}", "type": "Text"}
            ]
          },
          {
            "type": "Progress",
            "value": "{{ slider_4 }}",
            "min": 0.0,
            "max": 1.0,
            "variant": "default",
            "size": "default"
          },
          {
            "name": "slider_4",
            "value": 0.42,
            "type": "Slider",
            "min": 0.0,
            "max": 1.0,
            "disabled": false,
            "size": "default"
          }
        ]
      },
      "state": {"slider_4": 0.42}
    }
    ```
  </CodeGroup>
</ComponentPreview>

See [Forward References](/concepts/components#forward-references) for more on this pattern.

## Range and Step

Use `min`, `max`, and `step` to constrain the slider. Here the range is 0–5 with half-step increments:

<ComponentPreview json={{"view":{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Rating","optional":false},{"name":"rating","value":4.0,"type":"Slider","min":0.0,"max":5.0,"step":0.5,"disabled":false,"size":"default"},{"cssClass":"font-bold","content":"{{ rating }}","type":"Text"}]},"state":{"rating":4.0}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBMYWJlbCwgU2xpZGVyLCBUZXh0Cgp3aXRoIENvbHVtbihnYXA9Mik6CiAgICBMYWJlbCgiUmF0aW5nIikKICAgIHJhdGluZyA9IFNsaWRlcih2YWx1ZT00LCBuYW1lPSJyYXRpbmciLCBtaW49MCwgbWF4PTUsIHN0ZXA9MC41KQogICAgVGV4dChyYXRpbmcucngsIGJvbGQ9VHJ1ZSkK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Column, Label, Slider, Text

    with Column(gap=2):
        Label("Rating")
        rating = Slider(value=4, name="rating", min=0, max=5, step=0.5)
        Text(rating.rx, bold=True)
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-2",
        "type": "Column",
        "children": [
          {"type": "Label", "text": "Rating", "optional": false},
          {
            "name": "rating",
            "value": 4.0,
            "type": "Slider",
            "min": 0.0,
            "max": 5.0,
            "step": 0.5,
            "disabled": false,
            "size": "default"
          },
          {"cssClass": "font-bold", "content": "{{ rating }}", "type": "Text"}
        ]
      },
      "state": {"rating": 4.0}
    }
    ```
  </CodeGroup>
</ComponentPreview>

## With Actions

The `on_change` parameter runs actions when the slider value changes. `$event` is the current numeric value:

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Column","children":[{"name":"slider_5","value":50.0,"type":"Slider","min":0,"max":100,"disabled":false,"size":"default","onChange":{"action":"setState","key":"level","value":"{{ $event }}"}},{"cssClass":"text-muted-foreground","content":"{{ level | default:'Drag the slider' }}","type":"Text"}]},"state":{"slider_5":50.0}}} playground="ZnJvbSBwcmVmYWJfdWkuYWN0aW9ucyBpbXBvcnQgU2V0U3RhdGUKZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBTbGlkZXIsIFRleHQKZnJvbSBwcmVmYWJfdWkucnggaW1wb3J0IEVWRU5ULCBSeAoKbGV2ZWwgPSBSeCgibGV2ZWwiKQoKd2l0aCBDb2x1bW4oZ2FwPTQpOgogICAgU2xpZGVyKAogICAgICAgIHZhbHVlPTUwLAogICAgICAgIG9uX2NoYW5nZT1TZXRTdGF0ZSgibGV2ZWwiLCBFVkVOVCksCiAgICApCiAgICBUZXh0KAogICAgICAgIGxldmVsLmRlZmF1bHQoIkRyYWcgdGhlIHNsaWRlciIpLAogICAgICAgIGNzc19jbGFzcz0idGV4dC1tdXRlZC1mb3JlZ3JvdW5kIiwKICAgICkK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.actions import SetState
    from prefab_ui.components import Column, Slider, Text
    from prefab_ui.rx import EVENT, Rx

    level = Rx("level")

    with Column(gap=4):
        Slider(
            value=50,
            on_change=SetState("level", EVENT),
        )
        Text(
            level.default("Drag the slider"),
            css_class="text-muted-foreground",
        )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Column",
        "children": [
          {
            "name": "slider_5",
            "value": 50.0,
            "type": "Slider",
            "min": 0,
            "max": 100,
            "disabled": false,
            "size": "default",
            "onChange": {"action": "setState", "key": "level", "value": "{{ $event }}"}
          },
          {
            "cssClass": "text-muted-foreground",
            "content": "{{ level | default:'Drag the slider' }}",
            "type": "Text"
          }
        ]
      },
      "state": {"slider_5": 50.0}
    }
    ```
  </CodeGroup>
</ComponentPreview>

<Tip>
  For simply displaying the slider's current value, [`.rx` binding](#displaying-the-value) is usually easier. Use `on_change` when you need to run custom logic like triggering a tool call or updating multiple state keys.
</Tip>

## Disabled State

<ComponentPreview json={{"view":{"name":"slider_6","value":30.0,"type":"Slider","min":0,"max":100,"disabled":true,"size":"default"},"state":{"slider_6":30.0}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgU2xpZGVyCgpTbGlkZXIodmFsdWU9MzAsIGRpc2FibGVkPVRydWUpCg">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Slider

    Slider(value=30, disabled=True)
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "name": "slider_6",
        "value": 30.0,
        "type": "Slider",
        "min": 0,
        "max": 100,
        "disabled": true,
        "size": "default"
      },
      "state": {"slider_6": 30.0}
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Variants

Semantic variants color the filled track to communicate meaning at a glance — the same palette available on Progress:

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Column","children":[{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Default","optional":false},{"name":"slider_7","value":60.0,"type":"Slider","min":0,"max":100,"disabled":false,"size":"default"}]},{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Success","optional":false},{"name":"slider_8","value":100.0,"type":"Slider","min":0,"max":100,"disabled":false,"variant":"success","size":"default"}]},{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Warning","optional":false},{"name":"slider_9","value":72.0,"type":"Slider","min":0,"max":100,"disabled":false,"variant":"warning","size":"default"}]},{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Destructive","optional":false},{"name":"slider_10","value":90.0,"type":"Slider","min":0,"max":100,"disabled":false,"variant":"destructive","size":"default"}]},{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Info","optional":false},{"name":"slider_11","value":45.0,"type":"Slider","min":0,"max":100,"disabled":false,"variant":"info","size":"default"}]},{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Muted","optional":false},{"name":"slider_12","value":30.0,"type":"Slider","min":0,"max":100,"disabled":false,"variant":"muted","size":"default"}]}]},"state":{"slider_7":60.0,"slider_8":100.0,"slider_9":72.0,"slider_10":90.0,"slider_11":45.0,"slider_12":30.0}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBMYWJlbCwgU2xpZGVyCgp3aXRoIENvbHVtbihnYXA9NCk6CiAgICB3aXRoIENvbHVtbihnYXA9Mik6CiAgICAgICAgTGFiZWwoIkRlZmF1bHQiKQogICAgICAgIFNsaWRlcih2YWx1ZT02MCkKICAgIHdpdGggQ29sdW1uKGdhcD0yKToKICAgICAgICBMYWJlbCgiU3VjY2VzcyIpCiAgICAgICAgU2xpZGVyKHZhbHVlPTEwMCwgdmFyaWFudD0ic3VjY2VzcyIpCiAgICB3aXRoIENvbHVtbihnYXA9Mik6CiAgICAgICAgTGFiZWwoIldhcm5pbmciKQogICAgICAgIFNsaWRlcih2YWx1ZT03MiwgdmFyaWFudD0id2FybmluZyIpCiAgICB3aXRoIENvbHVtbihnYXA9Mik6CiAgICAgICAgTGFiZWwoIkRlc3RydWN0aXZlIikKICAgICAgICBTbGlkZXIodmFsdWU9OTAsIHZhcmlhbnQ9ImRlc3RydWN0aXZlIikKICAgIHdpdGggQ29sdW1uKGdhcD0yKToKICAgICAgICBMYWJlbCgiSW5mbyIpCiAgICAgICAgU2xpZGVyKHZhbHVlPTQ1LCB2YXJpYW50PSJpbmZvIikKICAgIHdpdGggQ29sdW1uKGdhcD0yKToKICAgICAgICBMYWJlbCgiTXV0ZWQiKQogICAgICAgIFNsaWRlcih2YWx1ZT0zMCwgdmFyaWFudD0ibXV0ZWQiKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Column, Label, Slider

    with Column(gap=4):
        with Column(gap=2):
            Label("Default")
            Slider(value=60)
        with Column(gap=2):
            Label("Success")
            Slider(value=100, variant="success")
        with Column(gap=2):
            Label("Warning")
            Slider(value=72, variant="warning")
        with Column(gap=2):
            Label("Destructive")
            Slider(value=90, variant="destructive")
        with Column(gap=2):
            Label("Info")
            Slider(value=45, variant="info")
        with Column(gap=2):
            Label("Muted")
            Slider(value=30, variant="muted")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Column",
        "children": [
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Default", "optional": false},
              {
                "name": "slider_7",
                "value": 60.0,
                "type": "Slider",
                "min": 0,
                "max": 100,
                "disabled": false,
                "size": "default"
              }
            ]
          },
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Success", "optional": false},
              {
                "name": "slider_8",
                "value": 100.0,
                "type": "Slider",
                "min": 0,
                "max": 100,
                "disabled": false,
                "variant": "success",
                "size": "default"
              }
            ]
          },
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Warning", "optional": false},
              {
                "name": "slider_9",
                "value": 72.0,
                "type": "Slider",
                "min": 0,
                "max": 100,
                "disabled": false,
                "variant": "warning",
                "size": "default"
              }
            ]
          },
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Destructive", "optional": false},
              {
                "name": "slider_10",
                "value": 90.0,
                "type": "Slider",
                "min": 0,
                "max": 100,
                "disabled": false,
                "variant": "destructive",
                "size": "default"
              }
            ]
          },
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Info", "optional": false},
              {
                "name": "slider_11",
                "value": 45.0,
                "type": "Slider",
                "min": 0,
                "max": 100,
                "disabled": false,
                "variant": "info",
                "size": "default"
              }
            ]
          },
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Muted", "optional": false},
              {
                "name": "slider_12",
                "value": 30.0,
                "type": "Slider",
                "min": 0,
                "max": 100,
                "disabled": false,
                "variant": "muted",
                "size": "default"
              }
            ]
          }
        ]
      },
      "state": {
        "slider_7": 60.0,
        "slider_8": 100.0,
        "slider_9": 72.0,
        "slider_10": 90.0,
        "slider_11": 45.0,
        "slider_12": 30.0
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Sizes

Control the track thickness with `size`. The default is a medium weight; use `sm` for compact layouts and `lg` for prominent controls:

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Column","children":[{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Small","optional":false},{"name":"slider_13","value":60.0,"type":"Slider","min":0,"max":100,"disabled":false,"size":"sm"}]},{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Default","optional":false},{"name":"slider_14","value":60.0,"type":"Slider","min":0,"max":100,"disabled":false,"size":"default"}]},{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Large","optional":false},{"name":"slider_15","value":60.0,"type":"Slider","min":0,"max":100,"disabled":false,"size":"lg"}]}]},"state":{"slider_13":60.0,"slider_14":60.0,"slider_15":60.0}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBMYWJlbCwgU2xpZGVyCgp3aXRoIENvbHVtbihnYXA9NCk6CiAgICB3aXRoIENvbHVtbihnYXA9Mik6CiAgICAgICAgTGFiZWwoIlNtYWxsIikKICAgICAgICBTbGlkZXIodmFsdWU9NjAsIHNpemU9InNtIikKICAgIHdpdGggQ29sdW1uKGdhcD0yKToKICAgICAgICBMYWJlbCgiRGVmYXVsdCIpCiAgICAgICAgU2xpZGVyKHZhbHVlPTYwKQogICAgd2l0aCBDb2x1bW4oZ2FwPTIpOgogICAgICAgIExhYmVsKCJMYXJnZSIpCiAgICAgICAgU2xpZGVyKHZhbHVlPTYwLCBzaXplPSJsZyIpCg">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Column, Label, Slider

    with Column(gap=4):
        with Column(gap=2):
            Label("Small")
            Slider(value=60, size="sm")
        with Column(gap=2):
            Label("Default")
            Slider(value=60)
        with Column(gap=2):
            Label("Large")
            Slider(value=60, size="lg")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Column",
        "children": [
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Small", "optional": false},
              {
                "name": "slider_13",
                "value": 60.0,
                "type": "Slider",
                "min": 0,
                "max": 100,
                "disabled": false,
                "size": "sm"
              }
            ]
          },
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Default", "optional": false},
              {
                "name": "slider_14",
                "value": 60.0,
                "type": "Slider",
                "min": 0,
                "max": 100,
                "disabled": false,
                "size": "default"
              }
            ]
          },
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Large", "optional": false},
              {
                "name": "slider_15",
                "value": 60.0,
                "type": "Slider",
                "min": 0,
                "max": 100,
                "disabled": false,
                "size": "lg"
              }
            ]
          }
        ]
      },
      "state": {"slider_13": 60.0, "slider_14": 60.0, "slider_15": 60.0}
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Custom Colors

Use `indicator_class` for arbitrary track colors beyond the built-in variants:

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Column","children":[{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Storage Used","optional":false},{"cssClass":"pf-slider-flat","name":"slider_16","value":85.0,"type":"Slider","min":0,"max":100,"disabled":false,"size":"default","indicatorClass":"bg-red-500"}]},{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Upload Progress","optional":false},{"cssClass":"pf-slider-flat","name":"slider_17","value":45.0,"type":"Slider","min":0,"max":100,"disabled":false,"size":"default","indicatorClass":"bg-blue-500"}]}]},"state":{"slider_16":85.0,"slider_17":45.0}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBMYWJlbCwgU2xpZGVyCgp3aXRoIENvbHVtbihnYXA9NCk6CiAgICB3aXRoIENvbHVtbihnYXA9Mik6CiAgICAgICAgTGFiZWwoIlN0b3JhZ2UgVXNlZCIpCiAgICAgICAgU2xpZGVyKHZhbHVlPTg1LCBpbmRpY2F0b3JfY2xhc3M9ImJnLXJlZC01MDAiKQogICAgd2l0aCBDb2x1bW4oZ2FwPTIpOgogICAgICAgIExhYmVsKCJVcGxvYWQgUHJvZ3Jlc3MiKQogICAgICAgIFNsaWRlcih2YWx1ZT00NSwgaW5kaWNhdG9yX2NsYXNzPSJiZy1ibHVlLTUwMCIpCg">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Column, Label, Slider

    with Column(gap=4):
        with Column(gap=2):
            Label("Storage Used")
            Slider(value=85, indicator_class="bg-red-500")
        with Column(gap=2):
            Label("Upload Progress")
            Slider(value=45, indicator_class="bg-blue-500")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Column",
        "children": [
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Storage Used", "optional": false},
              {
                "cssClass": "pf-slider-flat",
                "name": "slider_16",
                "value": 85.0,
                "type": "Slider",
                "min": 0,
                "max": 100,
                "disabled": false,
                "size": "default",
                "indicatorClass": "bg-red-500"
              }
            ]
          },
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Upload Progress", "optional": false},
              {
                "cssClass": "pf-slider-flat",
                "name": "slider_17",
                "value": 45.0,
                "type": "Slider",
                "min": 0,
                "max": 100,
                "disabled": false,
                "size": "default",
                "indicatorClass": "bg-blue-500"
              }
            ]
          }
        ]
      },
      "state": {"slider_16": 85.0, "slider_17": 45.0}
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Vertical Orientation

Set `orientation="vertical"` for vertical sliders. They fill their container's height, so wrap them in a fixed-height parent:

<ComponentPreview json={{"view":{"cssClass":"gap-8 h-48 items-center justify-center","type":"Row","children":[{"name":"slider_18","value":75.0,"type":"Slider","min":0,"max":100,"disabled":false,"size":"default","orientation":"vertical"},{"name":"slider_19","value":50.0,"type":"Slider","min":0,"max":100,"disabled":false,"variant":"success","size":"default","orientation":"vertical"},{"name":"slider_20","value":25.0,"type":"Slider","min":0,"max":100,"disabled":false,"variant":"info","size":"default","orientation":"vertical"}]},"state":{"slider_18":75.0,"slider_19":50.0,"slider_20":25.0}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgUm93LCBTbGlkZXIKCndpdGggUm93KGNzc19jbGFzcz0iZ2FwLTggaC00OCBpdGVtcy1jZW50ZXIganVzdGlmeS1jZW50ZXIiKToKICAgIFNsaWRlcih2YWx1ZT03NSwgb3JpZW50YXRpb249InZlcnRpY2FsIikKICAgIFNsaWRlcih2YWx1ZT01MCwgb3JpZW50YXRpb249InZlcnRpY2FsIiwgdmFyaWFudD0ic3VjY2VzcyIpCiAgICBTbGlkZXIodmFsdWU9MjUsIG9yaWVudGF0aW9uPSJ2ZXJ0aWNhbCIsIHZhcmlhbnQ9ImluZm8iKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Row, Slider

    with Row(css_class="gap-8 h-48 items-center justify-center"):
        Slider(value=75, orientation="vertical")
        Slider(value=50, orientation="vertical", variant="success")
        Slider(value=25, orientation="vertical", variant="info")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-8 h-48 items-center justify-center",
        "type": "Row",
        "children": [
          {
            "name": "slider_18",
            "value": 75.0,
            "type": "Slider",
            "min": 0,
            "max": 100,
            "disabled": false,
            "size": "default",
            "orientation": "vertical"
          },
          {
            "name": "slider_19",
            "value": 50.0,
            "type": "Slider",
            "min": 0,
            "max": 100,
            "disabled": false,
            "variant": "success",
            "size": "default",
            "orientation": "vertical"
          },
          {
            "name": "slider_20",
            "value": 25.0,
            "type": "Slider",
            "min": 0,
            "max": 100,
            "disabled": false,
            "variant": "info",
            "size": "default",
            "orientation": "vertical"
          }
        ]
      },
      "state": {"slider_18": 75.0, "slider_19": 50.0, "slider_20": 25.0}
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Handle Styles

The `handle_style` parameter changes the thumb shape. Use `"bar"` for a tall rounded rectangle instead of the default circle:

<ComponentPreview json={{"view":{"cssClass":"gap-4","type":"Column","children":[{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Circle (default)","optional":false},{"name":"slider_21","value":50.0,"type":"Slider","min":0,"max":100,"disabled":false,"size":"default"}]},{"cssClass":"gap-2","type":"Column","children":[{"type":"Label","text":"Bar","optional":false},{"name":"slider_22","value":50.0,"type":"Slider","min":0,"max":100,"disabled":false,"size":"default","handleStyle":"bar"}]}]},"state":{"slider_21":50.0,"slider_22":50.0}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQ29sdW1uLCBMYWJlbCwgU2xpZGVyCgp3aXRoIENvbHVtbihnYXA9NCk6CiAgICB3aXRoIENvbHVtbihnYXA9Mik6CiAgICAgICAgTGFiZWwoIkNpcmNsZSAoZGVmYXVsdCkiKQogICAgICAgIFNsaWRlcih2YWx1ZT01MCkKICAgIHdpdGggQ29sdW1uKGdhcD0yKToKICAgICAgICBMYWJlbCgiQmFyIikKICAgICAgICBTbGlkZXIodmFsdWU9NTAsIGhhbmRsZV9zdHlsZT0iYmFyIikK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Column, Label, Slider

    with Column(gap=4):
        with Column(gap=2):
            Label("Circle (default)")
            Slider(value=50)
        with Column(gap=2):
            Label("Bar")
            Slider(value=50, handle_style="bar")
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "cssClass": "gap-4",
        "type": "Column",
        "children": [
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Circle (default)", "optional": false},
              {
                "name": "slider_21",
                "value": 50.0,
                "type": "Slider",
                "min": 0,
                "max": 100,
                "disabled": false,
                "size": "default"
              }
            ]
          },
          {
            "cssClass": "gap-2",
            "type": "Column",
            "children": [
              {"type": "Label", "text": "Bar", "optional": false},
              {
                "name": "slider_22",
                "value": 50.0,
                "type": "Slider",
                "min": 0,
                "max": 100,
                "disabled": false,
                "size": "default",
                "handleStyle": "bar"
              }
            ]
          }
        ]
      },
      "state": {"slider_21": 50.0, "slider_22": 50.0}
    }
    ```
  </CodeGroup>
</ComponentPreview>

## API Reference

<Card icon="code" title="Slider Parameters">
  <ParamField body="value" type="float | None" default="None">
    Initial value of the slider.
  </ParamField>

  <ParamField body="name" type="str | None" default="None">
    State key for the slider's current value. Set this to bind the slider to state for display or form submission.
  </ParamField>

  <ParamField body="min" type="float" default="0">
    Minimum value of the range.
  </ParamField>

  <ParamField body="max" type="float" default="100">
    Maximum value of the range.
  </ParamField>

  <ParamField body="step" type="float | None" default="None">
    Step increment. If not provided, the slider moves continuously.
  </ParamField>

  <ParamField body="disabled" type="bool" default="False">
    Whether the slider is non-interactive.
  </ParamField>

  <ParamField body="variant" type="str" default="default">
    Visual variant for the filled track: `"default"`, `"success"`, `"warning"`, `"destructive"`, `"info"`, `"muted"`.
  </ParamField>

  <ParamField body="size" type="str" default="default">
    Track thickness: `"sm"` (4px), `"default"` (6px), `"lg"` (10px).
  </ParamField>

  <ParamField body="indicator_class" type="str | None" default="None">
    Tailwind classes for the filled track. Overrides variant coloring.
  </ParamField>

  <ParamField body="orientation" type="str" default="horizontal">
    Layout direction: `"horizontal"` or `"vertical"`. Vertical sliders fill their container's height.
  </ParamField>

  <ParamField body="handle_style" type="str" default="circle">
    Thumb shape: `"circle"` (default round) or `"bar"` (tall rounded rectangle).
  </ParamField>

  <ParamField body="on_change" type="Action | list[Action] | None" default="None">
    Action(s) to execute when the value changes. `$event` is the current numeric value.
  </ParamField>

  <ParamField body="css_class" type="str | None" default="None">
    Additional Tailwind CSS classes appended to the component's built-in styles.
  </ParamField>
</Card>

## Protocol Reference

```json Slider theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "Slider",
  "name?": "string",
  "min?": 0,
  "max?": 100,
  "value?": "number | Action[] | string",
  "step?": "number",
  "range?": false,
  "disabled?": false,
  "variant?": "default | success | warning | destructive | info | muted",
  "size?": "sm | default | lg",
  "indicatorClass?": "string",
  "orientation?": "horizontal | vertical",
  "handleStyle?": "circle | bar",
  "onChange?": "Action | Action[]",
  "cssClass?": "string"
}
```

For the complete protocol schema, see [Slider](/protocol/slider).


Built with [Mintlify](https://mintlify.com).