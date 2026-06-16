// Thin fetch wrapper over the read-only JSON API. All calls are GETs under /api.
export async function api(path) {
  const resp = await fetch(`/api${path}`)
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error(body.detail || `${resp.status} ${resp.statusText}`)
  }
  return resp.json()
}
