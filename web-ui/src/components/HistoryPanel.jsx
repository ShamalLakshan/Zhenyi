import React, { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { X, Trash2 } from 'lucide-react'
import api from '../api'
import './HistoryPanel.css'

export default function HistoryPanel({ onClose, onSelectQuery }) {
  const [queries, setQueries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadHistory()
  }, [])

  const loadHistory = async () => {
    try {
      setLoading(true)
      setError(null)
      const res = await api.getHistory(100)
      setQueries(res.data.queries || [])
    } catch (err) {
      setError('Failed to load history')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (queryId, e) => {
    e.stopPropagation()
    if (confirm('Delete this query and all its logs?')) {
      try {
        await api.deleteQuery(queryId)
        setQueries(queries.filter(q => q.query_id !== queryId))
      } catch (err) {
        console.error('Failed to delete:', err)
      }
    }
  }

  const formatDate = (timestamp) => {
    const date = new Date(timestamp * 1000)
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  return (
    <motion.div
      className="history-sidebar"
      initial={{ x: '100%' }}
      animate={{ x: 0 }}
      exit={{ x: '100%' }}
      transition={{ duration: 0.3 }}
    >
      <div className="history-header">
        <h2>Query History</h2>
        <button 
          onClick={onClose}
          className="btn-close"
          title="Close history"
        >
          <X size={20} />
        </button>
      </div>

      <div className="history-list">
        {loading ? (
          <div className="history-loading">Loading...</div>
        ) : error ? (
          <div className="history-error">{error}</div>
        ) : queries.length === 0 ? (
          <div className="history-empty">No queries yet</div>
        ) : (
          queries.map(query => (
            <motion.div
              key={query.query_id}
              className="history-item"
              onClick={() => onSelectQuery(query.query_id)}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <div className="item-header">
                <span className="query-id">{query.query_id}</span>
                <button
                  className="btn-delete"
                  onClick={(e) => handleDelete(query.query_id, e)}
                  title="Delete"
                >
                  <Trash2 size={14} />
                </button>
              </div>
              <p className="query-text">{query.query_text}</p>
              <div className="item-meta">
                <span className="profile">{query.profile}</span>
                <span className="confidence">
                  {(query.confidence * 100).toFixed(0)}%
                </span>
              </div>
              <small>{formatDate(query.created_at)}</small>
            </motion.div>
          ))
        )}
      </div>

      <button 
        className="btn-refresh"
        onClick={loadHistory}
        disabled={loading}
      >
        ↻ Refresh
      </button>
    </motion.div>
  )
}
