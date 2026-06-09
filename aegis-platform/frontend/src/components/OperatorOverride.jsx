/**
 * AEGIS – Operator Override Panel
 * Manual battery dispatch and demand-response commands.
 * All interventions are JWT-authenticated and logged.
 */

import { useState } from 'react'
import {
  Box, Typography, TextField, Button, Select, MenuItem,
  FormControl, InputLabel, Alert, Divider, Stack
} from '@mui/material'

const TOKEN_KEY = 'aegis_jwt'

export function OperatorOverride() {
  const [token,   setToken]   = useState(localStorage.getItem(TOKEN_KEY) || '')
  const [user,    setUser]    = useState('admin')
  const [pass,    setPass]    = useState('')
  const [loggedIn, setLoggedIn] = useState(!!token)
  const [authErr, setAuthErr] = useState(null)

  // Control form
  const [device,  setDevice]  = useState('commercial_01')
  const [cmd,     setCmd]     = useState('discharge')
  const [value,   setValue]   = useState(30)
  const [notes,   setNotes]   = useState('')
  const [cmdResult, setCmdResult] = useState(null)
  const [cmdErr,  setCmdErr]  = useState(null)

  const login = async () => {
    setAuthErr(null)
    const form = new URLSearchParams({ username: user, password: pass })
    const r = await fetch('/api/control/token', { method: 'POST', body: form })
    if (r.ok) {
      const data = await r.json()
      localStorage.setItem(TOKEN_KEY, data.access_token)
      setToken(data.access_token)
      setLoggedIn(true)
    } else {
      setAuthErr('Login failed. Use admin / admin123')
    }
  }

  const sendCommand = async () => {
    setCmdErr(null)
    setCmdResult(null)
    const r = await fetch('/api/control/manual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ device_id: device, command_type: cmd, value_kw: Number(value), notes }),
    })
    if (r.ok) {
      setCmdResult(await r.json())
    } else {
      setCmdErr(`Error ${r.status}: ${await r.text()}`)
    }
  }

  if (!loggedIn) {
    return (
      <Box>
        <Typography variant="h6" gutterBottom>Operator Override</Typography>
        <Stack spacing={1.5} maxWidth={280}>
          <TextField size="small" label="Username" value={user} onChange={e => setUser(e.target.value)} />
          <TextField size="small" label="Password" type="password" value={pass} onChange={e => setPass(e.target.value)} />
          <Button variant="contained" onClick={login}>Login</Button>
          {authErr && <Alert severity="error">{authErr}</Alert>}
        </Stack>
      </Box>
    )
  }

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Operator Override
        <Typography component="span" variant="caption" color="success.main" ml={1}>● Authenticated</Typography>
      </Typography>

      <Stack spacing={1.5}>
        <FormControl size="small">
          <InputLabel>Device</InputLabel>
          <Select value={device} label="Device" onChange={e => setDevice(e.target.value)}>
            <MenuItem value="residential_01">Residential</MenuItem>
            <MenuItem value="commercial_01">Commercial</MenuItem>
            <MenuItem value="industrial_01">Industrial</MenuItem>
          </Select>
        </FormControl>

        <FormControl size="small">
          <InputLabel>Command</InputLabel>
          <Select value={cmd} label="Command" onChange={e => setCmd(e.target.value)}>
            <MenuItem value="charge">Charge Battery</MenuItem>
            <MenuItem value="discharge">Discharge Battery</MenuItem>
            <MenuItem value="curtail">Curtail Solar</MenuItem>
            <MenuItem value="shed_load">Shed Load</MenuItem>
          </Select>
        </FormControl>

        <TextField size="small" label="Value (kW)" type="number" value={value}
          onChange={e => setValue(e.target.value)} />

        <TextField size="small" label="Notes" value={notes}
          onChange={e => setNotes(e.target.value)} />

        <Button variant="contained" color="warning" onClick={sendCommand}>
          ⚡ Dispatch Command
        </Button>

        {cmdErr    && <Alert severity="error">{cmdErr}</Alert>}
        {cmdResult && (
          <Alert severity="success">
            Command dispatched at {cmdResult.time?.slice(11, 19)} by {cmdResult.operator}
          </Alert>
        )}
      </Stack>
    </Box>
  )
}

