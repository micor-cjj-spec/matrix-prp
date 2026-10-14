/**
 * Clone the JSON-compatible health form payloads passed to our REST APIs.
 *
 * Vue refs unwrap to reactive Proxy objects. structuredClone(proxy) throws
 * DataCloneError in browsers, including iOS Safari. JSON serialization
 * intentionally produces a plain data transfer object (not a Vue Proxy).
 *
 * Use only for JSON data: no Dates, File/Blob, BigInt, undefined-valued
 * properties, cyclical references, or class instances.
 */
export function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
