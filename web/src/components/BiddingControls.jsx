import React from 'react';
import {
  Box,
  Paper,
  Typography,
  Button,
  TextField,
  Alert,
  CircularProgress,
  Divider,
} from '@mui/material';

/**
 * BiddingControls component for desktop-optimized bidding controls
 *
 * @param {Object} props
 * @param {Object} props.hands - Hands object (to check if exists)
 * @param {string} props.currentBidder - Current bidding position
 * @param {string|null} props.humanPosition - Human player position or null
 * @param {string} props.gameMode - 'four' or 'pair'
 * @param {Function} props.checkBiddingComplete - Function that returns true if bidding is complete
 * @param {Function} props.addBid - Function to add a bid
 * @param {Function} props.getJFSuggestion - Function to get JF suggestion
 * @param {Function} props.getFinalContract - Function to get final contract
 * @param {Object|null} props.bidSuggestion - Bid suggestion object
 * @param {boolean} props.suggestionLoading - Loading state for suggestion
 * @param {boolean} props.aiLoading - AI loading state
 * @param {boolean} props.stopBidding - Whether bidding is stopped
 * @param {Function} props.isInPassedPartnership - Function to check if position is in passed partnership
 * @param {string} props.customBidMeaning - Custom bid meaning text
 * @param {Function} props.setCustomBidMeaning - Function to set custom bid meaning
 * @param {Object|null} props.outputFormats - Output formats object
 * @param {boolean} props.outputFormatsLoading - Loading state for output formats
 * @param {Function} props.handleAnalyzeContract - Function to analyze contract
 * @param {boolean} props.analyzeLoading - Loading state for contract analysis
 * @param {boolean} props.isVerticalLayout - Whether to use vertical layout (stacked panels)
 */
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
  aiLoading,
  stopBidding,
  isInPassedPartnership,
  customBidMeaning,
  setCustomBidMeaning,
  outputFormats,
  outputFormatsLoading,
  handleAnalyzeContract,
  analyzeLoading,
  isVerticalLayout = false,
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
                minWidth: isVerticalLayout ? '40px' : '44px',
                width: isVerticalLayout ? '40px' : '44px',
                height: isVerticalLayout ? '24px' : '30px',
                padding: isVerticalLayout ? '2px 5px' : '4px 7px',
                fontSize: isVerticalLayout ? '0.75rem' : '0.8rem',
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

            {humanPosition !== null && !isHumanTurn && (
              <Alert severity="info" sx={{ mt: isVerticalLayout ? 1 : 2, py: isVerticalLayout ? 0.5 : undefined, display: 'flex', alignItems: 'center', gap: 2 }}>
                {aiLoading ? <CircularProgress size={isVerticalLayout ? 16 : 20} /> : null}
                {stopBidding ? '叫牌已暂停' : (aiLoading ? 'AI正在叫牌...' : '等待AI叫牌...')}
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

      {/* Middle: JF suggestion panel - show when human is playing and bidding not complete */}
      {humanPosition !== null && !checkBiddingComplete() && (
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

      {/* Right: More output formats panel (after bidding complete) */}
      {checkBiddingComplete() && (
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
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexShrink: 0, flexWrap: 'wrap', gap: 1 }}>
            <Typography variant="h6">
              更多格式
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {outputFormatsLoading && <CircularProgress size={20} />}
              <Button
                variant="contained"
                size="small"
                onClick={handleAnalyzeContract}
                disabled={!outputFormats?.deep_finesse || analyzeLoading}
                startIcon={analyzeLoading ? <CircularProgress size={16} /> : null}
              >
                检验定约
              </Button>
            </Box>
          </Box>

          {outputFormats ? (
            <Box sx={{ flex: 1, overflow: 'auto', maxWidth: '100%', minWidth: 0, minHeight: 0 }}>
              <Typography variant="subtitle2" sx={{ mt: 1, mb: 1, color: '#1976d2', fontWeight: 'bold' }}>
                简单格式
              </Typography>
              <Box sx={{ p: 1.5, background: '#fafafa', borderRadius: 1, border: '1px solid #e0e0e0', mb: 2, overflow: 'auto', maxWidth: '100%' }}>
                <Typography variant="body2" component="pre" sx={{
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  margin: 0,
                  fontFamily: 'monospace',
                  fontSize: '0.75rem',
                  maxWidth: '100%',
                }}>
                  {outputFormats.compact}
                </Typography>
              </Box>

              <Typography variant="subtitle2" sx={{ mt: 2, mb: 1, color: '#1976d2', fontWeight: 'bold' }}>
                Deep Finesse格式
              </Typography>
              <Box sx={{ p: 1.5, background: '#fafafa', borderRadius: 1, border: '1px solid #e0e0e0', overflow: 'auto', maxWidth: '100%' }}>
                <Typography variant="body2" component="pre" sx={{
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  margin: 0,
                  fontFamily: 'monospace',
                  fontSize: '0.75rem',
                  maxWidth: '100%',
                }}>
                  {outputFormats.deep_finesse}
                </Typography>
              </Box>
            </Box>
          ) : (
            <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 0 }}>
              {outputFormatsLoading ? (
                <Typography variant="body2" color="text.secondary">加载中...</Typography>
              ) : (
                <Typography variant="body2" color="text.secondary">无数据</Typography>
              )}
            </Box>
          )}
        </Paper>
      )}
    </Box>
  );
}

export default BiddingControls;