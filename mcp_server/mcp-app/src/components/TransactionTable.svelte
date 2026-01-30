<script lang="ts">
/**
 * Transaction table component for displaying property sales.
 * Supports interactive column sorting.
 */
import type { Transaction } from "../lib/types";
import { formatPrice, formatDate } from "../lib/formatters";

interface Props {
  transactions: Transaction[];
}

let { transactions }: Props = $props();

// Sort state
type SortColumn = "date" | "address" | "type" | "price";
type SortDirection = "asc" | "desc";

let sortColumn = $state<SortColumn>("date");
let sortDirection = $state<SortDirection>("desc"); // Most recent first by default

// Sort handler
function handleSort(column: SortColumn) {
  if (sortColumn === column) {
    // Toggle direction
    sortDirection = sortDirection === "asc" ? "desc" : "asc";
  } else {
    // New column - default direction
    sortColumn = column;
    sortDirection = column === "price" ? "desc" : column === "date" ? "desc" : "asc";
  }
}

// Sorted transactions
let sortedTransactions = $derived(() => {
  const sorted = [...transactions];

  sorted.sort((a, b) => {
    let comparison = 0;

    switch (sortColumn) {
      case "date":
        comparison = (a.date || "").localeCompare(b.date || "");
        break;
      case "address":
        comparison = formatAddress(a).localeCompare(formatAddress(b));
        break;
      case "type":
        comparison = (a.property_type || "").localeCompare(b.property_type || "");
        break;
      case "price":
        comparison = (a.price || 0) - (b.price || 0);
        break;
    }

    return sortDirection === "asc" ? comparison : -comparison;
  });

  return sorted;
});

function formatAddress(tx: Transaction): string {
  const parts = [tx.paon, tx.street, tx.postcode].filter(Boolean);
  return parts.join(", ") || "Address unknown";
}

function formatPropertyType(type: string | undefined): string {
  const types: Record<string, string> = {
    D: "Detached",
    S: "Semi-detached",
    T: "Terraced",
    F: "Flat",
    O: "Other",
  };
  return types[type || ""] || type || "Unknown";
}

// Sort indicator
function getSortIndicator(column: SortColumn): string {
  if (sortColumn !== column) return "";
  return sortDirection === "asc" ? " ↑" : " ↓";
}
</script>

<div class="table-container">
  <table class="comps-table">
    <thead>
      <tr>
        <th
          class="sortable"
          class:sorted={sortColumn === "date"}
          onclick={() => handleSort("date")}
        >
          Date{getSortIndicator("date")}
        </th>
        <th
          class="sortable"
          class:sorted={sortColumn === "address"}
          onclick={() => handleSort("address")}
        >
          Address{getSortIndicator("address")}
        </th>
        <th
          class="sortable"
          class:sorted={sortColumn === "type"}
          onclick={() => handleSort("type")}
        >
          Type{getSortIndicator("type")}
        </th>
        <th
          class="sortable price-col"
          class:sorted={sortColumn === "price"}
          onclick={() => handleSort("price")}
        >
          Price{getSortIndicator("price")}
        </th>
      </tr>
    </thead>
    <tbody>
      {#each sortedTransactions() as tx}
        <tr>
          <td class="date-col">{formatDate(tx.date)}</td>
          <td class="address-col">{formatAddress(tx)}</td>
          <td>{formatPropertyType(tx.property_type)}</td>
          <td class="price-col">{formatPrice(tx.price)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
.table-container {
  overflow-x: auto;
  margin-top: 16px;
}

.comps-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-text-sm-size, 14px);
}

.comps-table th,
.comps-table td {
  padding: 12px 8px;
  text-align: left;
  border-bottom: 1px solid var(--color-border-primary, #e0e0e0);
}

.comps-table th {
  font-weight: var(--font-weight-semibold, 600);
  color: var(--color-text-secondary, #666);
  text-transform: uppercase;
  font-size: var(--font-text-xs-size, 11px);
  letter-spacing: 0.5px;
}

.comps-table th.sortable {
  cursor: pointer;
  user-select: none;
  transition: background-color 0.15s ease;
}

.comps-table th.sortable:hover {
  background: var(--color-background-secondary, #f5f5f5);
}

.comps-table th.sorted {
  color: var(--color-text-primary, #333);
  background: var(--color-background-secondary, #f5f5f5);
}

.comps-table tbody tr:hover {
  background: var(--color-background-secondary, #f5f5f5);
}

.date-col {
  white-space: nowrap;
}

.address-col {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.price-col {
  text-align: right;
  font-weight: var(--font-weight-semibold, 600);
  white-space: nowrap;
}
</style>
