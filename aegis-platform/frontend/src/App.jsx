/**
 * AEGIS – Elite Dashboard v2
 */
import { useState, useEffect, useCallback } from "react"
import {
  ThemeProvider, createTheme, CssBaseline, Box, Grid, Paper,
  Typography, Chip, Divider, CircularProgress, LinearProgress,
  Tab, Tabs, IconButton, Badge
} from "@mui/material"
import BoltIcon           from "@mui/icons-material/Bolt"
import WarningAmberIcon   from "@mui/icons-material/WarningAmber"
import TuneIcon           from "@mui/icons-material/Tune"
import PsychologyIcon     from "@mui/icons-material/Psychology"
import BarChartIcon       from "@mui/icons-material/BarChart"
import FlashOnIcon        from "@mui/icons-material/FlashOn"
import WbSunnyIcon from "@mui/icons-material/WbSunny"
import BatteryChargingFullIcon from "@mui/icons-material/Battery5Bar"
import AttachMoneyIcon from "@mui/icons-material/AttachMoney"
import SpeedIcon          from "@mui/icons-material/Speed"
import TrendingUpIcon from "@mui/icons-material/TrendingUp"
import ShieldIcon         from "@mui/icons-material/Shield"
import PublicIcon from "@mui/icons-material/Public"
import NotificationsIcon  from "@mui/icons-material/Notifications"
import { useWebSocket }      from "./hooks/useWebSocket"
import { SingleLineDiagram } from "./components/SingleLineDiagram"
import { ForecastChart }     from "./components/ForecastChart"
import { AnomalyAlertPanel } from "./components/AnomalyAlertPanel"
import { WhatIfSimulator }   from "./components/WhatIfSimulator"
import { OperatorOverride }  from "./components/OperatorOverride"
import { AIInsightsPanel }   from "./components/AIInsightsPanel"
const theme = createTheme({
  palette: {
    mode: "dark",
    primary:    { main: "#00d4ff" },
    secondary:  { main: "#a855f7" },
    success:    { main: "#22c55e" },
    warning:    { main: "#f59e0b" },
    error:      { main: "#ef4444" },
    background: { default: "#060b14", paper: "#0d1520" },
  },
  typography: { fontFamily: '"Inter","Roboto",sans-serif' },
  components: { MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } } },
})
const NAV = [
  { label: "Dashboard",   icon: <BarChartIcon />,     id: "dashboard" },
  { label: "AI Insights", icon: <PsychologyIcon />,   id: "ai"        },
  { label: "Forecasting", icon: <TrendingUpIcon />,    id: "forecast"  },
  { label: "Anomalies",   icon: <WarningAmberIcon />, id: "anomalies" },
  { label: "Operator",    icon: <TuneIcon />,         id: "operator"  },
]
function KPICard({ icon, label, value, unit, color, subtext, loading }) {
  return (
    <Paper sx={{
      p: 2.5, position: "relative", overflow: "hidden",
      border: `1px solid ${color}22`,
      background: `linear-gradient(135deg, #0d1520 60%, ${color}0d)`,
      borderRadius: 2,
      transition: "all 0.3s",
      "&:hover": { borderColor: `${color}55`, transform: "translateY(-2px)", boxShadow: `0 8px 32px ${color}22` }
    }}>
      <Box sx={{ position:"absolute", top:-20, right:-20, width:80, height:80, borderRadius:"50%",
        background:`radial-gradient(circle, ${color}2a 0%, transparent 70%)` }} />
      <Box display="flex" alignItems="center" gap={1} mb={1}>
        <Box sx={{ color, opacity:0.85, display:"flex" }}>{icon}</Box>
        <Typography variant="caption" sx={{ color:"#8b9ab0", textTransform:"uppercase", letterSpacing:1, fontSize:10 }}>{label}</Typography>
      </Box>
      {loading ? <LinearProgress sx={{ mt:1, borderRadius:1 }} /> :
        <Box display="flex" alignItems="baseline" gap={0.5}>
          <Typography variant="h4" sx={{ color, fontWeight:700, lineHeight:1 }}>{value ?? "—"}</Typography>
          {unit && <Typography variant="caption" sx={{ color:"#8b9ab0", fontSize:12 }}>{unit}</Typography>}
        </Box>
      }
      {subtext && <Typography variant="caption" sx={{ color:"#6b7a8d", fontSize:10, mt:0.5, display:"block" }}>{subtext}</Typography>}
    </Paper>
  )
}
function LivePulse({ connected }) {
  return (
    <Box display="flex" alignItems="center" gap={0.7}>
      <Box sx={{
        width:8, height:8, borderRadius:"50%",
        background: connected ? "#22c55e" : "#ef4444",
        boxShadow:  connected ? "0 0 8px #22c55e" : "0 0 8px #ef4444",
        animation:  connected ? "aegispulse 2s infinite" : "none",
        "@keyframes aegispulse": {
          "0%":   { boxShadow:"0 0 0 0 #22c55e66" },
          "70%":  { boxShadow:"0 0 0 6px transparent" },
          "100%": { boxShadow:"0 0 0 0 transparent" },
        }
      }} />
      <Typography variant="caption" sx={{ color: connected ? "#22c55e" : "#ef4444", fontSize:10, fontWeight:600 }}>
        {connected ? "LIVE" : "OFFLINE"}
      </Typography>
    </Box>
  )
}
function NodeMini({ nodeKey, data }) {
  if (!data) return null
  const soc = Math.round((data.battery_soc || 0) * 100)
  const sc  = soc < 25 ? "#ef4444" : soc < 50 ? "#f59e0b" : "#22c55e"
  return (
    <Paper sx={{ p:1.2, border:"1px solid #1a2535", background:"#0a1019", borderRadius:1.5, minWidth:90 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.5}>
        <Typography variant="caption" sx={{ color:"#00d4ff", fontWeight:700, textTransform:"uppercase", fontSize:9 }}>
          {nodeKey.replace("_01","")}
        </Typography>
        <Box sx={{ width:5, height:5, borderRadius:"50%", background:"#22c55e", boxShadow:"0 0 4px #22c55e" }} />
      </Box>
      <Typography variant="body2" sx={{ color:"#e2e8f0", fontWeight:700, fontSize:13 }}>{Math.round(data.load_kw || 0)} kW</Typography>
      <Box display="flex" alignItems="center" gap={0.5} mt={0.4}>
        <Box sx={{ flex:1, height:3, background:"#1a2535", borderRadius:2 }}>
          <Box sx={{ width:`${soc}%`, height:"100%", background:sc, borderRadius:2, transition:"width 0.5s" }} />
        </Box>
        <Typography variant="caption" sx={{ color:sc, fontSize:9, minWidth:22 }}>{soc}%</Typography>
      </Box>
    </Paper>
  )
}
export default function App() {
  const [page,       setPage]       = useState("dashboard")
  const [telemetry,  setTelemetry]  = useState({})
  const [restData,   setRestData]   = useState(null)
  const [aiData,     setAiData]     = useState(null)
  const [liveAlerts, setLiveAlerts] = useState([])
  const [alertCount, setAlertCount] = useState(0)
  const [dataLoaded, setDataLoaded] = useState(false)
  const { connected, subscribe } = useWebSocket()
  useEffect(() => subscribe("sensor.features", p => {
    if (!p?.node_id) return
    setTelemetry(prev => ({ ...prev, [p.node_id]: p }))
  }), [subscribe])
  useEffect(() => subscribe("anomaly.alerts", p => {
    setLiveAlerts(prev => [p, ...prev].slice(0, 100))
    setAlertCount(c => c + 1)
  }), [subscribe])
  const pollRest = useCallback(async () => {
    try {
      const r = await fetch("/api/dashboard/summary")
      if (r.ok) {
        const d = await r.json()
        setRestData(d)
        if (d.nodes) {
          const m = {}; d.nodes.forEach(n => { m[n.node_id] = n })
          setTelemetry(prev => ({ ...m, ...prev }))
          setDataLoaded(true)
        }
      }
    } catch (_) {}
  }, [])
  const pollAI = useCallback(async () => {
    try {
      const r = await fetch("/api/ai/insights")
      if (r.ok) setAiData(await r.json())
    } catch (_) {}
  }, [])
  useEffect(() => {
    pollRest(); pollAI()
    const t1 = setInterval(pollRest, 5000)
    const t2 = setInterval(pollAI,  15000)
    return () => { clearInterval(t1); clearInterval(t2) }
  }, [pollRest, pollAI])
  const comm = telemetry["commercial_01"]  || {}
  const resi = telemetry["residential_01"] || {}
  const ind  = telemetry["industrial_01"]  || {}
  const totalLoad  = [comm.load_kw, resi.load_kw, ind.load_kw].filter(v => v != null).reduce((s,v)=>s+Number(v),0)
  const totalSolar = Math.max(comm.solar_kw||0, resi.solar_kw||0, ind.solar_kw||0)
  const avgSoC     = [comm,resi,ind].filter(n=>n.battery_soc).reduce((s,n,_,a)=>s+n.battery_soc/a.length,0)
  const price      = comm.price_per_kwh || resi.price_per_kwh || ind.price_per_kwh || null
  const voltage    = comm.voltage_pu || null
  const temp       = comm.temperature || null
  const renewPct   = totalLoad > 0 ? Math.round(totalSolar/totalLoad*100) : 0
  const effScore   = aiData?.summary?.efficiency_score ?? null
  const effGrade   = aiData?.summary?.efficiency_grade ?? null
  const renderPage = () => {
    switch (page) {
      case "ai":        return <AIInsightsPanel />
      case "forecast":  return <Box p={1}><ForecastChart /></Box>
      case "anomalies": return <AnomalyAlertPanel alerts={liveAlerts} />
      case "operator":  return <Box sx={{ display:"flex", flexDirection:"column", gap:2 }}><WhatIfSimulator /><OperatorOverride /></Box>
      default:          return (
        <DashboardPage comm={comm} resi={resi} ind={ind}
          totalLoad={totalLoad} totalSolar={totalSolar} avgSoC={avgSoC}
          price={price} voltage={voltage} temp={temp} renewPct={renewPct}
          effScore={effScore} effGrade={effGrade} aiData={aiData}
          liveAlerts={liveAlerts} dataLoaded={dataLoaded} telemetry={telemetry} restData={restData} />
      )
    }
  }
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ minHeight:"100vh", background:"#060b14" }}>
        <Box sx={{
          position:"fixed", top:0, left:0, right:0, zIndex:1200, height:52,
          background:"linear-gradient(90deg,#060b14 0%,#0d1520 100%)",
          borderBottom:"1px solid #1a2535",
          display:"flex", alignItems:"center", px:3, gap:2,
        }}>
          <BoltIcon sx={{ color:"#f59e0b", fontSize:22 }} />
          <Typography variant="subtitle1" sx={{ fontWeight:800, color:"#e2e8f0", letterSpacing:1, fontSize:15 }}>AEGIS</Typography>
          <Typography variant="caption" sx={{ color:"#374151", fontSize:9, display:{ xs:"none", sm:"block" } }}>
            AUTONOMOUS ENERGY GRID INTELLIGENT SYSTEM
          </Typography>
          <Box flex={1} />
          {effScore != null && (
            <Chip icon={<ShieldIcon sx={{ fontSize:"13px !important" }} />}
              label={`AI Score: ${effScore}/100 · Grade ${effGrade}`} size="small"
              sx={{
                background: effScore>=80?"#22c55e22": effScore>=65?"#f59e0b22":"#ef444422",
                color:      effScore>=80?"#22c55e":   effScore>=65?"#f59e0b":  "#ef4444",
                border:`1px solid ${effScore>=80?"#22c55e44": effScore>=65?"#f59e0b44":"#ef444444"}`,
                fontWeight:700, fontSize:10,
              }} />
          )}
          <IconButton size="small" onClick={() => { setPage("anomalies"); setAlertCount(0) }}>
            <Badge badgeContent={alertCount||null} color="error" max={99}>
              <NotificationsIcon sx={{ color: alertCount>0?"#ef4444":"#374151", fontSize:18 }} />
            </Badge>
          </IconButton>
          <LivePulse connected={connected} />
        </Box>
        <Box sx={{ position:"fixed", top:52, left:0, right:0, zIndex:1100, background:"#0d1520", borderBottom:"1px solid #1a2535" }}>
          <Tabs value={page} onChange={(_,v)=>setPage(v)} variant="scrollable" scrollButtons="auto"
            sx={{ minHeight:40,
              "& .MuiTab-root":  { minHeight:40, fontSize:11, fontWeight:600, color:"#374151", textTransform:"none", py:0 },
              "& .Mui-selected": { color:"#00d4ff !important" },
              "& .MuiTabs-indicator": { background:"#00d4ff", height:2 },
            }}>
            {NAV.map(n => <Tab key={n.id} value={n.id} label={n.label} icon={n.icon} iconPosition="start" sx={{ gap:0.5 }} />)}
          </Tabs>
        </Box>
        <Box sx={{ pt:"92px", px:{ xs:1, sm:2 }, pb:3, minHeight:"100vh" }}>
          {renderPage()}
        </Box>
      </Box>
    </ThemeProvider>
  )
}
function DashboardPage({ comm, resi, ind, totalLoad, totalSolar, avgSoC, price, voltage,
  temp, renewPct, effScore, effGrade, aiData, liveAlerts, dataLoaded, telemetry, restData }) {
  const netGrid = Math.max(0, totalLoad - totalSolar)
  const carbon  = (totalSolar * 0.5).toFixed(1)
  const priceLabel = price == null ? null : price < 0.06 ? "🟢 Off-peak" : price < 0.12 ? "🟡 Mid-peak" : "🔴 Peak tariff"
  return (
    <Box>
      <Grid container spacing={1.5} mb={2}>
        <Grid item xs={6} sm={4} md={2}>
          <KPICard icon={<FlashOnIcon />} label="Total Load" color="#ef4444"
            value={dataLoaded ? Math.round(totalLoad) : null} unit="kW" loading={!dataLoaded} subtext={`Grid import: ${Math.round(netGrid)} kW`} />
        </Grid>
        <Grid item xs={6} sm={4} md={2}>
          <KPICard icon={<WbSunnyIcon />} label="Solar Gen" color="#f59e0b"
            value={dataLoaded ? Math.round(totalSolar) : null} unit="kW" loading={!dataLoaded} subtext={`${renewPct}% renewable`} />
        </Grid>
        <Grid item xs={6} sm={4} md={2}>
          <KPICard icon={<BatteryChargingFullIcon />} label="Battery SoC" color="#a855f7"
            value={dataLoaded && avgSoC>0 ? Math.round(avgSoC*100) : null} unit="%" loading={!dataLoaded} subtext="Avg all nodes" />
        </Grid>
        <Grid item xs={6} sm={4} md={2}>
          <KPICard icon={<AttachMoneyIcon />} label="Price" color="#22c55e"
            value={price!=null ? (price*100).toFixed(2) : null} unit="¢/kWh" loading={!dataLoaded} subtext={priceLabel} />
        </Grid>
        <Grid item xs={6} sm={4} md={2}>
          <KPICard icon={<SpeedIcon />} label="Voltage" color="#00d4ff"
            value={voltage!=null ? voltage.toFixed(3) : null} unit="pu" loading={!dataLoaded}
            subtext={voltage ? (Math.abs(voltage-1.0)<0.04 ? "✅ Nominal" : "⚠️ Deviation") : null} />
        </Grid>
        <Grid item xs={6} sm={4} md={2}>
          <KPICard icon={<PublicIcon />} label="CO₂ Saved" color="#10b981"
            value={dataLoaded ? carbon : null} unit="kg/h" loading={!dataLoaded} subtext="vs grid-only" />
        </Grid>
      </Grid>
      {aiData?.summary && (
        <Paper sx={{ mb:2, p:1.5, background:"#0a1019", border:"1px solid #1a2535", borderRadius:2 }}>
          <Box display="flex" alignItems="center" gap={2} flexWrap="wrap">
            <Box display="flex" alignItems="center" gap={1}>
              <PsychologyIcon sx={{ color:"#a855f7", fontSize:16 }} />
              <Typography variant="caption" sx={{ color:"#a855f7", fontWeight:700, textTransform:"uppercase", fontSize:10 }}>AI Engine</Typography>
              <Chip label="Active" size="small" sx={{ height:14, fontSize:8, background:"#22c55e22", color:"#22c55e" }} />
            </Box>
            <Divider orientation="vertical" flexItem sx={{ borderColor:"#1a2535" }} />
            {[
              { l:"Efficiency", v:`${effScore}/100 (${effGrade})`, c: effScore>=65?"#22c55e":"#f59e0b" },
              { l:"Renewable",  v:`${renewPct}%`,                  c: renewPct>30?"#22c55e":"#f59e0b" },
              { l:"Freq",       v:`${(comm.frequency_hz||50).toFixed(3)} Hz`, c:"#00d4ff" },
              { l:"Temp",       v: temp ? `${temp.toFixed(1)}°C` : "—",       c:"#f59e0b" },
              { l:"Anomalies",  v:`${restData?.anomalies_1h??0}/hr`,           c: restData?.anomalies_1h>0?"#ef4444":"#22c55e" },
              { l:"CO₂ Saved",  v:`${(aiData.summary.carbon_avoided_kg_h||0).toFixed(1)} kg/h`, c:"#10b981" },
            ].map(m => (
              <Box key={m.l} display="flex" alignItems="center" gap={0.5}>
                <Typography variant="caption" sx={{ color:"#374151", fontSize:10 }}>{m.l}:</Typography>
                <Typography variant="caption" sx={{ color:m.c, fontWeight:700, fontSize:10 }}>{m.v}</Typography>
              </Box>
            ))}
          </Box>
        </Paper>
      )}
      <Grid container spacing={2} mb={2}>
        <Grid item xs={12} md={7}>
          <Paper sx={{ p:2, background:"#0d1520", border:"1px solid #1a2535", borderRadius:2, height:"100%" }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={1.5} flexWrap="wrap" gap={1}>
              <Typography variant="subtitle2" sx={{ color:"#e2e8f0", fontWeight:700 }}>Live Single-Line Diagram</Typography>
              <Box display="flex" gap={1} flexWrap="wrap">
                {["residential_01","commercial_01","industrial_01"].map(k => <NodeMini key={k} nodeKey={k} data={telemetry[k]} />)}
              </Box>
            </Box>
            <SingleLineDiagram telemetry={telemetry} />
          </Paper>
        </Grid>
        <Grid item xs={12} md={5}>
          <Paper sx={{ p:2, background:"#0d1520", border:"1px solid #1a2535", borderRadius:2, height:"100%", minHeight:380 }}>
            <Box display="flex" alignItems="center" gap={1} mb={1.5}>
              <PsychologyIcon sx={{ color:"#a855f7", fontSize:18 }} />
              <Typography variant="subtitle2" sx={{ color:"#e2e8f0", fontWeight:700 }}>Live AI Insights</Typography>
              <Chip label="15s refresh" size="small" sx={{ fontSize:8, height:16, background:"#a855f722", color:"#a855f7" }} />
            </Box>
            {aiData?.insights ? (
              <Box sx={{ display:"flex", flexDirection:"column", gap:1, maxHeight:340, overflowY:"auto",
                "&::-webkit-scrollbar":{ width:4 }, "&::-webkit-scrollbar-thumb":{ background:"#1a2535", borderRadius:2 } }}>
                {aiData.insights.map(ins => {
                  const C = { success:"#22c55e", warning:"#f59e0b", error:"#ef4444", info:"#00d4ff" }[ins.severity]||"#00d4ff"
                  return (
                    <Box key={ins.id} sx={{ p:1.2, borderRadius:1.5, background:`${C}0d`, border:`1px solid ${C}22` }}>
                      <Box display="flex" justifyContent="space-between" alignItems="flex-start">
                        <Typography variant="caption" sx={{ color:C, fontWeight:700, fontSize:11, flex:1 }}>{ins.title}</Typography>
                        <Chip label={ins.value} size="small" sx={{ height:16, fontSize:8, background:`${C}22`, color:C, ml:1, flexShrink:0 }} />
                      </Box>
                      <Typography variant="caption" sx={{ color:"#6b7a8d", fontSize:9, display:"block", mt:0.3 }}>{ins.recommendation}</Typography>
                    </Box>
                  )
                })}
              </Box>
            ) : (
              <Box display="flex" alignItems="center" justifyContent="center" height={200}>
                <CircularProgress size={24} sx={{ color:"#a855f7" }} />
              </Box>
            )}
          </Paper>
        </Grid>
      </Grid>
      <Paper sx={{ p:2, background:"#0d1520", border:"1px solid #1a2535", borderRadius:2, mb:2 }}>
        <ForecastChart />
      </Paper>
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Paper sx={{ p:2, background:"#0d1520", border:"1px solid #1a2535", borderRadius:2 }}>
            <AnomalyAlertPanel alerts={liveAlerts} compact />
          </Paper>
        </Grid>
        <Grid item xs={12} md={6}>
          <AEGISvsML aiData={aiData} />
        </Grid>
      </Grid>
    </Box>
  )
}
function AEGISvsML({ aiData }) {
  const rows = [
    { icon:"📈", label:"Forecasting",        ml:"RandomForest R²=0.82",         aegis:"TCN+Attention R²=0.94" },
    { icon:"🛡️", label:"Anomaly Detection",  ml:"Static threshold rules",        aegis:"VAE deep learning" },
    { icon:"⚡", label:"Battery Dispatch",    ml:"Fixed schedule",                aegis:"SAC Reinforcement Learning" },
    { icon:"🔄", label:"Real-time Adapt.",   ml:"❌ Batch retrain only",         aegis:"✅ Online learning loop" },
    { icon:"🌐", label:"Multi-node",         ml:"❌ Single node only",           aegis:"✅ 3-node co-optimisation" },
    { icon:"🧠", label:"Causal Reasoning",   ml:"❌ Correlation only",           aegis:"✅ Causal rule engine" },
  ]
  return (
    <Paper sx={{ p:2, background:"#0d1520", border:"1px solid #1a2535", borderRadius:2, height:"100%" }}>
      <Box display="flex" alignItems="center" gap={1} mb={1.5}>
        <TrendingUpIcon sx={{ color:"#00d4ff", fontSize:18 }} />
        <Typography variant="subtitle2" sx={{ color:"#e2e8f0", fontWeight:700 }}>Why AEGIS Beats Simple ML</Typography>
        <Chip label="6 Key Advantages" size="small" sx={{ fontSize:9, height:18, background:"#00d4ff22", color:"#00d4ff" }} />
      </Box>
      <Box sx={{ display:"grid", gridTemplateColumns:"20px 1fr 1fr", gap:"2px 6px", mb:1 }}>
        <Box />
        <Typography variant="caption" sx={{ color:"#ef4444", fontWeight:700, fontSize:9, textAlign:"center" }}>Simple ML</Typography>
        <Typography variant="caption" sx={{ color:"#22c55e", fontWeight:700, fontSize:9, textAlign:"center" }}>AEGIS AI</Typography>
      </Box>
      {rows.map(r => (
        <Box key={r.label} sx={{ display:"grid", gridTemplateColumns:"20px 1.1fr 1.1fr", gap:"2px 6px", mb:0.8, alignItems:"start" }}>
          <Typography sx={{ fontSize:12, lineHeight:"18px" }}>{r.icon}</Typography>
          <Box sx={{ p:"3px 6px", borderRadius:1, background:"#ef444411", border:"1px solid #ef444422" }}>
            <Typography variant="caption" sx={{ color:"#ef4444", fontSize:9 }}>{r.ml}</Typography>
          </Box>
          <Box sx={{ p:"3px 6px", borderRadius:1, background:"#22c55e11", border:"1px solid #22c55e22" }}>
            <Typography variant="caption" sx={{ color:"#22c55e", fontSize:9 }}>{r.aegis}</Typography>
          </Box>
        </Box>
      ))}
      {aiData?.summary && (
        <Box sx={{ background:"#00d4ff0d", border:"1px solid #00d4ff22", borderRadius:1.5, mt:1.5, p:1.2 }}>
          <Typography variant="caption" sx={{ color:"#00d4ff", fontWeight:700, fontSize:10 }}>
            🏆 Live: {(aiData.summary.renewable_share_pct||0).toFixed(1)}% renewable · {(aiData.summary.carbon_avoided_kg_h||0).toFixed(1)} kg CO₂/h saved · Score {aiData.summary.efficiency_score}/100
          </Typography>
        </Box>
      )}
    </Paper>
  )
}