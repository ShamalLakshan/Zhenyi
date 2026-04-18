import React, { useState, useEffect } from 'react'
import { motion, Reorder } from 'framer-motion'
import { X, Copy, Download } from 'lucide-react'
import api from '../api'
import './DetailPanel.css'

const panelTitles = {
  orchestrator: 'Orchestrator Plan',
  scrapers: 'Scraper Results',
  triage: 'Triage Summary',
  analysts: 'Analyst Findings',
  synthesizer: 'Synthesizer Result'
}

export default function DetailPanel({ panelId, queryId, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)
  const [position, setPosition] = useState({ x: 50 + Math.random() * 100, y: 50 + Math.random() * 100 })
  const [isDragging, setIsDragging] = useState(false)
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 })

  useEffect(() => {
    loadPanelData()
  }, [panelId, queryId])

  const loadPanelData = async () => {
    try {
      setLoading(true)
      setError(null)
      console.log(`[Panel] Loading data for ${panelId}`)
      
      if (panelId === 'output') {
        const queryData = await api.getQuery(queryId)
        console.log(`[Panel] Got output data for ${queryId}:`, queryData.data)
        setData(queryData.data)
      } else {
        const debugData = await api.getDebug(queryId, panelId)
        console.log(`[Panel] Got debug data for ${panelId}:`, debugData.data)
        // Extract the data field from the response
        setData(debugData.data?.data || debugData.data || debugData)
      }
    } catch (err) {
      console.error(`[Panel] Error loading ${panelId}:`, err)
      setError(err.response?.data?.detail || err.message || 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  const copyToClipboard = () => {
    const text = JSON.stringify(data, null, 2)
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleMouseDown = (e) => {
    setIsDragging(true)
    setDragOffset({
      x: e.clientX - position.x,
      y: e.clientY - position.y
    })
  }

  const handleMouseMove = (e) => {
    if (isDragging) {
      setPosition({
        x: e.clientX - dragOffset.x,
        y: e.clientY - dragOffset.y
      })
    }
  }

  const handleMouseUp = () => {
    setIsDragging(false)
  }

  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
      return () => {
        window.removeEventListener('mousemove', handleMouseMove)
        window.removeEventListener('mouseup', handleMouseUp)
      }
    }
  }, [isDragging, dragOffset])

  return (
    <motion.div
      className="detail-panel"
      style={{
        position: 'absolute',
        left: `${position.x}px`,
        top: `${position.y}px`,
        minWidth: '350px',
        maxWidth: '500px'
      }}
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
    >
      <div 
        className="panel-header"
        onMouseDown={handleMouseDown}
        style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
      >
        <h3>{panelTitles[panelId] || panelId}</h3>
        <div className="header-actions">
          <button 
            onClick={copyToClipboard}
            title="Copy JSON"
            className="btn-copy"
          >
            <Copy size={16} />
          </button>
          <button 
            onClick={onClose}
            title="Close"
            className="btn-close"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      <div className="panel-content">
        {loading ? (
          <div className="loading">Loading...</div>
        ) : error ? (
          <div className="error">{error}</div>
        ) : data ? (
          <div className="data-display">
            {typeof data === 'object' ? (
              <pre>{JSON.stringify(data, null, 2)}</pre>
            ) : (
              <p>{String(data)}</p>
            )}
          </div>
        ) : (
          <div className="empty">No data available</div>
        )}
      </div>

      {copied && (
        <div className="copy-notification">✓ Copied to clipboard</div>
      )}
    </motion.div>
  )
}
