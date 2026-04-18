import React, { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Play, Trash2, RotateCcw, Menu } from 'lucide-react'
import api from './api'
import PipelineGraph from './components/PipelineGraph'
import DetailPanel from './components/DetailPanel'
import QueryInput from './components/QueryInput'
import HistoryPanel from './components/HistoryPanel'
import './App.css'

export default function App() {
  const [currentQueryId, setCurrentQueryId] = useState(null)
  const [queryResult, setQueryResult] = useState(null)
  const [status, setStatus] = useState('ready')
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] })
  const [openPanels, setOpenPanels] = useState({})
  const [systemStatus, setSystemStatus] = useState(null)
  const [showHistory, setShowHistory] = useState(false)
  const [error, setError] = useState(null)
  const wsRef = useRef(null)

  // Load initial status
  useEffect(() => {
    const loadStatus = async () => {
      try {
        const res = await api.status()
        setSystemStatus(res.data)
      } catch (err) {
        console.error('Failed to load status:', err)
      }
    }
    loadStatus()
    const interval = setInterval(loadStatus, 10000)
    return () => clearInterval(interval)
  }, [])

  // WebSocket connection for real-time updates
  useEffect(() => {
    if (!currentQueryId) return

    const ws = api.connectQueryStream(currentQueryId)
    wsRef.current = ws

    ws.onopen = () => {
      console.log(`Connected to query ${currentQueryId}`)
      setStatus('connected')
    }

    ws.onmessage = (event) => {
      const event_data = JSON.parse(event.data)
      console.log('Event:', event_data)
      handlePipelineEvent(event_data)
    }

    ws.onerror = (err) => {
      console.error('WebSocket error:', err)
      setError('Connection error')
    }

    ws.onclose = () => {
      console.log('WebSocket closed')
      setStatus('done')
    }

    return () => {
      if (wsRef.current) wsRef.current.close()
    }
  }, [currentQueryId])

  const handlePipelineEvent = (event) => {
    // Ignore ping/keep-alive messages
    if (event.type === 'ping' || !event.event_type) {
      console.debug('[Event] Ignoring non-pipeline event:', event.type)
      return
    }

    const { event_type, query_id, data, timestamp } = event
    console.log(`[Event] ${event_type}:`, event)

    // Update graph based on event
    setGraphData(prev => {
      const nodes = [...prev.nodes]
      const edges = [...prev.edges]

      const nodeMap = Object.fromEntries(nodes.map(n => [n.id, n]))

      switch (event_type) {
        case 'QUERY_STARTED':
          console.log('[Graph] Initializing pipeline graph')
          nodeMap['orchestrator'] = { 
            id: 'orchestrator', 
            label: 'Orchestrator', 
            status: 'running',
            title: data.query 
          }
          nodeMap['scrapers'] = { 
            id: 'scrapers', 
            label: 'Scrapers', 
            status: 'pending'
          }
          nodeMap['triage'] = { 
            id: 'triage', 
            label: 'Triage', 
            status: 'pending'
          }
          nodeMap['analysts'] = { 
            id: 'analysts', 
            label: 'Analysts', 
            status: 'pending'
          }
          nodeMap['synthesizer'] = { 
            id: 'synthesizer', 
            label: 'Synthesizer', 
            status: 'pending'
          }
          nodeMap['output'] = { 
            id: 'output', 
            label: 'Output', 
            status: 'pending'
          }
          
          console.log('[Graph] Nodes created:', Object.values(nodeMap).length)
          return { 
            nodes: Object.values(nodeMap),
            edges: [
              { from: 'orchestrator', to: 'scrapers' },
              { from: 'scrapers', to: 'triage' },
              { from: 'triage', to: 'analysts' },
              { from: 'analysts', to: 'synthesizer' },
              { from: 'synthesizer', to: 'output' }
            ]
          }
        case 'ORCHESTRATOR_DONE':
          if (nodeMap['orchestrator']) nodeMap['orchestrator'].status = 'done'
          if (nodeMap['scrapers']) nodeMap['scrapers'].status = 'running'
          break
        case 'SCRAPER_DONE':
          if (nodeMap['scrapers']) nodeMap['scrapers'].status = 'done'
          if (nodeMap['triage']) nodeMap['triage'].status = 'running'
          break
        case 'TRIAGE_DONE':
          if (nodeMap['triage']) nodeMap['triage'].status = 'done'
          if (nodeMap['analysts']) nodeMap['analysts'].status = 'running'
          break
        case 'ANALYST_DONE':
          if (nodeMap['analysts']) nodeMap['analysts'].status = 'done'
          if (nodeMap['synthesizer']) nodeMap['synthesizer'].status = 'running'
          break
        case 'SYNTHESIZER_DONE':
          if (nodeMap['synthesizer']) nodeMap['synthesizer'].status = 'done'
          if (nodeMap['output']) nodeMap['output'].status = 'running'
          break
        case 'QUERY_DONE':
          if (nodeMap['output']) nodeMap['output'].status = 'done'
          setQueryResult({
            query_id,
            answer: data.answer,
            confidence: data.confidence,
            profile: data.profile,
            duration_ms: data.duration_ms
          })
          setStatus('done')
          break
        case 'QUERY_ERROR':
          if (nodeMap['output']) nodeMap['output'].status = 'error'
          setError(data.error)
          setStatus('error')
          break
        default:
          console.warn('[Event] Unhandled event type:', event_type)
      }

      console.log('[Graph] Returning nodes:', Object.values(nodeMap).length)
      return { nodes: Object.values(nodeMap), edges }
    })
  }

  const handleSubmitQuery = async (query, focusArea) => {
    try {
      setError(null)
      setStatus('submitting')
      setOpenPanels({})
      
      const res = await api.submitQuery(query, focusArea)
      const queryId = res.data.query_id
      
      setCurrentQueryId(queryId)
      setStatus('running')
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to submit query')
      setStatus('error')
    }
  }

  const handleCancelQuery = async () => {
    if (!currentQueryId) return
    try {
      await api.cancelQuery(currentQueryId)
      setStatus('cancelled')
    } catch (err) {
      console.error('Failed to cancel:', err)
    }
  }

  const handleClearPanels = () => {
    setOpenPanels({})
  }

  const togglePanel = (panelId) => {
    setOpenPanels(prev => ({
      ...prev,
      [panelId]: !prev[panelId]
    }))
  }

  const handleNodeClick = async (nodeId) => {
    togglePanel(nodeId)
  }

  return (
    <div className="app-container">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <h1>⚗️ LLM Research Council</h1>
          <div className="status-badge" data-status={status}>
            ● {status}
          </div>
        </div>

        <div className="header-actions">
          <button 
            className="btn-history"
            onClick={() => setShowHistory(!showHistory)}
            title="View query history"
          >
            <Menu size={20} />
          </button>
          {currentQueryId && status === 'running' && (
            <button 
              className="btn-cancel"
              onClick={handleCancelQuery}
              title="Cancel query"
            >
              ✕ Cancel
            </button>
          )}
          {status === 'done' || status === 'error' ? (
            <button 
              className="btn-new"
              onClick={() => {
                setCurrentQueryId(null)
                setQueryResult(null)
                setStatus('ready')
                setGraphData({ nodes: [], edges: [] })
              }}
              title="Start new query"
            >
              <RotateCcw size={18} /> New
            </button>
          ) : null}
        </div>
      </header>

      {/* Main Content */}
      <div className="main-content">
        <div className="left-panel">
          {status === 'ready' ? (
            <QueryInput onSubmit={handleSubmitQuery} />
          ) : (
            <PipelineGraph 
              nodes={graphData.nodes} 
              edges={graphData.edges}
              onNodeClick={handleNodeClick}
            />
          )}
        </div>

        {/* Detail Panels */}
        <div className="panels-container">
          <AnimatePresence>
            {Object.entries(openPanels).map(([panelId, isOpen]) => isOpen && (
              <DetailPanel
                key={panelId}
                panelId={panelId}
                queryId={currentQueryId}
                onClose={() => togglePanel(panelId)}
              />
            ))}
          </AnimatePresence>

          {/* Query Result */}
          {queryResult && status === 'done' && (
            <motion.div
              className="result-panel"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="panel-header">
                <h3>Result</h3>
                <button 
                  className="btn-close"
                  onClick={() => setQueryResult(null)}
                >
                  <X size={18} />
                </button>
              </div>
              <div className="panel-content">
                <div className="result-confidence">
                  Confidence: <strong>{(queryResult.confidence * 100).toFixed(1)}%</strong>
                </div>
                <div className="result-text">
                  {queryResult.answer}
                </div>
                <div className="result-meta">
                  <small>Duration: {queryResult.duration_ms.toFixed(0)}ms</small>
                </div>
              </div>
            </motion.div>
          )}

          {/* Error Message */}
          {error && (
            <motion.div
              className="error-panel"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="panel-header">
                <h3>⚠️ Error</h3>
                <button 
                  className="btn-close"
                  onClick={() => setError(null)}
                >
                  <X size={18} />
                </button>
              </div>
              <div className="panel-content">
                <p>{error}</p>
              </div>
            </motion.div>
          )}
        </div>
      </div>

      {/* History Sidebar */}
      <AnimatePresence>
        {showHistory && (
          <HistoryPanel 
            onClose={() => setShowHistory(false)}
            onSelectQuery={(queryId) => {
              setCurrentQueryId(queryId)
              setShowHistory(false)
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
