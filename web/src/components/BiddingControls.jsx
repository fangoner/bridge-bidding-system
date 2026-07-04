import React from 'react';
import {
  Box,
  Paper,
  Typography,
  Button,
  TextField,
  Alert,
  Divider,
  CircularProgress,
  useTheme,
  alpha,
} from '@mui/material';
import { styled } from '@mui/material/styles';
import { isHumanPosition, hasAnyHuman } from '../utils/position';

const getBidColor = (bid, theme) => {
  if (!bid) return {};
  const isDark = theme.palette.mode === 'dark';
  const suit = bid.slice(-1);

  // Dark mode: muted but distinct tones on dark backgrounds
  if (isDark) {
    if (suit === 'H') {
      return { color: '#fca5a5', bgColor: 'rgba(239,68,68,0.15)', borderColor: 'rgba(239,68,68,0.25)' };
    }
    if (suit === 'D') {
      return { color: '#a78bfa', bgColor: 'rgba(124,58,237,0.15)', borderColor: 'rgba(124,58,237,0.25)' };
    }
    if (suit === 'S' || suit === 'C') {
      return { color: '#cbd5e1', bgColor: 'rgba(148,163,184,0.12)', borderColor: 'rgba(148,163,184,0.2)' };
    }
    if (suit === 'T') {
      return { color: '#b0bec5', bgColor: 'rgba(144,164,174,0.15)', borderColor: 'rgba(144,164,174,0.25)' };
    }
    if (bid === 'X') {
      return { color: '#fca5a5', bgColor: 'rgba(239,68,68,0.15)', borderColor: 'rgba(239,68,68,0.3)' };
    }
    if (bid === 'XX') {
      return { color: '#f87171', bgColor: 'rgba(239,68,68,0.2)', borderColor: 'rgba(239,68,68,0.35)' };
    }
    if (bid === 'pass') {
      return { color: '#6ee7b7', bgColor: 'rgba(16,185,129,0.12)', borderColor: 'rgba(16,185,129,0.2)' };
    }
    return { color: '#94a3b8', bgColor: 'rgba(148,163,184,0.1)', borderColor: 'rgba(148,163,184,0.15)' };
  }

  // Light mode
  if (suit === 'H') {
    return { color: '#dc2626', bgColor: '#fef2f2', borderColor: '#fca5a5' };
  }
  if (suit === 'D') {
    return { color: '#7c3aed', bgColor: '#f5f3ff', borderColor: '#a78bfa' };
  }
  if (suit === 'S' || suit === 'C') {
    return { color: '#1e293b', bgColor: '#f1f5f9', borderColor: '#94a3b8' };
  }
  if (suit === 'T') {
    return { color: '#455a64', bgColor: '#eceff1', borderColor: '#90a4ae' };
  }
  if (bid === 'X') {
    return { color: '#dc2626', bgColor: '#fef2f2', borderColor: '#fca5a5' };
  }
  if (bid === 'XX') {
    return { color: '#dc2626', bgColor: '#fee2e2', borderColor: '#f87171' };
  }
  if (bid === 'pass') {
    return { color: '#059669', bgColor: '#ecfdf5', borderColor: '#6ee7b7' };
  }
  return { color: '#475569', bgColor: '#f8fafc', borderColor: '#cbd5e1' };
};

const BidButton = styled(Button, {
  shouldForwardProp: (prop) => !['bidColor', 'isActive'].includes(prop),
})(({ theme, bidColor, isActive }) => ({
  minWidth: '44px',
  width: '44px',
  height: '32px',
  padding: '4px 8px',
  fontSize: '0.8rem',
  fontWeight: 600,
  borderRadius: '8px',
  transition: 'all 0.2s ease',
  color: bidColor?.color || '#475569',
  backgroundColor: bidColor?.bgColor || '#f8fafc',
  border: `1.5px solid ${bidColor?.borderColor || '#cbd5e1'}`,
  boxShadow: '0 1px 2px rgba(0,0,0,0.05)',
  '&:hover': {
    backgroundColor: bidColor?.bgColor || '#f8fafc',
    transform: 'translateY(-1px)',
    boxShadow: '0 4px 8px rgba(0,0,0,0.1)',
    border: `1.5px solid ${bidColor?.color || '#475569'}`,
  },
  '&:disabled': {
    opacity: 0.5,
    transform: 'none',
    boxShadow: 'none',
  },
  ...(isActive && {
    transform: 'scale(1.05)',
    boxShadow: `0 0 0 2px ${bidColor?.color || '#475569'}`,
  }),
}));

