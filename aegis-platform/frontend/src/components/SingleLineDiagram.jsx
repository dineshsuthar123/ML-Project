/**
 * AEGIS – Single Line Diagram
 * SVG microgrid topology with animated power flow arrows
 * updated in real time from WebSocket data.
 */

import { useEffect, useRef, useState } from 'react'
import { Box, Typography } from '@mui/material'

const NODES = [
  { id: 'residential_01', label: 'Residential', x: 80,  y: 200, color: '#42a5f5', icon: '🏠' },
  { id: 'commercial_01',  label: 'Commercial',  x: 320, y: 200, color: '#66bb6a', icon: '🏢' },
  { id: 'industrial_01',  label: 'Industrial',  x: 560, y: 200, color: '#ef5350', icon: '🏭' },
  { id: 'solar_01',       label: 'Solar PV',    x: 200, y: 60,  color: '#ffa726', icon: '☀️' },
  { id: 'battery_01',     label: 'Battery',     x: 440, y: 60,  color: '#ab47bc', icon: '🔋' },
  { id: 'grid_01',        label: 'Grid',        x: 320, y: 340, color: '#78909c', icon: '⚡' },
]

const EDGES = [
  { from: 'solar_01',   to: 'commercial_01' },
  { from: 'battery_01', to: 'commercial_01' },
  { from: 'grid_01',    to: 'commercial_01' },
  { from: 'commercial_01', to: 'residential_01' },
  { from: 'commercial_01', to: 'industrial_01' },
]

function getPos(id) {
  return NODES.find(n => n.id === id) || { x: 0, y: 0 }
}

export function SingleLineDiagram({ telemetry = {} }) {
  const [tick, setTick] = useState(0)

  // Animate flow arrows
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 400)
    return () => clearInterval(id)
  }, [])

  const nodeData = (id) => telemetry[id] || {}

  return (
    <Box>
      <Typography variant="h6" gutterBottom>Single-Line Diagram</Typography>
      <svg width="100%" viewBox="0 0 680 420" style={{ background: '#0d1117', borderRadius: 8 }}>
        {/* Edges with animated dashes */}
        {EDGES.map((e, i) => {
          const a = getPos(e.from)
          const b = getPos(e.to)
          const dashOffset = -(tick * 6) % 40
          return (
            <g key={i}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke="#4caf50" strokeWidth={2}
                strokeDasharray="12 8"
                strokeDashoffset={dashOffset}
                opacity={0.8}
              />
            </g>
          )
        })}

        {/* Nodes */}
        {NODES.map(node => {
          const d = nodeData(node.id)
          return (
            <g key={node.id} transform={`translate(${node.x},${node.y})`}>
              <circle r={32} fill={node.color} opacity={0.15} />
              <circle r={28} fill={node.color} opacity={0.35} stroke={node.color} strokeWidth={2} />
              <text textAnchor="middle" dominantBaseline="central" fontSize={20}>{node.icon}</text>
              <text y={46} textAnchor="middle" fill="#e0e0e0" fontSize={10} fontWeight="bold">
                {node.label}
              </text>
              {d.load_kw !== undefined && (
                <text y={58} textAnchor="middle" fill="#aaa" fontSize={9}>
                  {d.load_kw?.toFixed(0)} kW
                </text>
              )}
              {d.battery_soc !== undefined && (
                <text y={68} textAnchor="middle" fill="#ffd54f" fontSize={9}>
                  SoC {(d.battery_soc * 100).toFixed(0)}%
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </Box>
  )
}

