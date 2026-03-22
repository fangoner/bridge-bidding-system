import React from 'react';
import { Box, Button, CircularProgress } from '@mui/material';
import HandDisplay from './HandDisplay';

function CardTable({
  hands,
  currentBidder,
  humanPosition,
  dealer,
  gameMode,
  showPartnerHand,
  showAIHands,
  showOpponentHands,
  getPartnerPosition,
  renderBiddingTable,
  checkBiddingComplete,
  outputFormats,
  outputFormatsLoading,
  handleAnalyzeContract,
  analyzeLoading,
  colorScheme,
  currentBiddingPosition,
}) {
  if (!hands) return null;

  const north = hands['北'];
  const south = hands['南'];
  const east = hands['东'];
  const west = hands['西'];

  const scheme = colorScheme || {
    table: {
      background: 'linear-gradient(135deg, #2e7d32 0%, #1b5e20 100%)',
      border: '3px solid rgba(255, 255, 255, 0.5)',
      centerBg: 'rgba(255, 255, 255, 0.95)',
    },
    button: {
      primary: '#1976d2',
      primaryHover: '#1565c0',
      text: 'white',
    },
  };

  const shouldShowHandContent = (position) => {
    if (!humanPosition) {
      return true;
    }
    if (position === humanPosition) {
      return true;
    }
    if (gameMode === 'four') {
      return showAIHands;
    }
    if (gameMode === 'pair') {
      const partnerPosition = getPartnerPosition(humanPosition);
      if (position === partnerPosition) {
        return showPartnerHand;
      }
      return showOpponentHands;
    }
    return true;
  };

  const renderHandWithStatus = (hand, position, sxProps) => {
    const isCurrentlyBidding = currentBiddingPosition === position;
    return (
      <Box sx={{ ...sxProps, position: 'relative' }}>
        {isCurrentlyBidding && (
          <Box sx={{
            position: 'absolute',
            top: 10,
            right: 8,
            zIndex: 100,
            bgcolor: 'rgba(0, 0, 0, 0.5)',
            borderRadius: '50%',
            p: 0.5,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <CircularProgress size={14} sx={{ color: '#ffeb3b' }} />
          </Box>
        )}
        <HandDisplay
          hand={hand}
          position={position}
          isActive={currentBidder === position}
          isHuman={humanPosition === position}
          isDealer={dealer === position}
          isPartner={humanPosition && getPartnerPosition(humanPosition) === position}
          showContent={shouldShowHandContent(position)}
        />
      </Box>
    );
  };

  return (
    <Box className="card-table-container" sx={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      padding: { xs: 1, md: 2 },
      background: scheme.table.background,
      borderRadius: 2,
      boxShadow: 8,
      minHeight: { xs: 350, md: 600 },
      width: '100%',
      position: 'relative',
    }}>
      {checkBiddingComplete && checkBiddingComplete() && (
        <Box sx={{
          position: 'absolute',
          top: 8,
          right: 8,
          zIndex: 10,
        }}>
          {outputFormatsLoading && <CircularProgress size={20} sx={{ mr: 1, color: 'white' }} />}
          <Button
            variant="contained"
            size="small"
            onClick={handleAnalyzeContract}
            disabled={!outputFormats?.deep_finesse || analyzeLoading}
            startIcon={analyzeLoading ? <CircularProgress size={16} /> : null}
            sx={{
              bgcolor: scheme.button.primary,
              color: scheme.button.text,
              '&:hover': {
                bgcolor: scheme.button.primaryHover,
              },
              '&.Mui-disabled': {
                bgcolor: 'rgba(255,255,255,0.5)',
                color: 'rgba(0,0,0,0.4)',
              }
            }}
          >
            检验定约
          </Button>
        </Box>
      )}

      {renderHandWithStatus(north, '北', { marginBottom: { xs: 1, md: 2 } })}

      <Box className="middle-row" sx={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        width: '100%',
        maxWidth: 800,
        margin: { xs: 1, md: 2 },
        gap: { xs: 1, md: 3 },
        flex: 1,
      }}>
        {renderHandWithStatus(west, '西', {})}

        <Box className="table-center">
          <Box className="table-border" sx={{
            width: { xs: 200, md: 280 },
            minHeight: { xs: 150, md: 280 },
            border: scheme.table.border,
            borderRadius: 2,
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'flex-start',
            background: scheme.table.centerBg,
            padding: { xs: 1, md: 2 },
            overflowY: 'auto',
            maxHeight: { xs: 200, md: 400 },
          }}>
            {renderBiddingTable ? renderBiddingTable() : (
              <div style={{ color: '#666', fontStyle: 'italic', textAlign: 'center', padding: 3 }}>
                等待叫牌...
              </div>
            )}
          </Box>
        </Box>

        {renderHandWithStatus(east, '东', {})}
      </Box>

      {renderHandWithStatus(south, '南', { marginTop: { xs: 1, md: 2 } })}
    </Box>
  );
}

export default CardTable;
