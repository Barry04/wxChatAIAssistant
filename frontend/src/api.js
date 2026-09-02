async function api(path, options = {}) {
  const response = await fetch(path, options)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload = await response.json()
      message = payload.detail || message
    } catch {
      // Keep the HTTP fallback when a response is not JSON.
    }
    throw new Error(message)
  }
  return response.json()
}

export { api }
