/**
 * AEGIS – Multi-Series Forecast & History Chart
 * Fetches from /api/dashboard/multifield — real DB data, no fake timestamps.
 * Shows load, solar, battery SoC + AI 6h extrapolation.
 */
import {
  ComposedChart, Area, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine
} from "recharts"
import { Box, Typography, Select, MenuItem, FormControl,
  InputLabel, Chip, ToggleButton, ToggleButtonGroup } from "@mui/material"
import { useState, useEffect } from "react"
const NODES = [
  { value:"residential_01", label:"Residential" },
  { value:"commercial_01",  label:"Commercial"  },
  { value:"industrial_01",  label:"Industrial"  },
]
const WINDOWS = [
  { v:6,  l:"6 h"  },
  { v:12, l:"12 h" },
  { v:24, l:"24 h" },
  { v:48, l:"48 h" },
]
function fmtTime(iso) {
  try {
    const d = new Date(iso)
    return `${String(d.getMonth()+1).padStart(2,"0")}/${String(d.getDate()).padStart(2,"0")} ${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`
  } catch { return iso }
}
export function ForecastChart({ nodeId = "commercial_01" }) {
  const [node,    setNode]    = useState(nodeId)
  const [hours,   setHours]   = useState(24)
  const [series,  setSeries]  = useState("load")
  const [data,    setData]    = useState([])
  const [loading, setLoading] = useState(false)
  const fetchData = async () => {
    setLoading(true)
    try {
      const r = await fetch(`/api/dashboard/multifield?node_id=${node}&hours=${hours}`)
      if (!r.ok) throw new Error("fetch failed")
      const rows = await r.json()
      if (rows.length === 0) { setData([]); setLoading(false); return }
      const formatted = rows.map(row => ({
        label:       fmtTime(row.time),
        load_kw:     row.load_kw,
        solar_kw:    row.solar_kw,
        battery_soc: row.battery_soc,
        voltage_pu:  row.voltage_pu,
        freq_hz:     row.frequency_hz,
        price_cents: parseFloat((row.price_per_kwh * 100).toFixed(3)),
      }))
      // AI extrapolation: 6 future points using linear regression on last 12 pts
      const key = series === "solar" ? "solar_kw" : series === "battery" ? "battery_soc" : "load_kw"
      const last = formatted.slice(-12).map(r => r[key])
      const n = last.length
      if (n >= 2) {
        const xm = (n-1)/2
        const ym = last.reduce((a,b)=>a+b,0)/n
        const slope = last.reduce((s,v,i)=>s+(i-xm)*(v-ym),0) / (last.reduce((s,_,i)=>s+(i-xm)**2,0)||1)
        const base  = last[n-1]
        for (let h = 1; h <= 6; h++) {
          const proj = Math.max(0, parseFloat((base + slope*h).toFixed(2)))
          const noise = proj * 0.04
          formatted.push({
            label:    `+${h*10}m`,
            forecast: proj,
            q10:      parseFloat((proj - noise*2).toFixed(2)),
            q90:      parseFloat((proj + noise*2).toFixed(2)),
            _future:  true,
          })
        }
      }
      setData(formatted)
    } catch (e) {
      console.warn("ForecastChart error", e)
      setData([])
    }
    setLoading(false)
  }
  useEffect(() => { fetchData() }, [node, hours, series])
  useEffect(() => { const t = setInterval(fetchData, 30000); return () => clearInterval(t) }, [node, hours, series])
  const splitIdx = data.findIndex(d => d._future)
  const seriesCfg = {
    load:    { key:"load_kw",     color:"#ef4444", unit:"kW",   label:"Load (kW)" },
    solar:   { key:"solar_kw",    color:"#f59e0b", unit:"kW",   label:"Solar (kW)" },
    battery: { key:"battery_soc", color:"#a855f7", unit:"%",    label:"Battery SoC (%)" },
    price:   { key:"price_cents", color:"#22c55e", unit:"¢/kWh",label:"Price (¢/kWh)" },
  }
  const cfg = seriesCfg[series]
  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={1.5} flexWrap="wrap" gap={1}>
        <Box display="flex" alignItems="center" gap={1}>
          <Typography variant="h6" sx={{ fontWeight:700, fontSize:15 }}>Load Forecast & History</Typography>
          <Chip label="AI Trend Extrapolation" size="small" color="primary" variant="outlined" sx={{ fontSize:9 }} />
          <Chip label={`${data.length} data pts`} size="small" sx={{ fontSize:9, background:"#1a2535", color:"#8b9ab0" }} />
        </Box>
        <Box display="flex" gap={1} flexWrap="wrap">
          <ToggleButtonGroup value={series} exclusive onChange={(_,v)=>v&&setSeries(v)} size="small"
            sx={{ "& .MuiToggleButton-root":{ py:0.3, px:1, fontSize:10, color:"#6b7a8d", border:"1px solid #1a2535" },
                  "& .Mui-selected":{ color:"#00d4ff !important", background:"#00d4ff15 !important" } }}>
            <ToggleButton value="load">Load</ToggleButton>
            <ToggleButton value="solar">Solar</ToggleButton>
            <ToggleButton value="battery">Battery</ToggleButton>
            <ToggleButton value="price">Price</ToggleButton>
          </ToggleButtonGroup>
          <FormControl size="small" sx={{ minWidth:130 }}>
            <InputLabel>Node</InputLabel>
            <Select value={node} label="Node" onChange={e=>setNode(e.target.value)}>
              {NODES.map(n=><MenuItem key={n.value} value={n.value}>{n.label}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth:80 }}>
            <InputLabel>Window</InputLabel>
            <Select value={hours} label="Window" onChange={e=>setHours(e.target.value)}>
              {WINDOWS.map(w=><MenuItem key={w.v} value={w.v}>{w.l}</MenuItem>)}
            </Select>
          </FormControl>
        </Box>
      </Box>
      {loading && data.length === 0
        ? <Box py={4} textAlign="center"><Typography color="text.secondary" fontSize={13}>Loading from TimescaleDB...</Typography></Box>
        : data.length === 0
          ? <Box py={4} textAlign="center">
              <Typography color="text.secondary" fontSize={13}>No data in selected window. Try a wider time range.</Typography>
            </Box>
          : (
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={data} margin={{ top:8, right:20, bottom:5, left:10 }}>
                <defs>
                  <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={cfg.color} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={cfg.color} stopOpacity={0.03} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1a2535" />
                <XAxis dataKey="label" tick={{ fill:"#6b7a8d", fontSize:9 }} interval={Math.max(1, Math.floor(data.length/8))} />
                <YAxis tick={{ fill:"#6b7a8d", fontSize:10 }} unit={` ${cfg.unit}`} width={55} />
                <Tooltip
                  contentStyle={{ background:"#0d1520", border:"1px solid #1a2535", borderRadius:8, fontSize:11 }}
                  labelStyle={{ color:"#e2e8f0", fontWeight:600 }}
                  formatter={(v,n) => [v != null ? `${v} ${cfg.unit}` : "—", n]}
                />
                <Legend wrapperStyle={{ color:"#8b9ab0", fontSize:11 }} />
                {splitIdx > 0 && (
                  <ReferenceLine x={data[splitIdx]?.label} stroke="#374151" strokeDasharray="5 3"
                    label={{ value:"Forecast →", fill:"#6b7a8d", fontSize:10 }} />
                )}
                <Area dataKey="q90" stroke="none" fill={cfg.color} fillOpacity={0.12} legendType="none" name="q90" />
                <Area dataKey="q10" stroke="none" fill="#060b14"  fillOpacity={1}    legendType="none" name="q10" />
                <Area dataKey={cfg.key} stroke={cfg.color} strokeWidth={2}
                  fill="url(#areaGrad)" dot={false} name={cfg.label} connectNulls />
                <Line dataKey="forecast" stroke="#fbbf24" strokeWidth={2} strokeDasharray="6 3"
                  dot={false} name="AI Forecast" connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          )
      }
      <Box display="flex" gap={2} mt={0.5} flexWrap="wrap">
        {[
          { c:"#ef4444", l:"Load (kW)" }, { c:"#f59e0b", l:"Solar (kW)" },
          { c:"#a855f7", l:"Battery SoC (%)" }, { c:"#fbbf24", l:"AI Forecast (dashed)" },
        ].map(m => (
          <Box key={m.l} display="flex" alignItems="center" gap={0.5}>
            <Box sx={{ width:12, height:3, background:m.c, borderRadius:2 }} />
            <Typography variant="caption" sx={{ color:"#6b7a8d", fontSize:9 }}>{m.l}</Typography>
          </Box>
        ))}
      </Box>
    </Box>
  )
}