/**
 * AEGIS – Anomaly Alert Panel
 * Real-time list of anomaly alerts with severity badges and drilldown.
 */

import { useEffect, useState } from 'react'
import {
  Box, Typography, List, ListItem, ListItemText,
  Chip, Divider, Alert
} from '@mui/material'

const SEVERITY_COLORS = {
  LOW:      'info',
  MEDIUM:   'warning',
  HIGH:     'error',
  CRITICAL: 'error',
}

export function AnomalyAlertPanel({ liveAlerts = [] }) {
  const [alerts, setAlerts] = useState([])

  useEffect(() => {
    fetch('/api/anomalies?limit=20')
      .then(r => r.json())
      .then(setAlerts)
      .catch(() => {})
  }, [])

  // Merge live alerts (from WebSocket) at top
  const combined = [...liveAlerts.slice(-5), ...alerts].slice(0, 25)

  return (
    <Box>
      <Typography variant="h6" gutterBottom>Anomaly Alerts</Typography>
      {combined.length === 0
        ? <Alert severity="success">No anomalies detected. System nominal.</Alert>
        : (
          <List dense disablePadding sx={{ maxHeight: 340, overflow: 'auto' }}>
            {combined.map((a, i) => (
              <Box key={i}>
                <ListItem alignItems="flex-start" sx={{ px: 0 }}>
                  <ListItemText
                    primary={
                      <Box display="flex" alignItems="center" gap={1}>
                        <Chip
                          label={a.severity}
                          color={SEVERITY_COLORS[a.severity] || 'default'}
                          size="small"
                        />
                        <Typography variant="body2" fontWeight="bold">
                          {a.node_id}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {new Date(a.time).toLocaleTimeString()}
                        </Typography>
                      </Box>
                    }
                    secondary={
                      <Box mt={0.5}>
                        <Typography variant="caption" color="text.secondary">
                          {a.diagnosis || a.diagnosis_code || 'Unknown anomaly'}
                        </Typography>
                        <br />
                        <Typography variant="caption" sx={{ color: '#ffd54f' }}>
                          ⚡ {a.recommended_action || ''}
                        </Typography>
                      </Box>
                    }
                  />
                </ListItem>
                {i < combined.length - 1 && <Divider />}
              </Box>
            ))}
          </List>
        )
      }
    </Box>
  )
}

