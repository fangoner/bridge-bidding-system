import React from 'react'
import { Box, useTheme, alpha } from '@mui/material'

function DoubleDummyTable({ tableData }) {
  const theme = useTheme()

  if (!tableData) return null

  const positions = ['南', '西', '北', '东'];
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
      fontSize: { xs: '0.75rem', md: '0.9rem' },
    }}>
      <Box className="bidding-header" sx={{
        display: 'flex',
        justifyContent: 'space-around',
        borderBottom: `2px solid ${theme.palette.text.primary}`,
        paddingBottom: { xs: 0.5, md: 1 },
        marginBottom: { xs: 0.5, md: 1 },
        fontWeight: 'bold',
        color: theme.palette.text.primary,
      }}>
        {positions.map(pos => (
          <Box
            key={pos}
            component="span"
            sx={{
              flex: 1,
              textAlign: 'center',
              minWidth: { xs: 35, md: 50 },
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
            justifyContent: 'space-around',
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
                minWidth: 50,
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
