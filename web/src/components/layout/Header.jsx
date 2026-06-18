import React from 'react';
import { Box, Button, Typography, useMediaQuery, useTheme } from '@mui/material';
import ControlButtons from '../ControlButtons';

/**
 * Minimal inline toolbar — flows with page content.
 */
export default function Header({ onBack, mode, ...controlProps }) {
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
      <Button
        size="small"
        onClick={onBack}
        sx={{
          fontSize: '0.8125rem',
          textTransform: 'none',
          color: 'text.secondary',
          '&:hover': { color: 'primary.main' },
        }}
      >
        ← 返回
      </Button>

      <Typography
        variant="h4"
        component="h1"
        sx={{
          fontSize: isMobile ? '1.1rem' : '1.35rem',
          whiteSpace: 'nowrap',
          fontWeight: 700,
          color: 'text.primary',
        }}
      >
        {mode === 'practice' ? '发牌练习' : '模拟实战'}
      </Typography>

      <ControlButtons
        size={isMobile ? 'medium' : 'large'}
        mode={mode}
        {...controlProps}
      />
    </Box>
  );
}
