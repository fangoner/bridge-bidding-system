import Box from '@mui/material/Box'
import { PANEL_LAYOUT } from '../styles/constants'
import CardTablePanel from './CardTablePanel'
import BiddingDetailPanel from './BiddingDetailPanel'
import PlayDetailPanel from './PlayDetailPanel'
import { hasAnyHuman } from '../utils/position'
import { useGame } from '../context/GameContext'
import { useBidding } from '../context/BiddingContext'
import { usePlay } from '../context/PlayContext'

// 主牌桌区域：桌面横排 / 手机纵排，消除 App.jsx 中桌面/手机两份重复 JSX
// state 从 Context 获取；业务回调和派生值由 App 传入
export default function MainTableArea({
  isMobile,
  declarer,
  finalContract,
  directPlayContractInfo,
  // CardTablePanel 业务回调
  onAnalyzeContract,
  onToggleDoubleDummy,
  onDealerChange,
  onPositionRoleChange,
  onClearAllHands,
  onEditHands,
  onEditBidding,
  onPlayCardClick,
  onSetPlayHand,
  onImageDeal,
  onScreenshotDeal,
  onSingleHandScreenshot,
  onSingleHandUpload,
  onCustomDeal,
  onDeal,
  onHandCardClick,
  onManualPlay,
  addBid,
  startBidding,
  // 叫牌面板业务回调
  onStartPlay,
  onResetBidding,
  onToggleStopBidding,
  onUndoBidding,
  onSaveBidding,
  canSaveBiddingProgress,
  showUndoBidding,
  canUndoBidding,
  onStartBidding,
  // 打牌面板业务回调
  onResume,
  onResetPlay,
  onClearExternalRecord,
  onBeginPlay,
  onPausePlay,
  onUndoPlay,
  onSavePlay,
  canSavePlay,
  onBackToBidding,
  onReviewPrev,
  onReviewNext,
  onRewindToTrick,
  onReviewCompletedPlay,
  playTotalTime, // v1.61：打牌总耗时（秒，完成后计算）
}) {
  return (
    <Box sx={isMobile
      ? { display: 'flex', flexDirection: 'column', gap: 2 }
      : { display: 'flex', gap: 2, mb: 2, justifyContent: 'center', m: 0 }
    }>
      <CardTablePanel
        isMobile={isMobile}
        declarer={declarer}
        finalContract={finalContract}
        directPlayContractInfo={directPlayContractInfo}
        onAnalyzeContract={onAnalyzeContract}
        onToggleDoubleDummy={onToggleDoubleDummy}
        onDealerChange={onDealerChange}
        onPositionRoleChange={onPositionRoleChange}
        onClearAllHands={onClearAllHands}
        onEditHands={onEditHands}
        onEditBidding={onEditBidding}
        onPlayCardClick={onPlayCardClick}
        onSetPlayHand={onSetPlayHand}
        onImageDeal={onImageDeal}
        onScreenshotDeal={onScreenshotDeal}
        onSingleHandScreenshot={onSingleHandScreenshot}
        onSingleHandUpload={onSingleHandUpload}
        onCustomDeal={onCustomDeal}
        onDeal={onDeal}
        onHandCardClick={onHandCardClick}
        onManualPlay={onManualPlay}
        addBid={addBid}
        startBidding={startBidding}
      />

      <RightPanelSwitcher
        isMobile={isMobile}
        directPlayContractInfo={directPlayContractInfo}
        // 叫牌回调
        onStartPlay={onStartPlay}
        onResetBidding={onResetBidding}
        onToggleStopBidding={onToggleStopBidding}
        onUndoBidding={onUndoBidding}
        onSaveBidding={onSaveBidding}
        canSaveBiddingProgress={canSaveBiddingProgress}
        showUndoBidding={showUndoBidding}
        canUndoBidding={canUndoBidding}
        onStartBidding={onStartBidding}
        // 打牌回调
        onResume={onResume}
        onResetPlay={onResetPlay}
        onClearExternalRecord={onClearExternalRecord}
        onBeginPlay={onBeginPlay}
        onPausePlay={onPausePlay}
        onUndoPlay={onUndoPlay}
        onSavePlay={onSavePlay}
        canSavePlay={canSavePlay}
        onBackToBidding={onBackToBidding}
        onReviewPrev={onReviewPrev}
        onReviewNext={onReviewNext}
        onRewindToTrick={onRewindToTrick}
        onReviewCompletedPlay={onReviewCompletedPlay}
        playTotalTime={playTotalTime}
      />
    </Box>
  )
}

