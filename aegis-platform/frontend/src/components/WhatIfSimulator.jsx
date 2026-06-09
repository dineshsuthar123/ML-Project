/**
 * AEGIS – What-If Simulator v2
 * Uses /api/dashboard/simulate (physics-based, always works)
 */
import { useState } from "react"
import {
  Box, Typography, Slider, Button, Alert,
  Grid, CircularProgress, Chip, Paper, Divider
} from "@mui/material"
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer
} from "recharts"
const PARAMS = [
  { key:"temperature",   label:"Temperature",   unit:"°C",    min:-10, max:45,  step:0.5,  default:25  },
  { key:"irradiance",    label:"Irradiance",    unit:"W/m²",  min:0,   max:1000,step:10,   default:500 },
  { key:"solar_kw",      label:"Solar PV Cap.", unit:"kW",    min:0,   max:150, step:5,    default:80  },
  { key:"battery_soc",   label:"Battery SoC",   unit:"",      min:0.1, max:0.95,step:0.01, default:0.5 },
  { key:"price_per_kwh", label:"Energy Price",  unit:"$/kWh", min:0.02,max:0.25,step:0.005,default:0.08},
  { key:"hour",          label:"Start Hour",    unit:":00",   min:0,   max:23,  step:1,    default:12  },
  { key:"humidity",      label:"Humidity",      unit:"%",     min:10,  max:100, step:1,    default:60  },
  { key:"wind_speed",    label:"Wind Speed",    unit:"km/h",  min:0,   max:80,  step:1,    default:8   },
]
const NODES = [
  { v:"commercial_01", l:"Commercial" },
  { v:"residential_01",l:"Residential"},
  { v:"industrial_01", l:"Industrial" },
]
const SEV_COLOR = { success:"#22c55e", warning:"#f59e0b", error:"#ef4444", ok:"#00d4ff" }
export function WhatIfSimulator() {
  const init = Object.fromEntries(PARAMS.map(p => [p.key, p.default]))
  const [vals,    setVals]    = useState({ ...init, month:6, day_of_week:0, is_weekend:0, node_id:"commercial_01" })
  const [result,  setResult]  = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)
  const simulate = async () => {
    setLoading(true); setError(null)
    try {
      const r = await fetch("/api/dashboard/simulate", {
        method:"POST",
        headers:{ "Content-Type":"application/json" },
        body: JSON.stringify(vals),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setResult(await r.json())
    } catch(e) { setError(e.message) }
    setLoading(false)
  }
  const chartData = result ? result.q50.map((v,i) => ({
    h: `${String((vals.hour + i) % 24).padStart(2,"0")}:00`,
    "Load (kW)": v,
    "Solar (kW)": result.solar_profile[i],
    "Net Grid (kW)": result.net_grid_kw[i],
    "Batt SoC (%)": result.battery_soc_profile[i],
    q10: result.q10[i], q90: result.q90[i],
  })) : []
  return (
    <Box>
      <Box display="flex" alignItems="center" gap={1} mb={2}>
        <Typography variant="h6" fontWeight={700}>🔮 What-If Simulator</Typography>
        <Chip label="AEGIS Physics Engine v2" size="small" sx={{ fontSize:9, background:"#a855f722", color:"#a855f7" }} />
        <Chip label="+ RL Dispatch" size="small" sx={{ fontSize:9, background:"#00d4ff22", color:"#00d4ff" }} />
      </Box>
      <Grid container spacing={2}>
        {/* Sliders */}
        <Grid item xs={12} md={5}>
          <Paper sx={{ p:2, background:"#0a1019", border:"1px solid #1a2535", borderRadius:2 }}>
            <Typography variant="caption" sx={{ color:"#475569", textTransform:"uppercase", fontSize:9, fontWeight:700, mb:1, display:"block" }}>
              Scenario Parameters
            </Typography>
            <Box mb={1.5}>
              <Typography variant="caption" sx={{ color:"#8b9ab0", fontSize:10 }}>Node:</Typography>
              <Box display="flex" gap={0.5} mt={0.3}>
                {NODES.map(n => (
                  <Chip key={n.v} label={n.l} size="small" onClick={() => setVals(p => ({ ...p, node_id:n.v }))}
                    sx={{ fontSize:9, cursor:"pointer",
                      background: vals.node_id===n.v ? "#00d4ff22" : "#1a2535",
                      color: vals.node_id===n.v ? "#00d4ff" : "#6b7a8d",
                      border: vals.node_id===n.v ? "1px solid #00d4ff44" : "1px solid #1a2535",
                    }} />
                ))}
              </Box>
            </Box>
            {PARAMS.map(p => (
              <Box key={p.key} mb={1.2}>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="caption" sx={{ color:"#8b9ab0", fontSize:10 }}>{p.label}</Typography>
                  <Typography variant="caption" sx={{ color:"#00d4ff", fontWeight:700, fontSize:10 }}>
                    {p.key === "battery_soc" ? `${Math.round(vals[p.key]*100)}%` : `${vals[p.key]}${p.unit}`}
                  </Typography>
                </Box>
                <Slider size="small" min={p.min} max={p.max} step={p.step} value={vals[p.key]}
                  onChange={(_,v) => setVals(prev => ({ ...prev, [p.key]:v }))}
                  sx={{ color:"#00d4ff", py:0.5,
                    "& .MuiSlider-rail": { background:"#1a2535" },
                    "& .MuiSlider-thumb": { width:12, height:12 },
                  }} />
              </Box>
            ))}
            <Box display="flex" gap={1} mt={1}>
              <Chip label={vals.is_weekend ? "Weekend" : "Weekday"} size="small"
                onClick={() => setVals(p => ({ ...p, is_weekend: p.is_weekend ? 0 : 1 }))}
                sx={{ fontSize:9, cursor:"pointer",
                  background: vals.is_weekend ? "#f59e0b22" : "#1a2535",
                  color: vals.is_weekend ? "#f59e0b" : "#6b7a8d" }} />
              {[1,3,6,9,12].map(m => (
                <Chip key={m} label={`M${m}`} size="small"
                  onClick={() => setVals(p => ({ ...p, month:m }))}
                  sx={{ fontSize:8, cursor:"pointer", minWidth:28,
                    background: vals.month===m ? "#a855f722" : "#1a2535",
                    color: vals.month===m ? "#a855f7" : "#6b7a8d" }} />
              ))}
            </Box>
            <Button fullWidth variant="contained" onClick={simulate} disabled={loading} sx={{ mt:2,
              background:"linear-gradient(135deg, #6366f1, #a855f7)",
              fontWeight:700, fontSize:12,
              "&:hover": { background:"linear-gradient(135deg, #4f46e5, #9333ea)" }
            }}>
              {loading ? <><CircularProgress size={14} sx={{ mr:1 }} />Simulating...</> : "⚡ Run Simulation"}
            </Button>
          </Paper>
        </Grid>
        {/* Results */}
        <Grid item xs={12} md={7}>
          {error && <Alert severity="error" sx={{ mb:1 }}>{error}</Alert>}
          {!result && !loading && (
            <Paper sx={{ p:4, background:"#0a1019", border:"1px solid #1a2535", borderRadius:2,
              display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", minHeight:300 }}>
              <Typography fontSize={40}>🔮</Typography>
              <Typography variant="body2" sx={{ color:"#475569", mt:1 }}>
                Adjust parameters and click Run Simulation
              </Typography>
              <Typography variant="caption" sx={{ color:"#374151", mt:0.5 }}>
                Physics engine + RL dispatch will compute 24-hour grid forecast
              </Typography>
            </Paper>
          )}
          {loading && (
            <Paper sx={{ p:4, background:"#0a1019", border:"1px solid #1a2535", borderRadius:2,
              display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", minHeight:300 }}>
              <CircularProgress sx={{ color:"#a855f7" }} />
              <Typography variant="caption" sx={{ color:"#6b7a8d", mt:2 }}>Running AEGIS Physics Engine...</Typography>
            </Paper>
          )}
          {result && !loading && (
            <Box display="flex" flexDirection="column" gap={1.5}>
              {/* Summary KPIs */}
              <Grid container spacing={1}>
                {[
                  { l:"Peak Load",    v:`${result.summary.peak_load_kw} kW`,  c:"#ef4444" },
                  { l:"Avg Load",     v:`${result.summary.avg_load_kw} kW`,   c:"#f59e0b" },
                  { l:"Peak Solar",   v:`${result.summary.peak_solar_kw} kW`, c:"#fbbf24" },
                  { l:"Cost Savings", v:`$${result.summary.total_savings}`,   c:"#22c55e" },
                  { l:"CO₂ Saved",    v:`${result.summary.carbon_saved_kg} kg/h`, c:"#10b981" },
                  { l:"RL Arbitrage", v:`$${result.summary.rl_arbitrage_usd}`,c:"#a855f7" },
                ].map(m => (
                  <Grid item xs={4} sm={2} key={m.l}>
                    <Paper sx={{ p:1, background:"#0a1019", border:`1px solid ${m.c}22`, borderRadius:1.5, textAlign:"center" }}>
                      <Typography variant="caption" sx={{ color:"#6b7a8d", fontSize:8, display:"block" }}>{m.l}</Typography>
                      <Typography variant="caption" sx={{ color:m.c, fontWeight:700, fontSize:11 }}>{m.v}</Typography>
                    </Paper>
                  </Grid>
                ))}
              </Grid>
              {/* Chart */}
              <Paper sx={{ p:1.5, background:"#0a1019", border:"1px solid #1a2535", borderRadius:2 }}>
                <ResponsiveContainer width="100%" height={220}>
                  <ComposedChart data={chartData} margin={{ top:5, right:10, bottom:0, left:0 }}>
                    <defs>
                      <linearGradient id="simLoadGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#ef4444" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1a2535" />
                    <XAxis dataKey="h" tick={{ fill:"#475569", fontSize:9 }} interval={3} />
                    <YAxis tick={{ fill:"#475569", fontSize:9 }} width={40} />
                    <Tooltip contentStyle={{ background:"#0d1520", border:"1px solid #1a2535", fontSize:10 }} />
                    <Legend wrapperStyle={{ fontSize:10, color:"#6b7a8d" }} />
                    <Area dataKey="q90" stroke="none" fill="#ef4444" fillOpacity={0.08} legendType="none" />
                    <Area dataKey="q10" stroke="none" fill="#0a1019" fillOpacity={1} legendType="none" />
                    <Area dataKey="Load (kW)" stroke="#ef4444" fill="url(#simLoadGrad)" strokeWidth={2} dot={false} />
                    <Line dataKey="Solar (kW)" stroke="#fbbf24" strokeWidth={2} dot={false} />
                    <Line dataKey="Net Grid (kW)" stroke="#00d4ff" strokeWidth={1.5} strokeDasharray="4 2" dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </Paper>
              {/* AI Recommendations */}
              <Paper sx={{ p:1.5, background:"#0a1019", border:"1px solid #1a2535", borderRadius:2 }}>
                <Typography variant="caption" sx={{ color:"#a855f7", fontWeight:700, fontSize:10, textTransform:"uppercase", display:"block", mb:1 }}>
                  🤖 AEGIS AI Recommendations
                </Typography>
                {result.recommendations.map((r,i) => (
                  <Box key={i} display="flex" alignItems="flex-start" gap={1} mb={0.8}
                    sx={{ p:0.8, borderRadius:1, background:`${SEV_COLOR[r.severity]||"#00d4ff"}0d`, border:`1px solid ${SEV_COLOR[r.severity]||"#00d4ff"}22` }}>
                    <Typography sx={{ fontSize:12, mt:"1px" }}>
                      {r.severity==="success"?"✅":r.severity==="warning"?"⚠️":r.severity==="error"?"🚨":"💡"}
                    </Typography>
                    <Typography variant="caption" sx={{ color: SEV_COLOR[r.severity]||"#00d4ff", fontSize:10 }}>{r.msg}</Typography>
                  </Box>
                ))}
                <Typography variant="caption" sx={{ color:"#374151", fontSize:9 }}>
                  Model: {result.model_version}
                </Typography>
              </Paper>
            </Box>
          )}
        </Grid>
      </Grid>
    </Box>
  )
}