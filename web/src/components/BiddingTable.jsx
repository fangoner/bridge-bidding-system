import React, { useRef } from 'react';
import { Box, Typography, Button, useTheme, alpha } from '@mui/material';
import { BRIDGE_POSITIONS } from '../utils/position';

/**
 * BiddingTable component for displaying bidding history in a table format
 *
 * @param {Object} props
 * @param {Array} props.biddingSequence - Array of bid objects { position, bid }
 * @param {string} props.dealer - Dealer position
 * @param {Function} [props.onScreenshotBidding] - 截屏识别叫牌过程回调（传入时且序列为空才显示按钮）
 * @param {boolean} [props.screenshotBiddingDisabled] - 截屏按钮禁用状态
 */
function BiddingTable({ biddingSequence, dealer, onScreenshotBidding, screenshotBiddingDisabled }) {
  const theme = useTheme();
  const isMobile = window.innerWidth < 600;
  const fileRef = useRef(null);

  if (biddingSequence.length === 0) {
    return (
      <Box className="bidding-empty" sx={{
        color: theme.palette.text.secondary,
        fontStyle: 'italic',
        textAlign: 'center',
        padding: 3,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 1.5,
      }}>
        <Box>
          等待叫牌...<br />
          <small>发牌人: {dealer}</small>
        </Box>
        {onScreenshotBidding && (
          <Button
            variant="outlined"
            size="small"
            color="primary"
            onClick={() => {
              const isTouch = window.matchMedia && window.matchMedia('(pointer: coarse)').matches
              const isMobileUA = isTouch || /Android|iPhone|iPad|iPod|Mobile|Mobi/i.test(navigator.userAgent) || ('ontouchstart' in window)
              if (isMobileUA) {
                fileRef.current?.click()
              } else {
                onScreenshotBidding()
              }
            }}
            disabled={screenshotBiddingDisabled}
            sx={{ textTransform: 'none', fontStyle: 'normal' }}
          >
            图片识别叫牌过程
          </Button>
        )}
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          style={{ display: 'none' }}
          onChange={(e) => {
            const file = e.target.files && e.target.files[0]
            e.target.value = ''
            if (file) onScreenshotBidding(file)
          }}
        />
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
            justifyContent: 'center',
            gap: isMobile ? 1 : 0,
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
                minWidth: isMobile ? 30 : 50,
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
