import React from 'react';
import { Box, Typography, ToggleButton, ToggleButtonGroup, useMediaQuery, useTheme } from '@mui/material';
import ControlButtons from '../ControlButtons';

/**
 * Minimal inline toolbar — flows with page content.
 */
export default function Header({ onModeChange, mode, ...controlProps }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  return (
    <Box sx={{
      display: 'flex',
      flexWrap: 'wrap',
      justifyContent: 'center',
      alignItems: 'center',
      gap: isMobile ? 1 : 2,
      mb: 2,
    }}>
      <ToggleButtonGroup
        value={mode}
        exclusive
        onChange={(e, v) => v && onModeChange && onModeChange(v)}
        size="small"
        sx={{ height: 28 }}
      >
        <ToggleButton value="practice" sx={{ px: 1.5, py: 0, fontSize: '0.75rem', textTransform: 'none' }}>
          发牌练习
        </ToggleButton>
        <ToggleButton value="simulated" sx={{ px: 1.5, py: 0, fontSize: '0.75rem', textTransform: 'none' }}>
          模拟实战
        </ToggleButton>
      </ToggleButtonGroup>

      <ControlButtons
        size={isMobile ? 'medium' : 'large'}
        mode={mode}
        {...controlProps}
      />
    </Box>
  );
}
