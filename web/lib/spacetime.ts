import { DbConnection } from '@/src/module_bindings';

const TOKEN_KEY = 'talon_spacetimedb_token';

function readToken(): string | undefined {
  if (typeof window === 'undefined') return undefined;
  return localStorage.getItem(TOKEN_KEY) ?? undefined;
}

function persistToken(token: string | undefined) {
  if (typeof window === 'undefined' || !token) return;
  localStorage.setItem(TOKEN_KEY, token);
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

  return DbConnection.builder()
    .withUri(uri)
    .withDatabaseName(database)
    .withToken(readToken())
    .onConnect((_conn, _identity, token) => {
      persistToken(token);
    })
    .onAutomaticReconnect((_conn, _identity, token) => {
      persistToken(token);
    })
    .onConnectError((_ctx, error) => {
      console.error('[spacetime] connect error', error);
    });
}
