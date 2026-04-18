import React, { useState } from 'react'
import { Play } from 'lucide-react'
import './QueryInput.css'

export default function QueryInput({ onSubmit }) {
  const [query, setQuery] = useState('')
  const [focusArea, setFocusArea] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!query.trim()) return

    setIsSubmitting(true)
    try {
      await onSubmit(query, focusArea)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="query-input-container">
      <div className="query-input-header">
        <h2>Research Query</h2>
        <p className="subtitle">Enter your research question to begin</p>
      </div>

      <form onSubmit={handleSubmit} className="query-form">
        <div className="form-group">
          <label htmlFor="query">Query *</label>
          <textarea
            id="query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="E.g., What are the latest advancements in quantum computing?"
            rows={4}
            disabled={isSubmitting}
            required
            maxLength={2000}
          />
          <small>{query.length}/2000 characters</small>
        </div>

        <div className="form-group">
          <label htmlFor="focusArea">Focus Area (optional)</label>
          <input
            id="focusArea"
            type="text"
            value={focusArea}
            onChange={(e) => setFocusArea(e.target.value)}
            placeholder="E.g., recent breakthroughs, applications"
            disabled={isSubmitting}
            maxLength={200}
          />
        </div>

        <button 
          type="submit" 
          className="btn-submit"
          disabled={isSubmitting || !query.trim()}
        >
          <Play size={18} />
          {isSubmitting ? 'Submitting...' : 'Run Query'}
        </button>
      </form>

      <div className="info-section">
        <h3>How it works</h3>
        <ul>
          <li>📋 <strong>Orchestrator:</strong> Plans the research strategy</li>
          <li>🔍 <strong>Scrapers:</strong> Gather information from multiple sources</li>
          <li>🎯 <strong>Triage:</strong> Filters irrelevant information</li>
          <li>🧠 <strong>Analysts:</strong> Examines and extracts findings</li>
          <li>🔗 <strong>Synthesizer:</strong> Combines into final answer</li>
        </ul>
      </div>
    </div>
  )
}
