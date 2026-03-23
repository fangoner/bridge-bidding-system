import React from 'react';
import { Box } from '@mui/material';

function DoubleDummyTable({ tableData }) {
  if (!tableData) return null;

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
      fontFamily: '"Courier New", monospace',
      fontSize: { xs: '0.75rem', md: '0.9rem' },
    }}>
      <Box className="bidding-header" sx={{
        display: 'flex',
        justifyContent: 'space-around',
        borderBottom: '1px solid #333',
        paddingBottom: { xs: 0.5, md: 1 },
        marginBottom: { xs: 0.5, md: 1 },
        fontWeight: 'bold',
        color: '#333',
      }}>
        {positions.map(pos => (
          <Box
            key={pos}
            component="span"
            sx={{
              flex: 1,
              textAlign: 'center',
              minWidth: { xs: 35, md: 50 },
              color: '#333',
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
            borderBottom: '1px solid #ddd',
            '&:last-child': {
              borderBottom: 'none',
            },
          }}
        >
          {row.map((cell, cellIndex) => (
            <Box
              key={cellIndex}
              component="span"
              className={`bidding-cell ${cell !== '-' ? 'has-bid' : ''}`}
              sx={{
                flex: 1,
                textAlign: 'center',
                minWidth: 50,
                fontWeight: 500,
                color: '#333',
                backgroundColor: '#e3f2fd',
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