import React, { useEffect, useRef } from 'react'
import { Network } from 'vis-network'
import 'vis-network/styles/vis-network.min.css'

export default function PipelineGraph({ nodes, edges, onNodeClick }) {
  const containerRef = useRef(null)
  const networkRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current || nodes.length === 0) return

    const statusColors = {
      pending: '#6b7280',
      running: '#f59e0b',
      done: '#10b981',
      error: '#ef4444'
    }

    const visNodes = nodes.map(node => ({
      id: node.id,
      label: node.label,
      color: {
        background: statusColors[node.status] || statusColors.pending,
        border: statusColors[node.status] || statusColors.pending,
        highlight: {
          background: statusColors[node.status] || statusColors.pending,
          border: '#fff'
        }
      },
      font: { color: '#fff', size: 14, face: 'sans-serif' },
      shape: 'box',
      margin: 10,
      widthConstraint: { maximum: 150 },
      title: node.title || node.label,
      physics: false
    }))

    const visEdges = edges.map(edge => ({
      from: edge.from,
      to: edge.to,
      arrows: 'to',
      color: '#94a3b8',
      smooth: { type: 'cubicBezier' }
    }))

    const options = {
      physics: false,
      layout: {
        hierarchical: {
          enabled: true,
          levelSeparation: 150,
          nodeSpacing: 200,
          direction: 'LR',
          sortMethod: 'directed'
        }
      },
      interaction: {
        navigationButtons: true,
        keyboard: true
      }
    }

    const data = { nodes: visNodes, edges: visEdges }

    if (networkRef.current) {
      networkRef.current.destroy()
    }

    networkRef.current = new Network(containerRef.current, data, options)

    networkRef.current.on('click', (params) => {
      if (params.nodes.length > 0) {
        onNodeClick(params.nodes[0])
      }
    })

    return () => {
      if (networkRef.current) {
        networkRef.current.destroy()
        networkRef.current = null
      }
    }
  }, [nodes, edges, onNodeClick])

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        background: '#0a0f1b',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}
    >
      {nodes.length === 0 && (
        <div style={{ color: '#94a3b8', textAlign: 'center' }}>
          <p>Submit a query to see the pipeline graph</p>
        </div>
      )}
    </div>
  )
}
