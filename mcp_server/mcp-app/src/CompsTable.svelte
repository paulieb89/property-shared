<script lang="ts">
interface Transaction {
  date: string;
  paon?: string;
  street?: string;
  postcode?: string;
  price: number;
  property_type?: string;
}

type SortKey = "date" | "price" | "property_type";
type SortDir = "asc" | "desc";

let { transactions }: { transactions: Transaction[] } = $props();

let sortKey = $state<SortKey>("date");
let sortDir = $state<SortDir>("desc");
let typeFilter = $state<string>("all");

// Get unique property types for filter
let propertyTypes = $derived(() => {
  const types = new Set<string>();
  for (const tx of transactions) {
    if (tx.property_type) types.add(tx.property_type);
  }
  return Array.from(types).sort();
});

// Filtered and sorted transactions
let displayTransactions = $derived(() => {
  let filtered = transactions;

  // Apply type filter
  if (typeFilter !== "all") {
    filtered = filtered.filter(tx => tx.property_type === typeFilter);
  }

  // Sort
  return [...filtered].sort((a, b) => {
    let cmp = 0;
    if (sortKey === "date") {
      cmp = new Date(a.date).getTime() - new Date(b.date).getTime();
    } else if (sortKey === "price") {
      cmp = a.price - b.price;
    } else if (sortKey === "property_type") {
      cmp = (a.property_type ?? "").localeCompare(b.property_type ?? "");
    }
    return sortDir === "asc" ? cmp : -cmp;
  });
});

function formatPrice(price: number): string {
  return "£" + price.toLocaleString("en-GB");
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-GB");
}

function formatAddress(tx: Transaction): string {
  return [tx.paon, tx.street, tx.postcode].filter(Boolean).join(" ");
}

function handleSort(key: SortKey) {
  if (sortKey === key) {
    sortDir = sortDir === "asc" ? "desc" : "asc";
  } else {
    sortKey = key;
    sortDir = key === "price" ? "desc" : "asc";
  }
}

function getSortIndicator(key: SortKey): string {
  if (sortKey !== key) return "";
  return sortDir === "asc" ? " ▲" : " ▼";
}
</script>

<div class="table-controls">
  <label>
    Filter by type:
    <select bind:value={typeFilter}>
      <option value="all">All types</option>
      {#each propertyTypes() as ptype}
        <option value={ptype}>{ptype}</option>
      {/each}
    </select>
  </label>
  <span class="count">Showing {displayTransactions().length} of {transactions.length}</span>
</div>

<div class="table-wrapper">
  <table>
    <thead>
      <tr>
        <th class="sortable" onclick={() => handleSort("date")}>
          Date{getSortIndicator("date")}
        </th>
        <th>Address</th>
        <th class="sortable" onclick={() => handleSort("price")}>
          Price{getSortIndicator("price")}
        </th>
        <th class="sortable" onclick={() => handleSort("property_type")}>
          Type{getSortIndicator("property_type")}
        </th>
      </tr>
    </thead>
    <tbody>
      {#each displayTransactions() as tx}
        <tr>
          <td>{formatDate(tx.date)}</td>
          <td>{formatAddress(tx)}</td>
          <td class="price">{formatPrice(tx.price)}</td>
          <td>{tx.property_type ?? ""}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
.table-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 16px;
  flex-wrap: wrap;
}

.table-controls label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--font-text-sm-size, 14px);
}

.table-controls select {
  padding: 4px 8px;
  border: 1px solid var(--color-border-primary, #e0e0e0);
  border-radius: var(--border-radius-sm, 4px);
  background: var(--color-background-primary, #fff);
  color: var(--color-text-primary, #1a1a1a);
}

.count {
  font-size: var(--font-text-sm-size, 14px);
  color: var(--color-text-secondary, #666);
}

.table-wrapper {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-text-sm-size, 14px);
}

th, td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid var(--color-border-primary, #e0e0e0);
}

th {
  background: var(--color-background-secondary, #f5f5f5);
  font-weight: var(--font-weight-semibold, 600);
  white-space: nowrap;
}

th.sortable {
  cursor: pointer;
  user-select: none;
}

th.sortable:hover {
  background: var(--color-background-tertiary, #e8e8e8);
}

tr:hover {
  background: var(--color-background-ghost, rgba(0,0,0,0.02));
}

.price {
  font-family: var(--font-mono, monospace);
  text-align: right;
}
</style>
