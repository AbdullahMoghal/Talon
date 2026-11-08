/** Unwrap SpacetimeDB option values (`T | undefined` or `{ tag: 'some' | 'none' }`). */
export function unwrapOpt<T>(value: unknown): T | undefined {
  if (value == null) return undefined;
  if (typeof value === 'object' && value !== null && 'tag' in value) {
    const tagged = value as { tag: string; value?: T };
    return tagged.tag === 'some' ? tagged.value : undefined;
  }
  return value as T;
}
