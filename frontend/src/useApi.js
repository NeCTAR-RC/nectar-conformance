import { useEffect, useState } from 'react'
import { api } from './api.js'

// Fetch `path` and track loading/error/data. Refetches whenever `path` changes.
export function useApi(path) {
  const [state, setState] = useState({
    loading: true,
    data: null,
    error: null,
  })
  useEffect(() => {
    let live = true
    setState({ loading: true, data: null, error: null })
    api(path).then(
      (data) => live && setState({ loading: false, data, error: null }),
      (error) =>
        live && setState({ loading: false, data: null, error: error.message }),
    )
    return () => {
      live = false
    }
  }, [path])
  return state
}
