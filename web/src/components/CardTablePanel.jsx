import { Box, Typography, Paper, ToggleButton, ToggleButtonGroup, FormControlLabel, Checkbox, useTheme } from '@mui/material'
import CardTable from './CardTable'
import BiddingTable from './BiddingTable'
import { hasAnyHuman, getHumanPositions } from '../utils/position'

function CardTablePanel({
  isMobile,
  hands,
  currentBidder,
  dealer,
  gameMode,
  showPartnerHand,
  setShowPartnerHand,
  showOpponentHands,
  setShowOpponentHands,
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
  height = '680px',
  playState,
  showPlayPanel,
  declarer,
  lastCompletedTrick,
  isPlayPaused,
  playInitiated,
  aiLoading,
  showPlayedCards,
  setShowPlayedCards,
  playCenterView,
  setPlayCenterView,
  aiBiddingHistory,
  onPlayCardClick,
  onSetPlayHand,
  readonlyMode,
}) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  return (
    <Paper elevation={3} sx={{ 
      p: 1, 
      bgcolor: isDark ? 'rgba(30, 41, 59, 0.9)' : (isMobile ? '#f5f5f5' : '#e8e8e8'), 
      display: 'flex', 
      flexDirection: 'column', 
      flex: isMobile ? undefined : '0 0 auto',
      width: isMobile ? '100%' : '600px',
      height: isMobile ? 'auto' : '640px',
      overflow: 'hidden'
    }}>
      <Box sx={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        mb: 0.5, 
        flexShrink: 0, 
        minHeight: 40,
        flexWrap: isMobile ? 'wrap' : 'nowrap',
        gap: isMobile ? 0.5 : 0,
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="h6" sx={{ fontWeight: 600, fontSize: '1rem', color: isDark ? '#e2e8f0' : undefined }}>
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
              sx={{ height: 24 }}
              disabled={!isBiddingComplete()}
            >
              <ToggleButton value="table" sx={{ px: 1, py: 0, fontSize: '0.75rem', minWidth: 50 }}>
                叫牌过程
              </ToggleButton>
              <ToggleButton value="result" sx={{ px: 1, py: 0, fontSize: '0.75rem', minWidth: 50 }}>
                小房子
              </ToggleButton>
            </ToggleButtonGroup>
          )}
          {showPlayPanel && (
            <ToggleButtonGroup
              value={playCenterView || 'play'}
              exclusive
              onChange={(e, newValue) => {
                if (newValue !== null) {
                  setPlayCenterView(newValue)
                  toggleDoubleDummy(newValue === 'result')
                }
              }}
              size="small"
              sx={{ height: 24 }}
            >
              <ToggleButton value="play" sx={{ px: 1, py: 0, fontSize: '0.75rem', minWidth: 40 }}>
                出牌状态
              </ToggleButton>
              <ToggleButton value="bidding" sx={{ px: 1, py: 0, fontSize: '0.75rem', minWidth: 40 }}>
                叫牌过程
              </ToggleButton>
              <ToggleButton value="result" sx={{ px: 1, py: 0, fontSize: '0.75rem', minWidth: 40 }}>
                小房子
              </ToggleButton>
            </ToggleButtonGroup>
          )}
          
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {!showPlayPanel && hasAnyHuman(positionRoles) && getHumanPositions(positionRoles).length < 3 && (
            <>
              <Typography variant="body2" sx={{ fontSize: '0.75rem', fontWeight: 700, mr: 0 }}>
                {gameMode === 'pair' ? '双人练习' : '四人练习'}
              </Typography>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={showPartnerHand}
                    onChange={(e) => setShowPartnerHand(e.target.checked)}
                    size="small"
                  />
                }
                label="队友手牌"
                sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, mr: 0, height: 24 }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={showOpponentHands}
                    onChange={(e) => setShowOpponentHands(e.target.checked)}
                    size="small"
                  />
                }
                label="对方手牌"
                sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, mr: 0, height: 24 }}
              />
            </>
          )}
          {/* 打牌checkbox：仅四家全有手牌时显示（正常发牌练习模式），模拟实战不显示 */}
          {showPlayPanel && hasAnyHuman(positionRoles) && ['南','北','东','西'].every(p => {
            const h = hands?.[p]; return h && (h.spades || h.hearts || h.diamonds || h.clubs)
          }) && (
            <>
              {positionRoles[declarer] === 'ai' ? (
                <>
                  <FormControlLabel
                    control={<Checkbox checked={showPartnerHand} onChange={(e) => setShowPartnerHand(e.target.checked)} size="small" />}
                    label="队友手牌"
                    sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, mr: 0, height: 24 }}
                  />
                  <FormControlLabel
                    control={<Checkbox checked={showOpponentHands} onChange={(e) => setShowOpponentHands(e.target.checked)} size="small" />}
                    label="对方手牌"
                    sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, mr: 0, height: 24 }}
                  />
                </>
              ) : (
                <FormControlLabel
                  control={<Checkbox checked={showOpponentHands} onChange={(e) => setShowOpponentHands(e.target.checked)} size="small" />}
                  label="对方手牌"
                  sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, mr: 0, height: 24 }}
                />
              )}
            </>
          )}
          {showPlayPanel && (
            <FormControlLabel
              control={<Checkbox checked={showPlayedCards} onChange={(e) => setShowPlayedCards(e.target.checked)} size="small" />}
              label="显示已出"
              sx={{ '& .MuiFormControlLabel-label': { fontSize: '0.75rem' }, mr: 0, height: 24 }}
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
        overflow: 'hidden',
      }}>
        <CardTable
          hands={hands}
          currentBidder={currentBidder}
          dealer={dealer}
          gameMode={gameMode}
          showPartnerHand={showPartnerHand}
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
          declarer={declarer}
          playState={playState}
          showPlayPanel={showPlayPanel}
          lastCompletedTrick={lastCompletedTrick}
          isPlayPaused={isPlayPaused}
          playInitiated={playInitiated}
          aiLoading={aiLoading}
          showPlayedCards={showPlayedCards}
          playCenterView={playCenterView}
          aiBiddingHistory={aiBiddingHistory}
          onPlayCardClick={onPlayCardClick}
          onSetPlayHand={onSetPlayHand}
          readonlyMode={readonlyMode}
        />
      </Box>
    </Paper>
  )
}

export default CardTablePanel