// 右侧/下方面板切换：showPlayPanel 决定显示打牌面板还是叫牌面板
function RightPanelSwitcher({
  isMobile,
  directPlayContractInfo,
  // 叫牌回调
  onStartPlay,
  onResetBidding,
  onToggleStopBidding,
  onUndoBidding,
  onSaveBidding,
  canSaveBiddingProgress,
  showUndoBidding,
  canUndoBidding,
  onStartBidding,
  // 打牌回调
  onResume,
  onResetPlay,
    onBeginPlay,
  onPausePlay,
  onUndoPlay,
  onSavePlay,
  canSavePlay,
  onBackToBidding,
  onReviewPrev,
  onReviewNext,
  onRewindToTrick,
  onReviewCompletedPlay,
  playTotalTime, // v1.61：打牌总耗时（秒，完成后计算）
}) {
  const {
    hands,
    positionRoles,
    showAIBiddingOutput,
    readonlyMode,
    aiThinking,
    imageOpeningLead,
    fallbackModel,
  } = useGame()

  const {
    currentBidder,
    simpleDisplayMode, setSimpleDisplayMode,
    aiBiddingHistory,
    selectedBiddingIndex, setSelectedBiddingIndex,
    bidSuggestion,
    suggestionLoading,
    stopBidding,
    outputFormats,
    isBiddingComplete,
    biddingStarted,
    biddingTotalTime, // v1.61：叫牌总耗时（秒，叫牌完成时计算）
  } = useBidding()

  const {
    playState,
    aiPlayHistory,
    isPlayPaused,
    playStarted,
    playInitiated,
    loadedPlayRecord,
    selectedPlayRecord, setSelectedPlayRecord,
    reviewCursor,
    showPlayPanel,
    playLoading,
  } = usePlay()

  // 仅当有人类玩家或显示AI叫牌输出时才展示叫牌面板
  const showBiddingPanel = hasAnyHuman(positionRoles) || showAIBiddingOutput

  if (showPlayPanel) {
    return (
      <PlayDetailPanel
        isMobile={isMobile}
        playState={playState}
        aiPlayHistory={aiPlayHistory}
        aiLoading={aiThinking}
        isPaused={isPlayPaused}
        onResume={onResume}
        onResetPlay={onResetPlay}
        externalSelectedRecord={selectedPlayRecord}
        onClearExternalRecord={() => setSelectedPlayRecord(null)}
        playStarted={playStarted}
        onBeginPlay={onBeginPlay}
        onPausePlay={onPausePlay}
        playInitiated={playInitiated}
        onUndoPlay={onUndoPlay}
        isHistoryRecord={!!loadedPlayRecord}
        positionRoles={positionRoles}
        onSave={onSavePlay}
        canSave={canSavePlay}
        imageOpeningLead={imageOpeningLead}
        reviewCursor={reviewCursor}
        onReviewPrev={onReviewPrev}
        onReviewNext={onReviewNext}
        onBackToBidding={onBackToBidding}
        onRewindToTrick={onRewindToTrick}
        onReviewCompletedPlay={onReviewCompletedPlay}
        playTotalTime={playTotalTime}
      />
    )
  }

  if (showBiddingPanel) {
    return (
      <BiddingDetailPanel
        isMobile={isMobile}
        positionRoles={positionRoles}
        currentBidder={currentBidder}
        simpleDisplayMode={simpleDisplayMode}
        setSimpleDisplayMode={setSimpleDisplayMode}
        aiBiddingHistory={aiBiddingHistory}
        selectedBiddingIndex={selectedBiddingIndex}
        setSelectedBiddingIndex={setSelectedBiddingIndex}
        hands={hands}
        bidSuggestion={bidSuggestion}
        suggestionLoading={suggestionLoading}
        stopBidding={stopBidding}
        outputFormats={outputFormats}
        isBiddingCompleteFn={isBiddingComplete}
        onStartPlay={onStartPlay}
        playLoading={playLoading}
        directPlayContractInfo={directPlayContractInfo}
        biddingStarted={biddingStarted}
        onStartBidding={onStartBidding}
        onResetBidding={onResetBidding}
        onToggleStopBidding={onToggleStopBidding}
        showUndo={showUndoBidding}
        canUndo={canUndoBidding}
        onUndo={onUndoBidding}
        onSave={onSaveBidding}
        canSave={canSaveBiddingProgress}
        aiThinking={aiThinking}
        readonlyMode={readonlyMode}
        fallbackModel={fallbackModel}
        biddingTotalTime={biddingTotalTime}
      />
    )
  }

  return null
}
