/**
 * AEGIS – useWebSocket Hook
 * Connects to the API Gateway WebSocket and routes messages
 * to subscribers by topic.
 */

import { useEffect, useRef, useState, useCallback } from 'react'

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/live-telemetry'

export function useWebSocket() {
  const ws            = useRef(null)
  const [connected, setConnected]   = useState(false)
  const [lastMessage, setLastMessage] = useState(null)
  const subscribers   = useRef({})   // topic → [callback, ...]
  const reconnectTimer = useRef(null)

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return

    ws.current = new WebSocket(WS_URL)

    ws.current.onopen = () => {
      setConnected(true)
      console.log('[AEGIS WS] Connected')
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current)
        reconnectTimer.current = null
      }
    }

    ws.current.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        setLastMessage(msg)
        const topic = msg.topic || 'unknown'
        const cbs   = subscribers.current[topic] || []
        cbs.forEach(cb => cb(msg.payload, msg))
      } catch (_) {}
    }

    ws.current.onerror = (err) => {
      console.warn('[AEGIS WS] Error', err)
    }

    ws.current.onclose = () => {
      setConnected(false)
      console.log('[AEGIS WS] Disconnected. Reconnecting in 3s ...')
      reconnectTimer.current = setTimeout(connect, 3000)
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (ws.current) ws.current.close()
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
    }
  }, [connect])

  /**
   * Subscribe to a specific Kafka topic stream.
   * @param {string} topic  – e.g. 'sensor.features'
   * @param {function} callback – (payload, envelope) => void
   * @returns {function} unsubscribe
   */
  const subscribe = useCallback((topic, callback) => {
    if (!subscribers.current[topic]) subscribers.current[topic] = []
    subscribers.current[topic].push(callback)
    return () => {
      subscribers.current[topic] = subscribers.current[topic].filter(cb => cb !== callback)
    }
  }, [])

  return { connected, lastMessage, subscribe }
}

