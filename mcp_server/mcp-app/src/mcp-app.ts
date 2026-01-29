/**
 * Property Comps MCP App - follows official ext-apps pattern exactly
 */
import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
  type McpUiHostContext,
} from "@modelcontextprotocol/ext-apps";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import "./global.css";

interface Transaction {
  date: string;
  paon?: string;
  street?: string;
  postcode?: string;
  price: number;
  property_type?: string;
}

interface CompsData {
  median?: number;
  mean?: number;
  count?: number;
  percentile_25?: number;
  percentile_75?: number;
  transactions?: Transaction[];
}

const loadingEl = document.getElementById("loading")!;
const contentEl = document.getElementById("content")!;
const statsEl = document.getElementById("stats")!;
const tableBody = document.querySelector("#comps-table tbody")!;

function formatPrice(price: number): string {
  return "£" + price.toLocaleString("en-GB");
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-GB");
}

function render(data: CompsData) {
  // Stats
  const median = data.median ? formatPrice(data.median) : "N/A";
  const mean = data.mean ? formatPrice(data.mean) : "N/A";
  const count = data.count ?? 0;
  const p25 = data.percentile_25 ? formatPrice(data.percentile_25) : "?";
  const p75 = data.percentile_75 ? formatPrice(data.percentile_75) : "?";

  statsEl.innerHTML = `
    <p><strong>Median:</strong> ${median}</p>
    <p><strong>Mean:</strong> ${mean}</p>
    <p><strong>Count:</strong> ${count}</p>
    <p><strong>Range:</strong> ${p25} - ${p75}</p>
  `;

  // Table
  tableBody.innerHTML = "";
  for (const tx of data.transactions ?? []) {
    const row = document.createElement("tr");
    const addr = [tx.paon, tx.street, tx.postcode].filter(Boolean).join(" ");
    row.innerHTML = `
      <td>${formatDate(tx.date)}</td>
      <td>${addr}</td>
      <td>${formatPrice(tx.price)}</td>
      <td>${tx.property_type ?? ""}</td>
    `;
    tableBody.appendChild(row);
  }

  loadingEl.style.display = "none";
  contentEl.style.display = "block";
}

function extractCompsData(result: CallToolResult): CompsData | null {
  if (result.structuredContent) {
    return result.structuredContent as CompsData;
  }
  const textContent = result.content?.find((c) => c.type === "text");
  if (textContent && "text" in textContent) {
    try {
      return JSON.parse(textContent.text) as CompsData;
    } catch {
      return null;
    }
  }
  return null;
}

function handleHostContextChanged(ctx: McpUiHostContext) {
  if (ctx.theme) {
    applyDocumentTheme(ctx.theme);
  }
  if (ctx.styles?.variables) {
    applyHostStyleVariables(ctx.styles.variables);
  }
  if (ctx.styles?.css?.fonts) {
    applyHostFonts(ctx.styles.css.fonts);
  }
  if (ctx.safeAreaInsets) {
    document.body.style.paddingTop = `${ctx.safeAreaInsets.top}px`;
    document.body.style.paddingRight = `${ctx.safeAreaInsets.right}px`;
    document.body.style.paddingBottom = `${ctx.safeAreaInsets.bottom}px`;
    document.body.style.paddingLeft = `${ctx.safeAreaInsets.left}px`;
  }
}

// 1. Create app instance
const app = new App({ name: "Property Comps Dashboard", version: "1.0.0" });

// 2. Register handlers BEFORE connecting
app.onteardown = async () => {
  console.info("[MCP App] Teardown");
  return {};
};

app.ontoolinput = (params) => {
  console.info("[MCP App] Tool input:", params);
  const postcode = params.arguments?.postcode;
  if (postcode) {
    loadingEl.textContent = `Searching comparable sales for ${postcode}...`;
  }
};

app.ontoolresult = (result) => {
  console.info("[MCP App] Tool result:", result);
  const data = extractCompsData(result);
  if (data) {
    render(data);
  }
};

app.ontoolcancelled = (params) => {
  console.info("[MCP App] Tool cancelled:", params.reason);
};

app.onerror = console.error;

app.onhostcontextchanged = handleHostContextChanged;

// 3. Connect to host
app.connect().then(() => {
  console.info("[MCP App] Connected");
  const ctx = app.getHostContext();
  if (ctx) {
    handleHostContextChanged(ctx);
  }
});
