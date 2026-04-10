import React, { useState } from 'react';
import { Box, Button, CircularProgress, TextField, ToggleButton, ToggleButtonGroup, Typography, IconButton, Tooltip, useTheme, useMediaQuery } from '@mui/material';
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep';
import HandDisplay from './HandDisplay';
import DoubleDummyTable from './DoubleDummyTable';

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
  showDoubleDummy,
  doubleDummyResult,
  doubleDummyLoading,
  biddingTotalTime,
  positionRoles,
  onPositionRoleChange,
  onDealerChange,
  onClearAllHands,
  setHands,
  biddingStarted,
  stopBidding,
  startBidding,
}) {
  const [handInputs, setHandInputs] = useState({
    '南': '',
    '北': '',
    '东': '',
    '西': ''
  })
  const [inputErrors, setInputErrors] = useState({
    '南': '',
    '北': '',
    '东': '',
    '西': ''
  })

  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'))
  
  const handBoxSize = isMobile ? 'calc((100vw - 12px) * 0.42)' : 160
  const centerBoxSize = isMobile ? 120 : 220

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

  const isAIPosition = (position) => {
    return positionRoles && positionRoles[position] === 'ai'
  }

  const hasHand = (position) => {
    const hand = hands[position]
    return hand && (hand.spades || hand.hearts || hand.diamonds || hand.clubs)
  }

  const parseHandInput = (input) => {
    const suits = input.trim().split(/\s+/)
    if (suits.length !== 4) {
      return { valid: false, error: '请输入4个花色，用空格分隔' }
    }
    
    const validCards = /^[AKQJTakqjt2-9\-]+$/
    for (const suit of suits) {
      if (suit !== '-' && !validCards.test(suit)) {
        return { valid: false, error: '包含无效字符' }
      }
    }
    
    const calculateHCP = (cards) => {
      let hcp = 0
      for (const card of cards.toUpperCase()) {
        if (card === 'A') hcp += 4
        else if (card === 'K') hcp += 3
        else if (card === 'Q') hcp += 2
        else if (card === 'J') hcp += 1
      }
      return hcp
    }
    
    const spades = suits[0] === '-' ? '' : suits[0].toUpperCase()
    const hearts = suits[1] === '-' ? '' : suits[1].toUpperCase()
    const diamonds = suits[2] === '-' ? '' : suits[2].toUpperCase()
    const clubs = suits[3] === '-' ? '' : suits[3].toUpperCase()
    
    return {
      valid: true,
      hand: {
        spades,
        hearts,
        diamonds,
        clubs,
        hcp: calculateHCP(spades + hearts + diamonds + clubs)
      }
    }
  }

  const handleHandInputChange = (position, value) => {
    setHandInputs(prev => ({ ...prev, [position]: value }))
    setInputErrors(prev => ({ ...prev, [position]: '' }))
  }

  const handleHandInputSubmit = (position) => {
    const result = parseHandInput(handInputs[position])
    if (!result.valid) {
      setInputErrors(prev => ({ ...prev, [position]: result.error }))
      return
    }
    
    setHands(prev => ({
      ...prev,
      [position]: result.hand
    }))
    setHandInputs(prev => ({ ...prev, [position]: '' }))
  }

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
    const isAI = isAIPosition(position)
    const hasHandData = hasHand(position)
    const showInput = isAI && !hasHandData && !biddingStarted
    const isHuman = positionRoles && positionRoles[position] === 'human'
    
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
        
        <Box sx={{
          bgcolor: 'rgba(255, 255, 255, 0.98)',
          borderRadius: 2,
          p: isMobile ? 0.5 : 1,
          width: handBoxSize,
          height: handBoxSize,
          flexShrink: 0,
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          display: 'flex',
          flexDirection: 'column',
          border: '1px solid rgba(255,255,255,0.5)',
          backdropFilter: 'blur(10px)',
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
            <Typography 
              variant="subtitle2" 
              sx={{ 
                fontWeight: 600, 
                fontSize: '0.85rem',
                cursor: onDealerChange && (!biddingStarted || stopBidding) ? 'pointer' : 'default',
                transition: 'color 0.2s',
                '&:hover': onDealerChange && (!biddingStarted || stopBidding) ? { color: 'primary.main' } : {}
              }}
              onClick={() => onDealerChange && (!biddingStarted || stopBidding) && onDealerChange(position)}
            >
              {position}家
              {dealer === position && ' *'}
              {hasHandData && hand && hand.hcp !== undefined && !showInput && ` (${hand.hcp})`}
            </Typography>
            {onPositionRoleChange && (
              <ToggleButtonGroup
                value={positionRoles[position]}
                exclusive
                onChange={(e, newRole) => {
                  if (newRole !== null) {
                    onPositionRoleChange(position, newRole)
                  }
                }}
                size="small"
                sx={{ 
                  height: 24,
                  '& .MuiToggleButton-root': {
                    px: 0.8,
                    py: 0.3,
                    fontSize: '0.7rem',
                    fontWeight: 500,
                    borderRadius: 1,
                  }
                }}
              >
                <ToggleButton value="ai" sx={{ minWidth: 32 }}>AI</ToggleButton>
                <ToggleButton value="human" sx={{ minWidth: 32 }}>人类</ToggleButton>
              </ToggleButtonGroup>
            )}
          </Box>
          
          {showInput ? (
            <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative' }}>
              {!handInputs[position] && (
                <Box sx={{
                  position: 'absolute',
                  top: '8px',
                  left: '8px',
                  pointerEvents: 'none',
                  fontSize: '0.75rem',
                  zIndex: 1,
                }}>
                  <span style={{ color: '#000' }}>♠</span>{' '}
                  <span style={{ color: '#d32f2f' }}>♥</span>{' '}
                  <span style={{ color: '#f57c00' }}>♦</span>{' '}
                  <span style={{ color: '#000' }}>♣</span>
                </Box>
              )}
              <TextField
                size="small"
                value={handInputs[position]}
                onChange={(e) => handleHandInputChange(position, e.target.value)}
                error={!!inputErrors[position]}
                helperText={inputErrors[position] || '如: AKQJ - T87 654'}
                fullWidth
                multiline
                maxRows={2}
                sx={{ 
                  '& .MuiInputBase-input': { fontSize: '0.75rem', padding: '4px' },
                  '& .MuiFormHelperText-root': { fontSize: '0.6rem', margin: '2px 0 0 0' }
                }}
              />
              <Button 
                size="small" 
                variant="contained" 
                sx={{ mt: 0.5, fontSize: '0.7rem', py: 0.3 }}
                onClick={() => handleHandInputSubmit(position)}
                disabled={!handInputs[position].trim()}
              >
                确认
              </Button>
            </Box>
          ) : isHuman && !hasHandData ? (
            <Box sx={{ 
              flex: 1,
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center', 
              color: 'text.secondary'
            }}>
              <Typography variant="body2" sx={{ fontSize: '0.8rem' }}>未知</Typography>
            </Box>
          ) : (
            <Box sx={{ flex: 1 }}>
              <HandDisplay
                hand={hand}
                position={position}
                isActive={currentBidder === position}
                isHuman={isHuman}
                isDealer={dealer === position}
                isPartner={humanPosition && getPartnerPosition(humanPosition) === position}
                showContent={shouldShowHandContent(position)}
                hideTitle={true}
              />
            </Box>
          )}
        </Box>
      </Box>
    );
  };

  return (
    <Box className="card-table-container" sx={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: isMobile ? 'stretch' : 'center',
      justifyContent: 'center',
      padding: isMobile ? 0.5 : 1,
      background: scheme.table.background,
      borderRadius: 2,
      boxShadow: 8,
      width: isMobile ? 'calc(100vw - 16px)' : 'auto',
      maxWidth: '100%',
      maxHeight: '100%',
      position: 'relative',
      overflow: isMobile ? 'visible' : 'hidden',
    }}>
      {onClearAllHands && (!biddingStarted || (checkBiddingComplete && checkBiddingComplete())) && (
        <Box sx={{
          position: 'absolute',
          top: 8,
          left: 8,
          zIndex: 10,
        }}>
          <Tooltip title="清除所有手牌">
            <IconButton
              size="small"
              onClick={onClearAllHands}
              sx={{
                bgcolor: 'rgba(255, 255, 255, 0.9)',
                '&:hover': { bgcolor: 'rgba(255, 255, 255, 1)' }
              }}
            >
              <DeleteSweepIcon />
            </IconButton>
          </Tooltip>
        </Box>
      )}
      
      {checkBiddingComplete && checkBiddingComplete() && (
        <Box sx={{
          position: 'absolute',
          top: 8,
          right: 8,
          zIndex: 10,
          display: 'flex',
          alignItems: 'center',
          gap: 1,
        }}>
          {biddingTotalTime !== null && (
            <Box sx={{
              bgcolor: 'rgba(0, 0, 0, 0.6)',
              color: 'white',
              px: 1.5,
              py: 0.5,
              borderRadius: 1,
              fontSize: '0.85rem',
              fontWeight: 'medium',
            }}>
              ⏱ {Math.floor(biddingTotalTime / 60)}:{(biddingTotalTime % 60).toString().padStart(2, '0')}
            </Box>
          )}
          {outputFormatsLoading && <CircularProgress size={20} sx={{ color: 'white' }} />}
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

      {isMobile ? (
        <>
          <Box sx={{ display: 'flex', justifyContent: 'center', width: '100%' }}>
            {renderHandWithStatus(north, '北', { mb: '12px' })}
          </Box>
          
          <Box sx={{ display: 'flex', gap: '4px', width: '100%', mb: '12px', justifyContent: 'center' }}>
            {renderHandWithStatus(west, '西')}
            {renderHandWithStatus(east, '东')}
          </Box>
          
          <Box sx={{ display: 'flex', justifyContent: 'center', width: '100%' }}>
            {renderHandWithStatus(south, '南', { mb: '12px' })}
          </Box>
          
          <Box className="table-center" sx={{ width: '100%', display: 'flex', justifyContent: 'center' }}>
            <Box className="table-border" sx={{
              width: handBoxSize,
              minWidth: handBoxSize,
              flexShrink: 0,
              minHeight: 80,
              border: scheme.table.border,
              borderRadius: 2,
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'flex-start',
              background: scheme.table.centerBg,
              padding: 1,
              overflowY: 'auto',
            }}>
              {showDoubleDummy ? (
                doubleDummyLoading ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', width: '100%' }}>
                    <CircularProgress size={24} />
                  </Box>
                ) : doubleDummyResult ? (
                  <DoubleDummyTable tableData={doubleDummyResult} />
                ) : (
                  <div style={{ color: '#666', fontStyle: 'italic', textAlign: 'center', padding: 3 }}>
                    无分析结果
                  </div>
                )
              ) : renderBiddingTable ? renderBiddingTable() : (
                <div style={{ color: '#666', fontStyle: 'italic', textAlign: 'center', padding: 3 }}>
                  等待叫牌...
                </div>
              )}
            </Box>
          </Box>
        </>
      ) : (
        <>
          {renderHandWithStatus(north, '北', { mb: '8px' })}

          <Box className="middle-row" sx={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            width: '100%',
            maxWidth: 800,
            gap: '8px',
          }}>
            {renderHandWithStatus(west, '西')}

            <Box className="table-center">
              <Box className="table-border" sx={{
                width: centerBoxSize,
                height: centerBoxSize,
                border: scheme.table.border,
                borderRadius: 2,
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'flex-start',
                background: scheme.table.centerBg,
                padding: 1,
                overflowY: 'auto',
              }}>
                {showDoubleDummy ? (
                  doubleDummyLoading ? (
                    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', width: '100%' }}>
                      <CircularProgress size={24} />
                    </Box>
                  ) : doubleDummyResult ? (
                    <DoubleDummyTable tableData={doubleDummyResult} />
                  ) : (
                    <div style={{ color: '#666', fontStyle: 'italic', textAlign: 'center', padding: 3 }}>
                      无分析结果
                    </div>
                  )
                ) : renderBiddingTable ? renderBiddingTable() : (
                  <div style={{ color: '#666', fontStyle: 'italic', textAlign: 'center', padding: 3 }}>
                    等待叫牌...
                  </div>
                )}
              </Box>
            </Box>

            {renderHandWithStatus(east, '东')}
          </Box>

          {renderHandWithStatus(south, '南', { mt: '8px' })}
        </>
      )}
    </Box>
  );
}

export default CardTable;
