import React from 'react';
import { Box, Typography, useTheme, alpha } from '@mui/material';
import { BRIDGE_POSITIONS } from '../utils/position';

/**
 * BiddingTable component for displaying bidding history in a table format
 *
 * @param {Object} props
 * @param {Array} props.biddingSequence - Array of bid objects { position, bid }
 * @param {string} props.dealer - Dealer position
 */
function BiddingTable({ biddingSequence, dealer }) {
  const theme = useTheme();
  const isMobile = window.innerWidth < 600;

  if (biddingSequence.length === 0) {
    return (
      <Box className="bidding-empty" sx={{
        color: theme.palette.text.secondary,
        fontStyle: 'italic',
        textAlign: 'center',
        padding: 3,
      }}>
        等待叫牌...<br />
        <small>发牌人: {dealer}</small>
      </Box>
    );
  }

  const positions = BRIDGE_POSITIONS;
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
      fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", "Microsoft YaHei UI", Roboto, sans-serif',
      fontWeight: 600,
      fontSize: isMobile ? '0.9rem' : '0.9rem',
    }}>
      <Box className="bidding-header" sx={{
        display: 'flex',
        justifyContent: 'space-around',
        borderBottom: `2px solid ${theme.palette.text.primary}`,
        paddingBottom: isMobile ? 0.5 : 1,
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
              minWidth: isMobile ? 70 : 50,
              color: pos === dealer ? theme.palette.error.main : 'inherit',
            }}
            className={pos === dealer ? 'dealer' : ''}
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
          {positions.map((pos, colIndex) => (
            <Box
              key={colIndex}
              component="span"
              className={`bidding-cell ${row[colIndex] ? 'has-bid' : ''}`}
              sx={{
                flex: 1,
                textAlign: 'center',
                minWidth: isMobile ? 70 : 50,
                fontWeight: 500,
                color: theme.palette.text.primary,
                backgroundColor: row[colIndex] ? alpha(theme.palette.primary.main, 0.08) : 'transparent',
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