const CompactBidButton = styled(Button, {
  shouldForwardProp: (prop) => !['bidColor'].includes(prop),
})(({ theme, bidColor }) => ({
  minWidth: '28px',
  width: '100%',
  height: '28px',
  padding: '2px 2px',
  fontSize: '0.7rem',
  fontWeight: 600,
  borderRadius: '6px',
  transition: 'all 0.15s ease',
  color: bidColor?.color || '#475569',
  backgroundColor: bidColor?.bgColor || '#f8fafc',
  border: `1px solid ${bidColor?.borderColor || '#cbd5e1'}`,
  '&:hover': {
    backgroundColor: bidColor?.bgColor || '#f8fafc',
    transform: 'scale(1.05)',
  },
  '&:disabled': {
    opacity: 0.4,
    transform: 'none',
  },
}));

function BiddingControls({
  hands,
  currentBidder,
  positionRoles,
    checkBiddingComplete,
  addBid,
    getFinalContract,
  bidSuggestion,
  suggestionLoading,
  stopBidding,
    customBidMeaning,
  setCustomBidMeaning,
  isVerticalLayout = false,
  hideJFPanel = false,
}) {
  if (!hands) return null;

  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const bidLevels = [
    ['1C', '1D', '1H', '1S', '1NT'],
    ['2C', '2D', '2H', '2S', '2NT'],
    ['3C', '3D', '3H', '3S', '3NT'],
    ['4C', '4D', '4H', '4S', '4NT'],
    ['5C', '5D', '5H', '5S', '5NT'],
    ['6C', '6D', '6H', '6S', '6NT'],
    ['7C', '7D', '7H', '7S', '7NT'],
  ];
  const specialBids = ['X', 'XX', 'pass'];

  const allBidsCompact = [
    ['1C', '1D', '1H', '1S', '1NT', null, '2C', '2D', '2H', '2S', '2NT'],
    ['3C', '3D', '3H', '3S', '3NT', null, '4C', '4D', '4H', '4S', '4NT'],
    ['5C', '5D', '5H', '5S', '5NT', null, '6C', '6D', '6H', '6S', '6NT'],
    ['7C', '7D', '7H', '7S', '7NT', null, 'X', 'XX', 'pass', null, null],
  ];

  const isHumanTurn = isHumanPosition(positionRoles, currentBidder)
  const finalContract = getFinalContract();

  return (
    <Box sx={{
      display: 'flex',
      flexDirection: isVerticalLayout ? 'column' : { xs: 'column', md: 'row' },
      gap: isVerticalLayout ? 2 : 1.5,
      mt: isVerticalLayout ? 0 : 3,
      alignItems: isVerticalLayout ? 'stretch' : { xs: 'stretch', md: 'flex-start' },
      width: '100%',
      justifyContent: 'flex-start',
      height: isVerticalLayout ? 'auto' : 'auto',
    }}>
      {hasAnyHuman(positionRoles) && (
      <Paper elevation={0} sx={{
        p: isVerticalLayout ? 1.5 : 2,
        width: isVerticalLayout ? '100%' : { xs: '100%', md: '280px' },
        height: 'auto',
        flex: 'none',
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        minHeight: isVerticalLayout ? 0 : 'auto',
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 3,
        background: isDark ? 'rgba(17,24,39,0.65)' : 'rgba(255,255,255,0.65)',
        backdropFilter: 'blur(16px) saturate(160%)',
        boxSizing: 'border-box'
      }}>
        {!checkBiddingComplete() ? (
          <>
            <Typography variant="h6" gutterBottom sx={{ 
              fontSize: isVerticalLayout ? '1rem' : '1rem',
              fontWeight: 600,
              color: 'text.primary',
              display: 'flex',
              alignItems: 'center',
              gap: 1,
            }}>
              <Box component="span" sx={{ 
                width: 8, 
                height: 8, 
                borderRadius: '50%', 
                bgcolor: isHumanTurn ? 'success.main' : 'grey.400',
                animation: isHumanTurn ? 'pulse 1.5s infinite' : 'none',
                '@keyframes pulse': {
                  '0%': { opacity: 1 },
                  '50%': { opacity: 0.5 },
                  '100%': { opacity: 1 },
                },
              }} />
              叫牌控制 - {currentBidder}家 {isHumanTurn ? '(你的回合)' : '(AI)'}
            </Typography>

            <Box sx={{ 
              display: isVerticalLayout ? 'grid' : 'flex',
              flexDirection: isVerticalLayout ? undefined : 'column',
              gridTemplateColumns: isVerticalLayout ? 'repeat(11, 1fr)' : undefined,
              gap: isVerticalLayout ? '4px' : 0.8,
              width: '100%',
              maxWidth: '100%',
              alignItems: isVerticalLayout ? undefined : 'center',
              justifyContent: isVerticalLayout ? undefined : 'center',
              boxSizing: 'border-box'
            }}>
              {isVerticalLayout ? (
                allBidsCompact.flat().map((bid, index) => {
                  const bidColor = getBidColor(bid, theme);
                  return bid === null ? (
                    <Box key={index} />
                  ) : (
                    <CompactBidButton
                      key={bid + index}
                      bidColor={bidColor}
                      onClick={() => addBid(bid)}
                      disabled={!isHumanTurn && hasAnyHuman(positionRoles)}
                    >
                      {bid}
                    </CompactBidButton>
                  )
                })
              ) : (
                <>
                  {bidLevels.map((level, levelIndex) => (
                    <Box key={levelIndex} sx={{ display: 'flex', gap: 0.8 }}>
                      {level.map((bid) => {
                        const bidColor = getBidColor(bid, theme);
                        return (
                          <BidButton
                            key={bid}
                            bidColor={bidColor}
                            onClick={() => addBid(bid)}
                            disabled={!isHumanTurn && hasAnyHuman(positionRoles)}
                          >
                            {bid}
                          </BidButton>
                        );
                      })}
                    </Box>
                  ))}
                  <Box sx={{ display: 'flex', gap: 0.8, mt: 1.5 }}>
                    {specialBids.map((bid) => {
                      const bidColor = getBidColor(bid, theme);
                      return (
                        <BidButton
                          key={bid}
                          bidColor={bidColor}
                          onClick={() => addBid(bid)}
                          disabled={!isHumanTurn && hasAnyHuman(positionRoles)}
                          sx={{ width: bid === 'pass' ? '60px' : '44px' }}
                        >
                          {bid}
                        </BidButton>
                      );
                    })}
                  </Box>
                </>
              )}
            </Box>

            {hasAnyHuman(positionRoles) && isHumanTurn && (
              <Box sx={{ mt: isVerticalLayout ? 1 : 2 }}>
                <TextField
                  size="small"
                  label="自定义叫牌含义（可选）"
                  placeholder="输入后跳过AI提取"
                  value={customBidMeaning}
                  onChange={(e) => setCustomBidMeaning(e.target.value)}
                  fullWidth
                  multiline
                  maxRows={2}
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      borderRadius: 2,
                      fontSize: '0.875rem',
                    },
                  }}
                />
              </Box>
            )}

            {hasAnyHuman(positionRoles) && !isHumanTurn && stopBidding && (
              <Alert severity="info" sx={{ mt: isVerticalLayout ? 1 : 2, py: isVerticalLayout ? 0.5 : undefined, borderRadius: 2 }}>
                叫牌已暂停
              </Alert>
            )}
          </>
        ) : (
          <>
            <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
              叫牌结束
            </Typography>
            {finalContract ? (
              <Box sx={{
                mt: 2,
                p: 2,
                borderRadius: 2,
                background: alpha(theme.palette.success.main, isDark ? 0.12 : 0.08),
                border: `1px solid ${alpha(theme.palette.success.main, isDark ? 0.3 : 0.25)}`,
              }}>
                <Typography variant="h6" sx={{ color: theme.palette.success.main, fontWeight: 600, mb: 1 }}>
                  最终定约: {finalContract.level}{finalContract.suit}{finalContract.isRedouble ? 'XX' : finalContract.isDouble ? 'X' : ''}
                </Typography>
                <Typography variant="body2" sx={{ color: isDark ? theme.palette.success.light : theme.palette.success.dark }}>
                  定约方: {finalContract.partnership} | 庄家: {finalContract.declarer}家
                </Typography>
              </Box>
            ) : (
              <Box sx={{
                mt: 2,
                p: 2,
                borderRadius: 2,
                background: alpha(theme.palette.info.main, isDark ? 0.12 : 0.08),
                border: `1px solid ${alpha(theme.palette.info.main, isDark ? 0.3 : 0.25)}`,
              }}>
                <Typography variant="body1" sx={{ color: isDark ? theme.palette.info.light : theme.palette.info.dark }}>
                  叫牌结束，无最终定约（全部pass）
                </Typography>
              </Box>
            )}
          </>
        )}
      </Paper>
      )}

      {!hideJFPanel && hasAnyHuman(positionRoles) && !checkBiddingComplete() && (
        <Paper elevation={0} sx={{
          p: 2,
          flex: isVerticalLayout ? '1 1 auto' : '1 1 auto',
          height: isVerticalLayout ? 'auto' : '420px',
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          minHeight: isVerticalLayout ? 0 : 'auto',
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 3,
          background: isDark ? 'rgba(17,24,39,0.65)' : 'rgba(255,255,255,0.65)',
        backdropFilter: 'blur(16px) saturate(160%)',
        }}>
          <Typography variant="h6" gutterBottom sx={{ flexShrink: 0, fontWeight: 600 }}>
            JF约定片段
          </Typography>
          <Box sx={{ flex: 1, overflow: 'auto', maxWidth: '100%', minWidth: 0, minHeight: 0 }}>
            {suggestionLoading ? (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, justifyContent: 'center', height: '100%' }}>
                <CircularProgress size={20} />
                <Typography variant="body2">获取JF约定片段中...</Typography>
              </Box>
            ) : bidSuggestion ? (
              <Box>
                <Typography variant="subtitle2" gutterBottom sx={{ color: theme.palette.text.secondary, fontWeight: 500 }}>
                  检索关键字: <strong style={{ color: theme.palette.primary.main }}>{bidSuggestion.keyword}</strong>
                </Typography>
                {bidSuggestion.content ? (
                  <Box sx={{
                    mt: 1,
                    p: 1.5,
                    background: alpha(theme.palette.background.default, 0.5),
                    backdropFilter: 'blur(8px)',
                    borderRadius: 2,
                    border: `1px solid ${theme.palette.divider}`,
                    overflow: 'auto',
                    maxWidth: '100%' 
                  }}>
                    <Typography variant="body2" component="pre" sx={{
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      margin: 0,
                      fontFamily: 'inherit',
                      fontSize: '0.875rem',
                      maxWidth: '100%',
                      lineHeight: 1.6,
                    }}>
                      {bidSuggestion.content}
                    </Typography>
                  </Box>
                ) : (
                  <Alert severity="info" sx={{ mt: 1, borderRadius: 2 }}>
                    JF尚未提供建议
                  </Alert>
                )}
              </Box>
            ) : (
              <Alert severity="info" sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 2 }}>
                JF尚未提供建议
              </Alert>
            )}
          </Box>
        </Paper>
      )}
    </Box>
  );
}

export default BiddingControls;
