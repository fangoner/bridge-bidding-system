import React from 'react';
import { Box, Typography } from '@mui/material';
import { styled } from '@mui/material/styles';

const HandCard = styled(Box, {
  shouldForwardProp: (prop) => !['isActive', 'isHuman', 'isPartner'].includes(prop),
})(({ theme, isActive, isHuman, isPartner }) => ({
  background: 'white',
  borderRadius: theme.shape.borderRadius,
  padding: theme.spacing(0.5),
  boxShadow: 'none',
  width: '100%',
  fontFamily: '"Courier New", Courier, monospace',
  transition: 'all 0.3s ease',
  ...(isActive && {
    boxShadow: `0 0 0 3px #ffd700, ${theme.shadows[2]}`,
    transform: 'scale(1.02)',
  }),
  ...(isHuman && {
    background: 'linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%)',
  }),
  ...(isPartner && {
    background: 'linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%)',
  }),
}));

const HandTitle = styled(Typography)(({ theme }) => ({
  fontWeight: 'bold',
  marginBottom: theme.spacing(1),
  color: theme.palette.text.primary,
  borderBottom: `1px solid ${theme.palette.divider}`,
  paddingBottom: theme.spacing(0.5),
}));

const SuitLine = styled(Box)(({ theme }) => ({
  fontSize: '0.95rem',
  lineHeight: 1.4,
  whiteSpace: 'nowrap',
}));

const SuitSymbol = styled('span', {
  shouldForwardProp: (prop) => prop !== 'color',
})(({ theme, color }) => ({
  color,
  fontWeight: 'bold',
  marginRight: theme.spacing(0.5),
}));

const HiddenHand = styled(Box)(({ theme }) => ({
  height: '100%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: theme.palette.text.secondary,
  fontStyle: 'italic',
}));

/**
 * HandDisplay component for displaying a bridge hand
 * @param {Object} props
 * @param {Object} props.hand - Hand object with hcp, spades, hearts, diamonds, clubs, display
 * @param {string} props.position - Position: '北', '南', '东', '西'
 * @param {boolean} props.isActive - Whether this position is currently bidding
 * @param {boolean} props.isHuman - Whether this position is the human player
 * @param {boolean} props.isDealer - Whether this position is the dealer
 * @param {boolean} props.isPartner - Whether this position is the human's partner
 * @param {boolean} props.showContent - Whether to show hand content or hide it
 * @param {React.ReactNode} props.titleExtra - Extra content to display next to the title
 * @param {boolean} props.hideTitle - Whether to hide the title
 */
function HandDisplay({
  hand,
  position,
  isActive = false,
  isHuman = false,
  isDealer = false,
  isPartner = false,
  showContent = true,
  titleExtra = null,
  hideTitle = false,
}) {
  const suitColors = {
    spades: '#000000',
    hearts: '#d32f2f',
    diamonds: '#d32f2f', // Using red for diamonds as well (could use orange)
    clubs: '#000000',
  };

  const hasCards = hand && (hand.spades || hand.hearts || hand.diamonds || hand.clubs);

  return (
    <HandCard
      isActive={isActive}
      isHuman={isHuman}
      isPartner={isPartner}
      className={`hand-card ${isActive ? 'active' : ''} ${isHuman ? 'human' : ''} ${isPartner ? 'partner' : ''}`}
    >
      {!hideTitle && (
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <HandTitle variant="subtitle2" className="hand-title" sx={{ mb: 0, borderBottom: 'none', pb: 0 }}>
            {position}{isDealer ? '*' : ''} {showContent && hasCards ? `(${hand.hcp})` : ''}
          </HandTitle>
          {titleExtra}
        </Box>
      )}

      {showContent && hasCards ? (
        <>
          <SuitLine className="suit-line">
            <SuitSymbol color={suitColors.spades} className="suit-black">♠</SuitSymbol>
            {hand.spades || '-'}
          </SuitLine>
          <SuitLine className="suit-line">
            <SuitSymbol color={suitColors.hearts} className="suit-red">♥</SuitSymbol>
            {hand.hearts || '-'}
          </SuitLine>
          <SuitLine className="suit-line">
            <SuitSymbol color={suitColors.diamonds} className="suit-red">♦</SuitSymbol>
            {hand.diamonds || '-'}
          </SuitLine>
          <SuitLine className="suit-line">
            <SuitSymbol color={suitColors.clubs} className="suit-black">♣</SuitSymbol>
            {hand.clubs || '-'}
          </SuitLine>
        </>
      ) : (
        <HiddenHand className="hidden-hand">
          <Typography variant="body2" color="text.secondary" align="center">
            {hasCards ? '[隐藏]' : '[待输入]'}
          </Typography>
        </HiddenHand>
      )}
    </HandCard>
  );
}

export default HandDisplay;