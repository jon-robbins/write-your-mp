// Remembers Represent's answer per postal code for the life of the server. Every visitor's lookup
// leaves from this server, so they share OpenNorth's free limit of 60 requests a minute; repeat
// postal codes should not spend it. Entries never expire: a new deploy or Cloud Run instance starts
// empty, which is how a change of MP gets picked up. Memory is bounded by dropping the least
// recently used postal code once the cache is full.
export function createLookupCache({ maxEntries = 10_000 } = {}) {
  const entries = new Map();
  return {
    get(key) {
      if (!entries.has(key)) return undefined;
      const value = entries.get(key);
      entries.delete(key);
      entries.set(key, value); // re-insert so Map order tracks recent use
      return value;
    },
    set(key, value) {
      entries.delete(key);
      entries.set(key, value);
      if (entries.size > maxEntries) entries.delete(entries.keys().next().value);
    },
    get size() {
      return entries.size;
    },
  };
}
