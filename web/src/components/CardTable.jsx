import React from 'react';
import { Box } from '@mui/material';
import HandDisplay from './HandDisplay';

/**
 * CardTable component for desktop-optimized bridge card table display
 *
 * @param {Object} props
 * @param {Object} props.hands - Object with keys '北', '南', '东', '西' containing hand objects
 * @param {string} props.currentBidder - Current bidding position
 * @param {string|null} props.humanPosition - Human player position or null for observer mode
 * @param {string} props.dealer - Dealer position
 * @param {string} props.gameMode - 'four' or 'pair'
 * @param {boolean} props.showPartnerHand - Whether to show partner's hand (pair mode)
 * @param {boolean} props.showAIHands - Whether to show AI hands (four mode)
 * @param {boolean} props.showOpponentHands - Whether to show opponent hands (pair mode)
 * @param {Function} props.getPartnerPosition - Function to get partner position
 * @param {Function} props.renderBiddingTable - Function to render bidding table (optional)
 */
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
}) {
  if (!hands) return null;

  const north = hands['北'];
  const south = hands['南'];
  const east = hands['东'];
  const west = hands['西'];

  // Determine if hand content should be shown
  const shouldShowHandContent = (position) => {
    // Observer mode: show all hands
    if (!humanPosition) {
      return true;
    }

    // Human player's own hand always shown
    if (position === humanPosition) {
      return true;
    }

    // Four-player mode
    if (gameMode === 'four') {
      // Other players' hands based on showAIHands setting
      return showAIHands;
    }

    // Pair mode
    if (gameMode === 'pair') {
      const partnerPosition = getPartnerPosition(humanPosition);

      // Partner's hand based on showPartnerHand setting
      if (position === partnerPosition) {
        return showPartnerHand;
      }

      // Opponent's hand based on showOpponentHands setting
      return showOpponentHands;
    }

    return true;
  };

  return (
    <Box className="card-table-container" sx={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      padding: { xs: 1, md: 2 },
      background: 'linear-gradient(135deg, #2e7d32 0%, #1b5e20 100%)',
      borderRadius: 2,
      boxShadow: 8,
      minHeight: { xs: 350, md: 600 },
      width: '100%',
    }}>
      {/* North hand */}
      <Box className="north-hand" sx={{ marginBottom: { xs: 1, md: 2 } }}>
        <HandDisplay
          hand={north}
          position="北"
          isActive={currentBidder === '北'}
          isHuman={humanPosition === '北'}
          isDealer={dealer === '北'}
          isPartner={humanPosition && getPartnerPosition(humanPosition) === '北'}
          showContent={shouldShowHandContent('北')}
        />
      </Box>

      {/* Middle row: West + Table + East */}
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
        {/* West hand */}
        <Box className="west-hand">
          <HandDisplay
            hand={west}
            position="西"
            isActive={currentBidder === '西'}
            isHuman={humanPosition === '西'}
            isDealer={dealer === '西'}
            isPartner={humanPosition && getPartnerPosition(humanPosition) === '西'}
            showContent={shouldShowHandContent('西')}
          />
        </Box>

        {/* Table center with bidding table */}
        <Box className="table-center">
          <Box className="table-border" sx={{
            width: { xs: 200, md: 280 },
            minHeight: { xs: 150, md: 280 },
            border: '3px solid rgba(255, 255, 255, 0.5)',
            borderRadius: 2,
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'flex-start',
            background: 'rgba(255, 255, 255, 0.95)',
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

        {/* East hand */}
        <Box className="east-hand">
          <HandDisplay
            hand={east}
            position="东"
            isActive={currentBidder === '东'}
            isHuman={humanPosition === '东'}
            isDealer={dealer === '东'}
            isPartner={humanPosition && getPartnerPosition(humanPosition) === '东'}
            showContent={shouldShowHandContent('东')}
          />
        </Box>
      </Box>

      {/* South hand */}
      <Box className="south-hand" sx={{ marginTop: { xs: 1, md: 2 } }}>
        <HandDisplay
          hand={south}
          position="南"
          isActive={currentBidder === '南'}
          isHuman={humanPosition === '南'}
          isDealer={dealer === '南'}
          isPartner={humanPosition && getPartnerPosition(humanPosition) === '南'}
          showContent={shouldShowHandContent('南')}
        />
      </Box>
    </Box>
  );
}

export default CardTable;