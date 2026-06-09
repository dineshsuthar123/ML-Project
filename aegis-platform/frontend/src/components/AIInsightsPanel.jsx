/**
 * AEGIS AI Intelligence Panel
 * ────────────────────────────
 * Fetches /api/ai/insights every 10s and displays real AI-generated
 * energy insights, recommendations, KPI scores, and live metrics.
 */

import { useState, useEffect, useRef } from 'react'
import {
  Box, Typography, Chip, LinearProgress, Divider,
  Grid, Paper, Tooltip, IconButton, CircularProgress,
  Badge
} from '@mui/material'
import RefreshIcon from '@mui/icons-material/Refresh'

const SEVERITY_COLORS = {
  success: '#2ea043',
  warning: '#d29922',
  error:   '#da3633',
  info:    '#388bfd',
}
const SEVERITY_BG = {
  success: 'rgba(46,160,67,0.1)',
  warning: 'rgba(210,153,34,0.1)',
  error:   'rgba(218,54,51,0.1)',
  info:    'rgba(56,139,253,0.1)',
}

function KpiGauge({ label, value, max = 100, unit = '', color = '#42a5f5' }) {
  const pct = Math.min(100, (value / max) * 100)
  return (
    <Box sx={{ mb: 1.5 }}>
      <Box display="flex" justifyContent="space-between" mb={0.3}>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
        <Typography variant="caption" sx={{ color, fontWeight: 'bold' }}>
          {typeof value === 'number' ? value.toFixed(value < 10 ? 2 : 0) : value}{unit}
        </Typography>
      </Box>
      <LinearProgress variant="determinate" value={pct}
        sx={{
          height: 5, borderRadius: 3,
          bgcolor: '#1e2733',
          '& .MuiLinearProgress-bar': { bgcolor: color, borderRadius: 3 },
        }} />
    </Box>
  )
}

function InsightCard({ insight }) {
  const color = SEVERITY_COLORS[insight.severity] || '#888'
  const bg    = SEVERITY_BG[insight.severity]    || 'rgba(255,255,255,0.03)'
  return (
    <Box sx={{
      p: 1.5, mb: 1, borderRadius: 2,
      background: bg,
      border: `1px solid ${color}33`,
      transition: 'all 0.3s ease',
      '&:hover': { borderColor: color, transform: 'translateX(2px)' },
    }}>
      <Box display="flex" alignItems="center" gap={1} mb={0.5}>
        <Typography fontSize={16}>{insight.icon}</Typography>
        <Box flex={1}>
          <Typography variant="body2" fontWeight="bold" sx={{ color, lineHeight: 1.3 }}>
            {insight.title}
          </Typography>
          <Typography variant="caption" color="text.secondary">{insight.category}</Typography>
        </Box>
        <Chip label={insight.value} size="small"
          sx={{ fontSize: 10, height: 20, bgcolor: `${color}22`, color }} />
      </Box>
      <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>
        {insight.detail}
      </Typography>
      <Typography variant="caption" sx={{ color: '#7c8fa8', fontStyle: 'italic' }}>
        💡 {insight.recommendation}
      </Typography>
    </Box>
  )
}

