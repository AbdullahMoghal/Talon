import { DbConnection } from '@/src/module_bindings';

// One token per server + database. Each SpacetimeDB server issues its own tokens, so a token saved
// while pointed at a local database is rejected by Maincloud (the page then hangs on "Connecting").
function tokenKey(uri: string, database: string): string {
  return `talon_spacetimedb_token:${uri}|${database}`;
}

function readToken(key: string): string | undefined {
  if (typeof window === 'undefined') return undefined;
  return localStorage.getItem(key) ?? undefined;
}

function persistToken(key: string, token: string | undefined) {
  if (typeof window === 'undefined' || !token) return;
  localStorage.setItem(key, token);
}

function clearToken(key: string) {
  if (typeof window !== 'undefined') localStorage.removeItem(key);
}

/** Connection builder pointed at Maincloud prod (`talon-prod`). */
export function createSpacetimeConnectionBuilder() {
  const uri = process.env.NEXT_PUBLIC_SPACETIMEDB_URI;
  const database = process.env.NEXT_PUBLIC_SPACETIMEDB_DB;

  if (!uri || !database) {
    throw new Error(
      'Missing NEXT_PUBLIC_SPACETIMEDB_URI or NEXT_PUBLIC_SPACETIMEDB_DB'
    );
  }

  const key = tokenKey(uri, database);
  return DbConnection.builder()
    .withUri(uri)
    .withDatabaseName(database)
    .withToken(readToken(key))
    .onConnect((_conn, _identity, token) => {
      persistToken(key, token);
    })
    .onAutomaticReconnect((_conn, _identity, token) => {
      persistToken(key, token);
    })
    .onConnectError((_ctx, error) => {
      // A rejected token would fail on every reload; drop it so the next load gets a fresh identity.
      clearToken(key);
      console.error('[spacetime] connect error', error);
    });
}
