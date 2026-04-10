import React from 'react';
import { Box, Typography } from '@mui/material';

/**
 * BiddingTable component for displaying bidding history in a table format
 *
 * @param {Object} props
 * @param {Array} props.biddingSequence - Array of bid objects { position, bid }
 * @param {string} props.dealer - Dealer position
 */
function BiddingTable({ biddingSequence, dealer }) {
  const isMobile = window.innerWidth < 600;
  
  if (biddingSequence.length === 0) {
    return (
      <Box className="bidding-empty" sx={{
        color: '#666',
        fontStyle: 'italic',
        textAlign: 'center',
        padding: 3,
      }}>
        等待叫牌...<br />
        <small>发牌人: {dealer}</small>
      </Box>
    );
  }

  const positions = ['南', '西', '北', '东'];
  const rows = [];
  let currentRow = Array(4).fill(null);

  biddingSequence.forEach((bid) => {
    const posIndex = positions.indexOf(bid.position);
    currentRow[posIndex] = bid.bid;

    // If this row is full (East bid) or it's the last bid
    if (posIndex === 3) {
      rows.push([...currentRow]);
      currentRow = Array(4).fill(null);
    }
  });

  // Add incomplete last row
  if (currentRow.some(cell => cell !== null)) {
    rows.push([...currentRow]);
  }

  return (
    <Box className="bidding-table" sx={{
      width: '100%',
      fontFamily: '"Courier New", monospace',
      fontSize: isMobile ? '0.9rem' : '0.9rem',
    }}>
      <Box className="bidding-header" sx={{
        display: 'flex',
        justifyContent: 'space-around',
        borderBottom: '2px solid #333',
        paddingBottom: isMobile ? 0.5 : 1,
        marginBottom: isMobile ? 0.5 : 1,
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
              minWidth: isMobile ? 60 : 50,
              color: pos === dealer ? '#d32f2f' : 'inherit',
            }}
            className={pos === dealer ? 'dealer' : ''}
          >
            {pos}{pos === dealer ? '*' : ''}
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
          {positions.map((pos, colIndex) => (
            <Box
              key={colIndex}
              component="span"
              className={`bidding-cell ${row[colIndex] ? 'has-bid' : ''}`}
              sx={{
                flex: 1,
                textAlign: 'center',
                minWidth: isMobile ? 60 : 50,
                fontWeight: 500,
                color: '#333',
                backgroundColor: row[colIndex] ? '#e3f2fd' : 'transparent',
                borderRadius: 1,
              }}
            >
              {row[colIndex] === 'pass' ? 'P' : row[colIndex] || ''}
            </Box>
          ))}
        </Box>
      ))}
    </Box>
  );
}

export default BiddingTable;