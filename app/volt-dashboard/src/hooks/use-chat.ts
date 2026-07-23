import { useState, useCallback, useRef, useEffect } from 'react'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  provider?: string
  timestamp: number
}

interface ChatState {
  messages: ChatMessage[]
  loading: boolean
  error: string | null
  provider: string
}

const STORAGE_KEY = 'omni-studio-chat'

function loadHistory(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveHistory(messages: ChatMessage[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-100)))
  } catch {}
}

export function useChat() {
  const [state, setState] = useState<ChatState>({
    messages: loadHistory(),
    loading: false,
    error: null,
    provider: 'kimi',
  })
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    saveHistory(state.messages)
  }, [state.messages])

  const sendMessage = useCallback(async (content: string) => {
    if (!content.trim() || state.loading) return

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: content.trim(),
      timestamp: Date.now(),
    }

    setState((s) => ({
      ...s,
      messages: [...s.messages, userMsg],
      loading: true,
      error: null,
    }))

    abortRef.current = new AbortController()

    try {
      const body = new URLSearchParams({
        message: content.trim(),
        provider: state.provider,
      })

      const res = await fetch('/api/chat', {
        method: 'POST',
        body,
        signal: abortRef.current.signal,
      })

      if (!res.ok) throw new Error(`Chat API ${res.status}`)

      const data = await res.json()

      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: data.response || data.error || 'No response',
        provider: state.provider,
        timestamp: Date.now(),
      }

      setState((s) => ({
        ...s,
        messages: [...s.messages, assistantMsg],
        loading: false,
      }))
    } catch (err: any) {
      if (err.name === 'AbortError') return
      setState((s) => ({
        ...s,
        loading: false,
        error: err.message || 'Failed to get response',
      }))
    }
  }, [state.provider, state.loading])

  const setProvider = useCallback((provider: string) => {
    setState((s) => ({ ...s, provider }))
  }, [])

  const clearMessages = useCallback(() => {
    setState((s) => ({ ...s, messages: [], error: null }))
    localStorage.removeItem(STORAGE_KEY)
  }, [])

  const stopGeneration = useCallback(() => {
    abortRef.current?.abort()
    setState((s) => ({ ...s, loading: false }))
  }, [])

  return {
    messages: state.messages,
    loading: state.loading,
    error: state.error,
    provider: state.provider,
    sendMessage,
    setProvider,
    clearMessages,
    stopGeneration,
  }
}
