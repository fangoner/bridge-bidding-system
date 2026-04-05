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
} from '@mui/material';

function BiddingControls({
  hands,
  currentBidder,
  humanPosition,
  gameMode,
  checkBiddingComplete,
  addBid,
  getJFSuggestion,
  getFinalContract,
  bidSuggestion,
  suggestionLoading,
  stopBidding,
  isInPassedPartnership,
  customBidMeaning,
  setCustomBidMeaning,
  isVerticalLayout = false,
  hideJFPanel = false,
}) {
  if (!hands) return null;

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

  const isHumanTurn = humanPosition === currentBidder;
  const finalContract = getFinalContract();

  return (
    <Box sx={{
      display: 'flex',
      flexDirection: isVerticalLayout ? 'column' : { xs: 'column', md: 'row' },
      gap: isVerticalLayout ? 2 : 1,
      mt: isVerticalLayout ? 0 : 3,
      alignItems: isVerticalLayout ? 'stretch' : { xs: 'stretch', md: 'flex-start' },
      width: '100%',
      justifyContent: 'flex-start',
      height: isVerticalLayout ? '100%' : 'auto',
    }}>
      {/* Left: Bidding control panel - only show when humanPosition is set */}
      {humanPosition !== null && (
      <Paper elevation={2} sx={{
        p: 1.5,
        width: isVerticalLayout ? '100%' : { xs: '100%', md: '260px' },
        height: isVerticalLayout ? 'auto' : '420px',
        flex: isVerticalLayout ? '1 1 auto' : 'none',
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'auto',
        minHeight: isVerticalLayout ? 0 : 'auto',
      }}>
        {!checkBiddingComplete() ? (
          <>
            <Typography variant="h6" gutterBottom sx={{ fontSize: isVerticalLayout ? '1rem' : undefined }}>
              叫牌控制 - 当前: {currentBidder}家 {isHumanTurn ? '(你的回合)' : '(AI)'}
            </Typography>

            <Box sx={{ 
              display: isVerticalLayout ? 'grid' : 'flex',
              flexDirection: isVerticalLayout ? undefined : 'column',
              gridTemplateColumns: isVerticalLayout ? 'repeat(5, 40px) 8px repeat(5, 40px)' : undefined,
              gap: isVerticalLayout ? '2.4px' : 0.5,
              width: '100%',
              alignItems: isVerticalLayout ? undefined : 'center',
              justifyContent: isVerticalLayout ? 'center' : undefined,
              '& .MuiButton-root': {
                minWidth: isVerticalLayout ? '40px' : { xs: '46px', md: '44px' },
                width: isVerticalLayout ? '40px' : { xs: '46px', md: '44px' },
                height: isVerticalLayout ? '24px' : { xs: '40px', md: '30px' },
                padding: isVerticalLayout ? '2px 5px' : { xs: '4px 8px', md: '4px 7px' },
                fontSize: isVerticalLayout ? '0.75rem' : { xs: '0.85rem', md: '0.8rem' },
                fontWeight: 500,
                flexShrink: 0,
              }
            }}>
              {isVerticalLayout ? (
                allBidsCompact.flat().map((bid, index) => {
                  return bid === null ? (
                    <Box key={index} sx={{ width: '40px', height: '24px' }} />
                  ) : (
                    <Button
                      key={bid + index}
                      variant="outlined"
                      size="small"
                      onClick={() => addBid(bid)}
                      disabled={(!isHumanTurn && humanPosition !== null) || (gameMode === 'four' && isInPassedPartnership(currentBidder))}
                    >
                      {bid}
                    </Button>
                  )
                })
              ) : (
                <>
                  {bidLevels.map((level, levelIndex) => (
                    <Box key={levelIndex} sx={{ display: 'flex', gap: 0.5 }}>
                      {level.map((bid) => (
                        <Button
                          key={bid}
                          variant="outlined"
                          size="small"
                          onClick={() => addBid(bid)}
                          disabled={(!isHumanTurn && humanPosition !== null) || (gameMode === 'four' && isInPassedPartnership(currentBidder))}
                        >
                          {bid}
                        </Button>
                      ))}
                    </Box>
                  ))}
                  <Box sx={{ display: 'flex', gap: 0.5, mt: 1 }}>
                    {specialBids.map((bid) => (
                      <Button
                        key={bid}
                        variant="outlined"
                        size="small"
                        onClick={() => addBid(bid)}
                        disabled={(!isHumanTurn && humanPosition !== null) || (gameMode === 'four' && isInPassedPartnership(currentBidder))}
                      >
                        {bid}
                      </Button>
                    ))}
                  </Box>
                </>
              )}
            </Box>

            {humanPosition !== null && isHumanTurn && !isInPassedPartnership(currentBidder) && (
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
                />
              </Box>
            )}

            {gameMode === 'four' && isInPassedPartnership(currentBidder) && isHumanTurn && (
              <Alert severity="info" sx={{ mt: isVerticalLayout ? 1 : 2, py: isVerticalLayout ? 0.5 : undefined }}>
                您的搭档已相继pass，您将自动pass
              </Alert>
            )}

            {humanPosition !== null && !isHumanTurn && stopBidding && (
              <Alert severity="info" sx={{ mt: isVerticalLayout ? 1 : 2, py: isVerticalLayout ? 0.5 : undefined }}>
                叫牌已暂停
              </Alert>
            )}
          </>
        ) : (
          <>
            <Typography variant="h6" gutterBottom>
              叫牌结束
            </Typography>
            {finalContract ? (
              <Alert severity="success" sx={{ mt: 2 }}>
                <Typography variant="body1" gutterBottom>
                  最终定约: {finalContract.level}{finalContract.suit}{finalContract.isRedouble ? 'XX' : finalContract.isDouble ? 'X' : ''}
                </Typography>
                <Typography variant="body2">
                  定约方: {finalContract.partnership} | 庄家: {finalContract.declarer}家
                </Typography>
              </Alert>
            ) : (
              <Alert severity="info" sx={{ mt: 2 }}>
                叫牌结束，无最终定约（全部pass）
              </Alert>
            )}
          </>
        )}
      </Paper>
      )}

      {/* Middle: JF suggestion panel - show when human is playing and bidding not complete, and hideJFPanel is false */}
      {!hideJFPanel && humanPosition !== null && !checkBiddingComplete() && (
        <Paper elevation={2} sx={{
          p: 2,
          flex: isVerticalLayout ? '1 1 auto' : '1 1 auto',
          height: isVerticalLayout ? 'auto' : '420px',
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          minHeight: isVerticalLayout ? 0 : 'auto',
        }}>
          <Typography variant="h6" gutterBottom sx={{ flexShrink: 0 }}>
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
                <Typography variant="subtitle2" gutterBottom sx={{ color: '#666' }}>
                  检索关键字: <strong style={{ color: '#1976d2' }}>{bidSuggestion.keyword}</strong>
                </Typography>
                {bidSuggestion.content ? (
                  <Box sx={{ mt: 1, p: 1.5, background: '#fafafa', borderRadius: 1, border: '1px solid #e0e0e0', overflow: 'auto', maxWidth: '100%' }}>
                    <Typography variant="body2" component="pre" sx={{
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      margin: 0,
                      fontFamily: 'inherit',
                      fontSize: '0.9rem',
                      maxWidth: '100%',
                    }}>
                      {bidSuggestion.content}
                    </Typography>
                  </Box>
                ) : (
                  <Alert severity="info" sx={{ mt: 1 }}>
                    JF尚未提供建议
                  </Alert>
                )}
              </Box>
            ) : (
              <Alert severity="info" sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
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
