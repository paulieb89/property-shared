<script lang="ts">
/**
 * Transaction table component for displaying property sales.
 * BOUCH Design System - Interactive sortable table with reactive feedback
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
    S: "Semi",
    T: "Terrace",
    F: "Flat",
    O: "Other",
  };
  return types[type || ""] || type || "—";
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
      {#each sortedTransactions() as tx, i}
        <tr style="animation-delay: {i * 0.02}s">
          <td class="date-col">{formatDate(tx.date)}</td>
          <td class="address-col" title={formatAddress(tx)}>{formatAddress(tx)}</td>
          <td class="type-col">{formatPropertyType(tx.property_type)}</td>
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
  border: 1px solid var(--bouch-gray, rgba(28, 25, 23, 0.12));
}

.comps-table {
  width: 100%;
  border-collapse: collapse;
  font-family: 'Space Mono', monospace;
  font-size: 13px;
}

.comps-table th,
.comps-table td {
  padding: 12px 10px;
  text-align: left;
  border-bottom: 1px solid var(--bouch-gray, rgba(28, 25, 23, 0.12));
}

.comps-table th {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--bouch-mid-gray, #b0aea5);
  background: var(--bouch-charcoal, #1C1917);
  border-bottom: 2px solid var(--bouch-orange, #D97757);
  position: sticky;
  top: 0;
  z-index: 1;
}

.comps-table th.sortable {
  cursor: pointer;
  user-select: none;
  transition: all 0.15s ease;
}

.comps-table th.sortable:hover {
  color: var(--bouch-cream, #FAF9F5);
  background: #2d2926;
}

.comps-table th.sorted {
  color: var(--bouch-orange, #D97757);
}

.comps-table tbody tr {
  transition: all 0.15s ease;
  animation: fadeInRow 0.3s ease-out forwards;
  opacity: 0;
}

@keyframes fadeInRow {
  from {
    opacity: 0;
    transform: translateX(-10px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.comps-table tbody tr:hover {
  background: var(--bouch-gray, #e8e6dc);
}

.comps-table tbody tr:active {
  background: var(--bouch-mid-gray, #b0aea5);
}

.date-col {
  white-space: nowrap;
  color: var(--bouch-mid-gray, #b0aea5);
  font-size: 12px;
}

.address-col {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--bouch-charcoal, #1C1917);
}

.type-col {
  color: var(--bouch-mid-gray, #b0aea5);
  font-size: 12px;
}

.price-col {
  text-align: right;
  font-weight: 700;
  white-space: nowrap;
  color: var(--bouch-charcoal, #1C1917);
}

/* Responsive */
@media (max-width: 480px) {
  .comps-table th,
  .comps-table td {
    padding: 10px 6px;
    font-size: 11px;
  }

  .address-col {
    max-width: 120px;
  }
}
</style>
