<script lang="ts">
/**
 * Transaction table component for displaying property sales.
 */
import type { Transaction } from "../lib/types";
import { formatPrice, formatDate } from "../lib/formatters";

interface Props {
  transactions: Transaction[];
}

let { transactions }: Props = $props();

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
</script>

<div class="table-container">
  <table class="comps-table">
    <thead>
      <tr>
        <th>Date</th>
        <th>Address</th>
        <th>Type</th>
        <th class="price-col">Price</th>
      </tr>
    </thead>
    <tbody>
      {#each transactions as tx}
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