function EfficiencyRing({ score, grade }) {
  const color = score >= 80 ? '#2ea043' : score >= 60 ? '#ffa726' : '#da3633'
  return (
    <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" p={1}>
      <Box position="relative" display="inline-flex">
        <CircularProgress variant="determinate" value={score} size={80}
          thickness={5}
          sx={{ color, '& .MuiCircularProgress-circle': { strokeLinecap: 'round' } }} />
        <CircularProgress variant="determinate" value={100} size={80}
          thickness={5}
          sx={{ color: '#1e2733', position: 'absolute', left: 0, top: 0 }} />
        <Box sx={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center' }}>
          <Box textAlign="center">
            <Typography variant="h6" sx={{ color, fontWeight: 'bold', lineHeight: 1 }}>{grade}</Typography>
            <Typography variant="caption" color="text.secondary">{score}</Typography>
          </Box>
        </Box>
      </Box>
      <Typography variant="caption" color="text.secondary" mt={0.5}>Efficiency</Typography>
    </Box>
  )
}

export function AIInsightsPanel() {
  const [insights,  setInsights]  = useState([])
  const [summary,   setSummary]   = useState(null)
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)
  const [lastUpdate, setLastUpdate] = useState(null)
  const [category,  setCategory]  = useState('all')
  const timerRef = useRef(null)

  const fetch_ = async () => {
    try {
      const r = await fetch('/api/ai/insights')
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      setInsights(data.insights || [])
      setSummary(data.summary || null)
      setLastUpdate(new Date())
      setError(null)
    } catch (e) {
      setError(e.message)
    }
    setLoading(false)
  }

  useEffect(() => {
    fetch_()
    timerRef.current = setInterval(fetch_, 10000)
    return () => clearInterval(timerRef.current)
  }, [])

  const categories = ['all', ...new Set(insights.map(i => i.category))]
  const filtered   = category === 'all' ? insights : insights.filter(i => i.category === category)
  const errorCount = insights.filter(i => i.severity === 'error').length
  const warnCount  = insights.filter(i => i.severity === 'warning').length

  return (
    <Box>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={1.5}>
        <Box display="flex" alignItems="center" gap={1}>
          <Typography fontSize={18}>🤖</Typography>
          <Typography variant="h6" fontWeight="bold">AEGIS AI Intelligence</Typography>
          {errorCount > 0 && (
            <Chip label={`${errorCount} Critical`} size="small" color="error" sx={{ fontSize: 10 }} />
          )}
          {warnCount > 0 && (
            <Chip label={`${warnCount} Warning`} size="small" color="warning" sx={{ fontSize: 10 }} />
          )}
        </Box>
        <Box display="flex" alignItems="center" gap={1}>
          {lastUpdate && (
            <Typography variant="caption" color="text.secondary">
              {lastUpdate.toLocaleTimeString()}
            </Typography>
          )}
          <Tooltip title="Refresh now">
            <IconButton size="small" onClick={fetch_} disabled={loading}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {loading && <LinearProgress sx={{ mb: 1, borderRadius: 2 }} />}
      {error && (
        <Typography variant="caption" color="error" display="block" mb={1}>
          ⚠️ {error} — retrying…
        </Typography>
      )}

      {summary && (
        <>
          {/* KPI Grid */}
          <Grid container spacing={1.5} mb={2}>
            <Grid item xs={6} sm={3}>
              <Paper sx={{ p: 1.5, textAlign: 'center', background: '#0d1117', border: '1px solid #1e2733' }}>
                <Typography variant="caption" color="text.secondary">Total Load</Typography>
                <Typography variant="h6" sx={{ color: '#ef5350', fontWeight: 'bold' }}>
                  {summary.total_load_kw} kW
                </Typography>
              </Paper>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Paper sx={{ p: 1.5, textAlign: 'center', background: '#0d1117', border: '1px solid #1e2733' }}>
                <Typography variant="caption" color="text.secondary">Solar Gen</Typography>
                <Typography variant="h6" sx={{ color: '#ffa726', fontWeight: 'bold' }}>
                  {summary.total_solar_kw} kW
                </Typography>
              </Paper>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Paper sx={{ p: 1.5, textAlign: 'center', background: '#0d1117', border: '1px solid #1e2733' }}>
                <Typography variant="caption" color="text.secondary">Battery SoC</Typography>
                <Typography variant="h6" sx={{ color: '#ab47bc', fontWeight: 'bold' }}>
                  {summary.battery_soc_pct}%
                </Typography>
              </Paper>
            </Grid>
            <Grid item xs={6} sm={3}>
              <Paper sx={{ p: 1.5, textAlign: 'center', background: '#0d1117', border: '1px solid #1e2733' }}>
                <Typography variant="caption" color="text.secondary">Price</Typography>
                <Typography variant="h6" sx={{ color: '#66bb6a', fontWeight: 'bold' }}>
                  ${summary.price_per_kwh?.toFixed(4)}/kWh
                </Typography>
              </Paper>
            </Grid>
          </Grid>

          {/* Gauges + Efficiency Ring */}
          <Grid container spacing={2} mb={2}>
            <Grid item xs={12} sm={8}>
              <Paper sx={{ p: 2, background: '#0d1117', border: '1px solid #1e2733' }}>
                <Typography variant="caption" color="text.secondary" mb={1} display="block">
                  Live System Metrics
                </Typography>
                <KpiGauge label="Renewable Share" value={summary.renewable_share_pct} max={100}
                  unit="%" color="#2ea043" />
                <KpiGauge label="Battery SoC" value={summary.battery_soc_pct} max={100}
                  unit="%" color="#ab47bc" />
                <KpiGauge label="Voltage Quality" value={Math.abs(summary.voltage_pu - 1.0) < 0.01 ? 100 : 80}
                  max={100} unit="" color="#42a5f5" />
                <KpiGauge label="CO₂ Avoided" value={summary.carbon_avoided_kg_h} max={80}
                  unit=" kg/h" color="#66bb6a" />
              </Paper>
            </Grid>
            <Grid item xs={12} sm={4}>
              <Paper sx={{
                p: 2, background: '#0d1117', border: '1px solid #1e2733',
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                height: '100%'
              }}>
                <EfficiencyRing
                  score={summary.efficiency_score}
                  grade={summary.efficiency_grade}
                />
                <Divider sx={{ my: 1, width: '100%' }} />
                <Typography variant="caption" color="text.secondary" textAlign="center">
                  V: {summary.voltage_pu} pu &nbsp;|&nbsp; f: {summary.frequency_hz} Hz
                </Typography>
              </Paper>
            </Grid>
          </Grid>
        </>
      )}

      {/* Category filter chips */}
      <Box display="flex" gap={0.5} flexWrap="wrap" mb={1.5}>
        {categories.map(c => (
          <Chip key={c} label={c} size="small"
            onClick={() => setCategory(c)}
            variant={category === c ? 'filled' : 'outlined'}
            sx={{ fontSize: 10, cursor: 'pointer',
              ...(category === c ? { bgcolor: '#1e3a5f', color: '#42a5f5' } : {}) }}
          />
        ))}
      </Box>

      {/* Insight cards */}
      <Box sx={{ maxHeight: 480, overflowY: 'auto', pr: 0.5,
        '&::-webkit-scrollbar': { width: 4 },
        '&::-webkit-scrollbar-thumb': { bgcolor: '#30363d', borderRadius: 2 } }}>
        {filtered.length === 0
          ? <Typography variant="caption" color="text.secondary">No insights in this category.</Typography>
          : filtered.map(ins => <InsightCard key={ins.id} insight={ins} />)
        }
      </Box>
    </Box>
  )
}

