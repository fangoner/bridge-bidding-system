import React from 'react';
import { Box, Typography } from '@mui/material';
import { styled } from '@mui/material/styles';

const HandCard = styled(Box, {
  shouldForwardProp: (prop) => !['isActive', 'isHuman', 'isPartner'].includes(prop),
})(({ theme, isActive, isHuman, isPartner }) => ({
  background: 'white',
  borderRadius: 12,
  padding: theme.spacing(1),
  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
  width: '100%',
  fontFamily: '"SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace',
  transition: 'all 0.25s ease',
  border: '1px solid',
  borderColor: '#e2e8f0',
  ...(isActive && {
    boxShadow: '0 0 0 2px #6366f1, 0 4px 12px rgba(99, 102, 241, 0.2)',
    transform: 'scale(1.02)',
    borderColor: '#6366f1',
  }),
  ...(isHuman && {
    background: 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)',
    borderColor: '#a5b4fc',
  }),
  ...(isPartner && {
    background: 'linear-gradient(135deg, #fdf4ff 0%, #fae8ff 100%)',
    borderColor: '#e879f9',
  }),
}));

const HandTitle = styled(Typography)(({ theme }) => ({
  fontWeight: 600,
  marginBottom: theme.spacing(0.5),
  color: '#1e293b',
  fontSize: '0.8rem',
  letterSpacing: '0.01em',
}));

const SuitLine = styled(Box)(({ theme }) => ({
  fontSize: '0.85rem',
  lineHeight: 1.4,
  whiteSpace: 'nowrap',
  display: 'flex',
  alignItems: 'center',
  gap: '3px',
}));

const SuitSymbol = styled('span', {
  shouldForwardProp: (prop) => prop !== 'suitColor',
})(({ theme, suitColor }) => ({
  fontSize: '0.9rem',
  fontWeight: 700,
  width: '14px',
  textAlign: 'center',
  flexShrink: 0,
}));

const HiddenHand = styled(Box)(({ theme }) => ({
  height: '100%',
  minHeight: '50px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: '#94a3b8',
}));

const HCPBadge = styled(Box)(({ theme }) => ({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: '2px 8px',
  borderRadius: 12,
  background: 'linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%)',
  fontSize: '0.75rem',
  fontWeight: 600,
  color: '#475569',
  marginLeft: 'auto',
}));

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
    spades: '#1e293b',
    hearts: '#dc2626',
    diamonds: '#ea580c',
    clubs: '#16a34a',
  };

  const hasCards = hand && (hand.spades || hand.hearts || hand.diamonds || hand.clubs);

  return (
    <HandCard
      isActive={isActive}
      isHuman={isHuman}
      isPartner={isPartner}
    >
      {!hideTitle && (
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
          <HandTitle>
            {position}{isDealer ? '*' : ''}
          </HandTitle>
          {showContent && hasCards && hand.hcp !== undefined && (
            <HCPBadge>{hand.hcp}点</HCPBadge>
          )}
          {titleExtra}
        </Box>
      )}

      {showContent && hasCards ? (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.3 }}>
          <SuitLine>
            <SuitSymbol suitColor={suitColors.spades} sx={{ color: suitColors.spades }}>♠</SuitSymbol>
            <Box component="span" sx={{ color: suitColors.spades, fontWeight: 500 }}>
              {hand.spades || '-'}
            </Box>
          </SuitLine>
          <SuitLine>
            <SuitSymbol suitColor={suitColors.hearts} sx={{ color: suitColors.hearts }}>♥</SuitSymbol>
            <Box component="span" sx={{ color: suitColors.hearts, fontWeight: 500 }}>
              {hand.hearts || '-'}
            </Box>
          </SuitLine>
          <SuitLine>
            <SuitSymbol suitColor={suitColors.diamonds} sx={{ color: suitColors.diamonds }}>♦</SuitSymbol>
            <Box component="span" sx={{ color: suitColors.diamonds, fontWeight: 500 }}>
              {hand.diamonds || '-'}
            </Box>
          </SuitLine>
          <SuitLine>
            <SuitSymbol suitColor={suitColors.clubs} sx={{ color: suitColors.clubs }}>♣</SuitSymbol>
            <Box component="span" sx={{ color: suitColors.clubs, fontWeight: 500 }}>
              {hand.clubs || '-'}
            </Box>
          </SuitLine>
        </Box>
      ) : (
        <HiddenHand>
          <Typography variant="body2" sx={{ color: '#94a3b8', fontSize: '0.8rem' }}>
            {hasCards ? '[隐藏]' : '[待输入]'}
          </Typography>
        </HiddenHand>
      )}
    </HandCard>
  );
}

export default HandDisplay;
