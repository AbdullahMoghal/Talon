// Server-side reads from SpacetimeDB's HTTP SQL endpoint.
// Phase 1 polls through this; Phase 2 swaps in live subscriptions with the
// SpacetimeDB TypeScript SDK and bindings from `spacetime generate`.

type SqlElement = { name?: string | { some?: string } };
type SqlResult = { schema: { elements: SqlElement[] }; rows: unknown[][] };

const base = () => {
  const url = process.env.SPACETIME_URL;
  const db = process.env.SPACETIME_DB ?? "talon";
  return url ? `${url.replace(/\/$/, "")}/v1/database/${db}` : null;
};

export const spacetimeConfigured = () => base() !== null;

function columnName(el: SqlElement, i: number): string {
  const n = typeof el.name === "object" ? el.name?.some : el.name;
  return n ?? `col${i}`;
}

export async function sql<T>(query: string): Promise<T[]> {
  const root = base();
  if (!root) throw new Error("SPACETIME_URL is not set");
  const headers: Record<string, string> = { "Content-Type": "text/plain" };
  if (process.env.SPACETIME_TOKEN) headers.Authorization = `Bearer ${process.env.SPACETIME_TOKEN}`;
  const res = await fetch(`${root}/sql`, { method: "POST", body: query, headers, cache: "no-store" });
  if (!res.ok) throw new Error(`SpacetimeDB sql ${res.status}: ${await res.text()}`);
  const [first] = (await res.json()) as SqlResult[];
  if (!first) return [];
  const names = first.schema.elements.map(columnName);
  return first.rows.map((row) => Object.fromEntries(names.map((n, i) => [n, row[i]])) as T);
}
