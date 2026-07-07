import React from 'react'
import { Box, useTheme, alpha } from '@mui/material'
import { BRIDGE_POSITIONS } from '../utils/position'

function DoubleDummyTable({ tableData }) {
  const theme = useTheme()
  const isMobile = window.innerWidth < 600

  if (!tableData) return null

  const positions = BRIDGE_POSITIONS;
  const trumpOrder = ['S', 'H', 'D', 'C', 'NT'];

  const rows = [];
  trumpOrder.forEach(trump => {
    const row = positions.map(pos => {
      const data = tableData[pos]?.[trump];
      if (!data) return '-';
      if (data.max_level && data.max_level > 0) {
        return `${data.max_level}${trump}`;
      }
      return '-';
    });
    rows.push(row);
  });

  return (
    <Box className="bidding-table" sx={{
      width: '100%',
      fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", "Microsoft YaHei UI", Roboto, sans-serif',
      fontWeight: 600,
      fontSize: isMobile ? '0.9rem' : '0.9rem',
    }}>
      <Box className="bidding-header" sx={{
        display: 'flex',
        justifyContent: 'center',
        gap: isMobile ? 1 : 0,
        borderBottom: `2px solid ${theme.palette.text.primary}`,
        paddingBottom: isMobile ? 1 : 1,
        marginBottom: isMobile ? 0.5 : 1,
        fontWeight: 'bold',
        color: theme.palette.text.primary,
        position: 'sticky',
        top: 0,
        zIndex: 2,
      }}>
        {positions.map(pos => (
          <Box
            key={pos}
            component="span"
            sx={{
              flex: 1,
              textAlign: 'center',
              minWidth: isMobile ? 30 : 50,
            }}
          >
            {pos}
          </Box>
        ))}
      </Box>

      {rows.map((row, rowIndex) => (
        <Box
          key={rowIndex}
          className="bidding-row"
          sx={{
            display: 'flex',
            justifyContent: 'center',
            gap: isMobile ? 1 : 0,
            padding: '4px 0',
            borderBottom: `1px solid ${theme.palette.divider}`,
            '&:last-child': {
              borderBottom: 'none',
            },
          }}
        >
          {row.map((cell, cellIndex) => (
            <Box
              key={cellIndex}
              component="span"
              className="bidding-cell"
              sx={{
                flex: 1,
                textAlign: 'center',
                minWidth: isMobile ? 30 : 50,
                fontWeight: 500,
                color: theme.palette.text.primary,
                backgroundColor: alpha(theme.palette.primary.main, 0.08),
                borderRadius: 1,
              }}
            >
              {cell}
            </Box>
          ))}
        </Box>
      ))}
    </Box>
  );
}

export default DoubleDummyTable;
