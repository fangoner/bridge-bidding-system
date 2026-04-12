import { Box, Typography, Paper, ToggleButton, ToggleButtonGroup, FormControlLabel, Checkbox } from '@mui/material'
import CardTable from './CardTable'
import BiddingTable from './BiddingTable'

function CardTablePanel({
  isMobile,
  hands,
  currentBidder,
  humanPosition,
  dealer,
  gameMode,
  showPartnerHand,
  setShowPartnerHand,
  showAIHands,
  setShowAIHands,
  showOpponentHands,
  getPartnerPosition,
  biddingSequence,
  isBiddingComplete,
  outputFormats,
  outputFormatsLoading,
  handleAnalyzeContract,
  analyzeLoading,
  colorScheme,
  currentBiddingPosition,
  showDoubleDummy,
  toggleDoubleDummy,
  doubleDummyResult,
  doubleDummyLoading,
  biddingTotalTime,
  positionRoles,
  handlePositionRoleChange,
  onDealerChange,
  onClearAllHands,
  setHands,
  biddingStarted,
  stopBidding,
  startBidding,
  height = '680px',
  playState,
  showPlayPanel,
  declarer,
}) {
  return (
    <Paper elevation={3} sx={{ 
      p: isMobile ? 1 : (isMobile ? 0.5 : 1), 
      bgcolor: isMobile ? '#f5f5f5' : '#e8e8e8', 
      display: 'flex', 
      flexDirection: 'column', 
      flex: isMobile ? undefined : '0 0 auto',
      width: isMobile ? '100%' : '600px',
      height: isMobile ? 'auto' : height,
      minHeight: isMobile ? '400px' : undefined,
      overflow: isMobile ? undefined : 'hidden'
    }}>
      <Box sx={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        mb: 0.5, 
        flexShrink: 0, 
        minHeight: 32,
        flexWrap: isMobile ? 'wrap' : 'nowrap',
        gap: isMobile ? 0.5 : 0
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant={isMobile ? "h6" : "subtitle1"} sx={{ fontWeight: 600, fontSize: isMobile ? undefined : '1rem' }}>
            {showPlayPanel ? '打牌阶段' : '当前牌局'}
          </Typography>
          {!showPlayPanel && (
            <ToggleButtonGroup
              value={showDoubleDummy ? 'result' : 'table'}
              exclusive
              onChange={(e, newValue) => {
                if (newValue !== null) {
                  toggleDoubleDummy(newValue === 'result')
                }
              }}
              size="small"
              sx={{ height: isMobile ? 26 : 24 }}
              disabled={!isBiddingComplete()}
            >
              <ToggleButton value="table" sx={{ px: 1, py: 0, fontSize: isMobile ? '0.875rem' : '0.75rem', minWidth: 50 }}>
                叫牌过程
              </ToggleButton>
              <ToggleButton value="result" sx={{ px: 1, py: 0, fontSize: isMobile ? '0.875rem' : '0.75rem', minWidth: 50 }}>
                小房子
              </ToggleButton>
            </ToggleButtonGroup>
          )}
          {showPlayPanel && playState && (
            <Typography variant="body2" color="text.secondary">
              {playState.current_player}出牌
            </Typography>
          )}
          
          {gameMode === 'pair' && humanPosition && (
            <FormControlLabel
              control={
                <Checkbox
                  checked={showPartnerHand}
                  onChange={(e) => setShowPartnerHand(e.target.checked)}
                  size="small"
                />
              }
              label="队友手牌"
              sx={{ '& .MuiFormControlLabel-label': { fontSize: isMobile ? '0.875rem' : '0.75rem' }, ml: 0.5, mr: isMobile ? 0 : undefined }}
            />
          )}
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          {gameMode === 'four' && humanPosition && (
            <FormControlLabel
              control={
                <Checkbox
                  checked={showAIHands}
                  onChange={(e) => setShowAIHands(e.target.checked)}
                  size="small"
                />
              }
              label="AI手牌"
              sx={{ '& .MuiFormControlLabel-label': { fontSize: isMobile ? '0.875rem' : '0.75rem' }, mr: isMobile ? 0 : undefined }}
            />
          )}
        </Box>
      </Box>
      <Box sx={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center', 
        flex: isMobile ? 1 : '1 1 auto', 
        minHeight: 0, 
        overflow: 'hidden' 
      }}>
        <CardTable
          hands={hands}
          currentBidder={currentBidder}
          humanPosition={humanPosition}
          dealer={dealer}
          gameMode={gameMode}
          showPartnerHand={showPartnerHand}
          showAIHands={showAIHands}
          showOpponentHands={showOpponentHands}
          getPartnerPosition={getPartnerPosition}
          renderBiddingTable={() => <BiddingTable biddingSequence={biddingSequence} dealer={dealer} />}
          checkBiddingComplete={isBiddingComplete}
          outputFormats={outputFormats}
          outputFormatsLoading={outputFormatsLoading}
          handleAnalyzeContract={handleAnalyzeContract}
          analyzeLoading={analyzeLoading}
          colorScheme={colorScheme}
          currentBiddingPosition={currentBiddingPosition}
          showDoubleDummy={showDoubleDummy}
          doubleDummyResult={doubleDummyResult}
          doubleDummyLoading={doubleDummyLoading}
          biddingTotalTime={biddingTotalTime}
          positionRoles={positionRoles}
          onPositionRoleChange={handlePositionRoleChange}
          onDealerChange={onDealerChange}
          onClearAllHands={onClearAllHands}
          setHands={setHands}
          biddingStarted={biddingStarted}
          stopBidding={stopBidding}
          startBidding={startBidding}
          declarer={declarer}
        />
      </Box>
    </Paper>
  )
}

export default CardTablePanel
