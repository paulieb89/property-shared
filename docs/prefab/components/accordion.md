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

# Accordion

> Collapsible content sections for progressive disclosure.

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

Accordions let users expand and collapse sections to reveal content progressively. Each `AccordionItem` has a clickable title and hidden content that appears on expand.

## Basic Usage

<ComponentPreview json={{"view":{"type":"Accordion","multiple":false,"collapsible":true,"children":[{"type":"AccordionItem","title":"What is the Answer?","children":[{"content":"Forty-two. The Answer to the Ultimate Question of Life, the Universe, and Everything.","type":"Text"}]},{"type":"AccordionItem","title":"What is the Heart of Gold?","children":[{"content":"A starship powered by the Infinite Improbability Drive. It can pass through every conceivable point in every conceivable universe almost simultaneously.","type":"Text"}]},{"type":"AccordionItem","title":"What is Deep Thought?","children":[{"content":"A supercomputer designed to find the Answer to the Ultimate Question. It took 7.5 million years to compute: 42.","type":"Text"}]}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQWNjb3JkaW9uLCBBY2NvcmRpb25JdGVtLCBUZXh0Cgp3aXRoIEFjY29yZGlvbigpOgogICAgd2l0aCBBY2NvcmRpb25JdGVtKCJXaGF0IGlzIHRoZSBBbnN3ZXI_Iik6CiAgICAgICAgVGV4dCgKICAgICAgICAgICAgIkZvcnR5LXR3by4gVGhlIEFuc3dlciB0byB0aGUgVWx0aW1hdGUgIgogICAgICAgICAgICAiUXVlc3Rpb24gb2YgTGlmZSwgdGhlIFVuaXZlcnNlLCBhbmQgIgogICAgICAgICAgICAiRXZlcnl0aGluZy4iCiAgICAgICAgKQogICAgd2l0aCBBY2NvcmRpb25JdGVtKCJXaGF0IGlzIHRoZSBIZWFydCBvZiBHb2xkPyIpOgogICAgICAgIFRleHQoCiAgICAgICAgICAgICJBIHN0YXJzaGlwIHBvd2VyZWQgYnkgdGhlIEluZmluaXRlICIKICAgICAgICAgICAgIkltcHJvYmFiaWxpdHkgRHJpdmUuIEl0IGNhbiBwYXNzIHRocm91Z2ggIgogICAgICAgICAgICAiZXZlcnkgY29uY2VpdmFibGUgcG9pbnQgaW4gZXZlcnkgIgogICAgICAgICAgICAiY29uY2VpdmFibGUgdW5pdmVyc2UgYWxtb3N0IHNpbXVsdGFuZW91c2x5LiIKICAgICAgICApCiAgICB3aXRoIEFjY29yZGlvbkl0ZW0oIldoYXQgaXMgRGVlcCBUaG91Z2h0PyIpOgogICAgICAgIFRleHQoCiAgICAgICAgICAgICJBIHN1cGVyY29tcHV0ZXIgZGVzaWduZWQgdG8gZmluZCB0aGUgIgogICAgICAgICAgICAiQW5zd2VyIHRvIHRoZSBVbHRpbWF0ZSBRdWVzdGlvbi4gSXQgdG9vayAiCiAgICAgICAgICAgICI3LjUgbWlsbGlvbiB5ZWFycyB0byBjb21wdXRlOiA0Mi4iCiAgICAgICAgKQo">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Accordion, AccordionItem, Text

    with Accordion():
        with AccordionItem("What is the Answer?"):
            Text(
                "Forty-two. The Answer to the Ultimate "
                "Question of Life, the Universe, and "
                "Everything."
            )
        with AccordionItem("What is the Heart of Gold?"):
            Text(
                "A starship powered by the Infinite "
                "Improbability Drive. It can pass through "
                "every conceivable point in every "
                "conceivable universe almost simultaneously."
            )
        with AccordionItem("What is Deep Thought?"):
            Text(
                "A supercomputer designed to find the "
                "Answer to the Ultimate Question. It took "
                "7.5 million years to compute: 42."
            )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "Accordion",
        "multiple": false,
        "collapsible": true,
        "children": [
          {
            "type": "AccordionItem",
            "title": "What is the Answer?",
            "children": [
              {
                "content": "Forty-two. The Answer to the Ultimate Question of Life, the Universe, and Everything.",
                "type": "Text"
              }
            ]
          },
          {
            "type": "AccordionItem",
            "title": "What is the Heart of Gold?",
            "children": [
              {
                "content": "A starship powered by the Infinite Improbability Drive. It can pass through every conceivable point in every conceivable universe almost simultaneously.",
                "type": "Text"
              }
            ]
          },
          {
            "type": "AccordionItem",
            "title": "What is Deep Thought?",
            "children": [
              {
                "content": "A supercomputer designed to find the Answer to the Ultimate Question. It took 7.5 million years to compute: 42.",
                "type": "Text"
              }
            ]
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## Default Open

Use `default_open_items` to expand items when the accordion first renders. Pass an index or title.

<ComponentPreview json={{"view":{"type":"Accordion","multiple":false,"collapsible":true,"defaultValues":["What is the Answer?"],"children":[{"type":"AccordionItem","title":"What is the Answer?","children":[{"content":"Forty-two. The Answer to the Ultimate Question of Life, the Universe, and Everything.","type":"Text"}]},{"type":"AccordionItem","title":"What is the Heart of Gold?","children":[{"content":"A starship powered by the Infinite Improbability Drive. It can pass through every conceivable point in every conceivable universe almost simultaneously.","type":"Text"}]},{"type":"AccordionItem","title":"What is Deep Thought?","children":[{"content":"A supercomputer designed to find the Answer to the Ultimate Question. It took 7.5 million years to compute: 42.","type":"Text"}]}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQWNjb3JkaW9uLCBBY2NvcmRpb25JdGVtLCBUZXh0Cgp3aXRoIEFjY29yZGlvbihkZWZhdWx0X29wZW5faXRlbXM9MCk6CiAgICB3aXRoIEFjY29yZGlvbkl0ZW0oIldoYXQgaXMgdGhlIEFuc3dlcj8iKToKICAgICAgICBUZXh0KAogICAgICAgICAgICAiRm9ydHktdHdvLiBUaGUgQW5zd2VyIHRvIHRoZSBVbHRpbWF0ZSAiCiAgICAgICAgICAgICJRdWVzdGlvbiBvZiBMaWZlLCB0aGUgVW5pdmVyc2UsIGFuZCAiCiAgICAgICAgICAgICJFdmVyeXRoaW5nLiIKICAgICAgICApCiAgICB3aXRoIEFjY29yZGlvbkl0ZW0oIldoYXQgaXMgdGhlIEhlYXJ0IG9mIEdvbGQ_Iik6CiAgICAgICAgVGV4dCgKICAgICAgICAgICAgIkEgc3RhcnNoaXAgcG93ZXJlZCBieSB0aGUgSW5maW5pdGUgIgogICAgICAgICAgICAiSW1wcm9iYWJpbGl0eSBEcml2ZS4gSXQgY2FuIHBhc3MgdGhyb3VnaCAiCiAgICAgICAgICAgICJldmVyeSBjb25jZWl2YWJsZSBwb2ludCBpbiBldmVyeSAiCiAgICAgICAgICAgICJjb25jZWl2YWJsZSB1bml2ZXJzZSBhbG1vc3Qgc2ltdWx0YW5lb3VzbHkuIgogICAgICAgICkKICAgIHdpdGggQWNjb3JkaW9uSXRlbSgiV2hhdCBpcyBEZWVwIFRob3VnaHQ_Iik6CiAgICAgICAgVGV4dCgKICAgICAgICAgICAgIkEgc3VwZXJjb21wdXRlciBkZXNpZ25lZCB0byBmaW5kIHRoZSAiCiAgICAgICAgICAgICJBbnN3ZXIgdG8gdGhlIFVsdGltYXRlIFF1ZXN0aW9uLiBJdCB0b29rICIKICAgICAgICAgICAgIjcuNSBtaWxsaW9uIHllYXJzIHRvIGNvbXB1dGU6IDQyLiIKICAgICAgICApCg">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Accordion, AccordionItem, Text

    with Accordion(default_open_items=0):
        with AccordionItem("What is the Answer?"):
            Text(
                "Forty-two. The Answer to the Ultimate "
                "Question of Life, the Universe, and "
                "Everything."
            )
        with AccordionItem("What is the Heart of Gold?"):
            Text(
                "A starship powered by the Infinite "
                "Improbability Drive. It can pass through "
                "every conceivable point in every "
                "conceivable universe almost simultaneously."
            )
        with AccordionItem("What is Deep Thought?"):
            Text(
                "A supercomputer designed to find the "
                "Answer to the Ultimate Question. It took "
                "7.5 million years to compute: 42."
            )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "Accordion",
        "multiple": false,
        "collapsible": true,
        "defaultValues": ["What is the Answer?"],
        "children": [
          {
            "type": "AccordionItem",
            "title": "What is the Answer?",
            "children": [
              {
                "content": "Forty-two. The Answer to the Ultimate Question of Life, the Universe, and Everything.",
                "type": "Text"
              }
            ]
          },
          {
            "type": "AccordionItem",
            "title": "What is the Heart of Gold?",
            "children": [
              {
                "content": "A starship powered by the Infinite Improbability Drive. It can pass through every conceivable point in every conceivable universe almost simultaneously.",
                "type": "Text"
              }
            ]
          },
          {
            "type": "AccordionItem",
            "title": "What is Deep Thought?",
            "children": [
              {
                "content": "A supercomputer designed to find the Answer to the Ultimate Question. It took 7.5 million years to compute: 42.",
                "type": "Text"
              }
            ]
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

You can also assign a stable `value` to items and reference them by name, which is useful when item order might change:

```python {1, 2} theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
with Accordion(default_open_items="faq"):
    with AccordionItem("FAQ", value="faq"):
        Text("Frequently asked questions...")
    with AccordionItem("Contact"):
        Text("Get in touch...")
```

## Multiple Open

Set `multiple=True` to allow more than one section open at a time.

<ComponentPreview json={{"view":{"type":"Accordion","multiple":true,"collapsible":true,"defaultValues":["Who is Arthur Dent?","Who is Ford Prefect?"],"children":[{"type":"AccordionItem","title":"Who is Arthur Dent?","children":[{"content":"An ordinary human from Earth, unexpectedly swept into the cosmos when his planet is demolished to make way for a hyperspace bypass.","type":"Text"}]},{"type":"AccordionItem","title":"Who is Ford Prefect?","children":[{"content":"A researcher for the Hitchhiker's Guide to the Galaxy, and Arthur's best friend. He's from a small planet somewhere in the vicinity of Betelgeuse.","type":"Text"}]},{"type":"AccordionItem","title":"What is the Guide?","children":[{"content":"A digital reference with the words 'Don't Panic' written in large, friendly letters on the cover.","type":"Text"}]}]}}} playground="ZnJvbSBwcmVmYWJfdWkuY29tcG9uZW50cyBpbXBvcnQgQWNjb3JkaW9uLCBBY2NvcmRpb25JdGVtLCBUZXh0Cgp3aXRoIEFjY29yZGlvbigKICAgIG11bHRpcGxlPVRydWUsCiAgICBkZWZhdWx0X29wZW5faXRlbXM9WzAsIDFdCik6CiAgICB3aXRoIEFjY29yZGlvbkl0ZW0oIldobyBpcyBBcnRodXIgRGVudD8iKToKICAgICAgICBUZXh0KAogICAgICAgICAgICAiQW4gb3JkaW5hcnkgaHVtYW4gZnJvbSBFYXJ0aCwgdW5leHBlY3RlZGx5ICIKICAgICAgICAgICAgInN3ZXB0IGludG8gdGhlIGNvc21vcyB3aGVuIGhpcyBwbGFuZXQgaXMgIgogICAgICAgICAgICAiZGVtb2xpc2hlZCB0byBtYWtlIHdheSBmb3IgYSBoeXBlcnNwYWNlICIKICAgICAgICAgICAgImJ5cGFzcy4iCiAgICAgICAgKQogICAgd2l0aCBBY2NvcmRpb25JdGVtKCJXaG8gaXMgRm9yZCBQcmVmZWN0PyIpOgogICAgICAgIFRleHQoCiAgICAgICAgICAgICJBIHJlc2VhcmNoZXIgZm9yIHRoZSBIaXRjaGhpa2VyJ3MgR3VpZGUgIgogICAgICAgICAgICAidG8gdGhlIEdhbGF4eSwgYW5kIEFydGh1cidzIGJlc3QgZnJpZW5kLiAiCiAgICAgICAgICAgICJIZSdzIGZyb20gYSBzbWFsbCBwbGFuZXQgc29tZXdoZXJlIGluIHRoZSAiCiAgICAgICAgICAgICJ2aWNpbml0eSBvZiBCZXRlbGdldXNlLiIKICAgICAgICApCiAgICB3aXRoIEFjY29yZGlvbkl0ZW0oIldoYXQgaXMgdGhlIEd1aWRlPyIpOgogICAgICAgIFRleHQoCiAgICAgICAgICAgICJBIGRpZ2l0YWwgcmVmZXJlbmNlIHdpdGggdGhlIHdvcmRzICIKICAgICAgICAgICAgIidEb24ndCBQYW5pYycgd3JpdHRlbiBpbiBsYXJnZSwgZnJpZW5kbHkgIgogICAgICAgICAgICAibGV0dGVycyBvbiB0aGUgY292ZXIuIgogICAgICAgICkK">
  <CodeGroup>
    ```python Python icon="python" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    from prefab_ui.components import Accordion, AccordionItem, Text

    with Accordion(
        multiple=True,
        default_open_items=[0, 1]
    ):
        with AccordionItem("Who is Arthur Dent?"):
            Text(
                "An ordinary human from Earth, unexpectedly "
                "swept into the cosmos when his planet is "
                "demolished to make way for a hyperspace "
                "bypass."
            )
        with AccordionItem("Who is Ford Prefect?"):
            Text(
                "A researcher for the Hitchhiker's Guide "
                "to the Galaxy, and Arthur's best friend. "
                "He's from a small planet somewhere in the "
                "vicinity of Betelgeuse."
            )
        with AccordionItem("What is the Guide?"):
            Text(
                "A digital reference with the words "
                "'Don't Panic' written in large, friendly "
                "letters on the cover."
            )
    ```

    ```json Protocol icon="brackets-curly" theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
    {
      "view": {
        "type": "Accordion",
        "multiple": true,
        "collapsible": true,
        "defaultValues": ["Who is Arthur Dent?", "Who is Ford Prefect?"],
        "children": [
          {
            "type": "AccordionItem",
            "title": "Who is Arthur Dent?",
            "children": [
              {
                "content": "An ordinary human from Earth, unexpectedly swept into the cosmos when his planet is demolished to make way for a hyperspace bypass.",
                "type": "Text"
              }
            ]
          },
          {
            "type": "AccordionItem",
            "title": "Who is Ford Prefect?",
            "children": [
              {
                "content": "A researcher for the Hitchhiker's Guide to the Galaxy, and Arthur's best friend. He's from a small planet somewhere in the vicinity of Betelgeuse.",
                "type": "Text"
              }
            ]
          },
          {
            "type": "AccordionItem",
            "title": "What is the Guide?",
            "children": [
              {
                "content": "A digital reference with the words 'Don't Panic' written in large, friendly letters on the cover.",
                "type": "Text"
              }
            ]
          }
        ]
      }
    }
    ```
  </CodeGroup>
</ComponentPreview>

## API Reference

<Card icon="code" title="Accordion Parameters">
  <ParamField body="default_open_items" type="int | str | list[int | str] | None" default="None">
    Initially expanded item(s). Pass an index to select by position, or a string to match by title.
  </ParamField>

  <ParamField body="multiple" type="bool" default="False">
    Allow multiple items to be open simultaneously.
  </ParamField>

  <ParamField body="collapsible" type="bool" default="True">
    Whether the open item can be collapsed.
  </ParamField>

  <ParamField body="css_class" type="str | None" default="None">
    Additional Tailwind CSS classes.
  </ParamField>
</Card>

<Card icon="code" title="AccordionItem Parameters">
  <ParamField body="title" type="str" required>
    Trigger label text. Can be passed as a positional argument.
  </ParamField>

  <ParamField body="value" type="str | None" default="None">
    Unique value identifying this item. Defaults to the title.
  </ParamField>
</Card>

## Protocol Reference

```json Accordion theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "Accordion",
  "children?": "[Component]",
  "let?": "object",
  "multiple?": false,
  "collapsible?": true,
  "default_open_items?": "number | string | Action[]",
  "defaultValues?": "Action[]",
  "cssClass?": "string"
}
```

```json AccordionItem theme={"theme":{"light":"snazzy-light","dark":"dark-plus"}}
{
  "type": "AccordionItem",
  "children?": "[Component]",
  "let?": "object",
  "title": "string (required)",
  "value?": "string",
  "cssClass?": "string"
}
```

For the complete protocol schema, see [Accordion](/protocol/accordion), [AccordionItem](/protocol/accordion-item).


Built with [Mintlify](https://mintlify.com).