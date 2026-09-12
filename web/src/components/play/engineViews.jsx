import { Box } from '@mui/material'
import { RawFields, SuitCountsTable, PromptView, FinesseStamps, FinesseProbeView, CollapseSection } from './shared'
import { AlphaMuBars, DdBars, AlphaMuTiming } from './CandidateBars'
import { FINESSE_KEYS } from './utils'

// DD 视图专属：已在折叠区/Bar 标题行/探针印章展示，不从 RawFields 重复渲染
const DD_EXCLUDE = [...FINESSE_KEYS, '核心逻辑', '局面评估', 'dd_stats', '候选对比', 'finesse_probe', '伙伴探针']

function parseMcts(fullOutput) {
  const raw = fullOutput.mcts_stats
  if (!raw) return null
  if (typeof raw === 'string') {
    try { return JSON.parse(raw) } catch { return null }
  }
  return raw
}

// ── LLM 引擎视图：无候选条，保留输出/输入切换（input 显示提示词） ──
export function LlmEngineView({ record, fullOutput, viewMode }) {
  if (viewMode === 'input') return <PromptView fullOutput={fullOutput} record={record} prompt={record.prompt} />
  return (
    <>
      <SuitCountsTable fullOutput={fullOutput} />
      <RawFields fullOutput={fullOutput} record={record} />
    </>
  )
}

// ── DD 引擎视图：约束 → 飞牌印章 → Bar（含样本来源与统计标题行） → 其余 → 候选对比折叠 ──
// 非 LLM 引擎无"输入"模式，去切换直接输出
export function DdEngineView({ record, fullOutput }) {
  const mcts = parseMcts(fullOutput)
  const scoringMode = mcts?.candidates?.[0]?.scoring_mode
  const candidateRaw = fullOutput['候选对比']
  return (
    <>
      <SuitCountsTable fullOutput={fullOutput} />
      <FinesseProbeView fullOutput={fullOutput} />
      <FinesseStamps fullOutput={fullOutput} />
      {mcts && <DdBars mctsData={mcts} scoringMode={scoringMode} ddStats={fullOutput.dd_stats} />}
      <RawFields fullOutput={fullOutput} record={record} excludeKeys={DD_EXCLUDE} />
      {candidateRaw && (
        <CollapseSection title="候选对比">
          <Box component="pre" sx={{
            fontSize: '0.7rem', lineHeight: 1.3,
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            color: 'text.secondary',
          }}>
            {typeof candidateRaw === 'string' ? candidateRaw : JSON.stringify(candidateRaw, null, 2)}
          </Box>
        </CollapseSection>
      )}
    </>
  )
}

// αμ 视图专属：统计已在 Bar 标题行/时间监控展示，候选对比与 DDS 诊断低频折叠
const AM_EXCLUDE = [...FINESSE_KEYS, '核心逻辑', '局面评估', '候选对比', 'DDS诊断']

const preStyle = {
  fontSize: '0.7rem', lineHeight: 1.3,
  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
  color: 'text.secondary',
}

// ── αμ 引擎视图：成功率条形 + Pareto front + 时间监控 ──
export function AlphaMuEngineView({ record, fullOutput }) {
  const mcts = parseMcts(fullOutput)
  const candidateRaw = fullOutput['候选对比']
  const ddDiag = fullOutput['DDS诊断']
  return (
    <>
      <SuitCountsTable fullOutput={fullOutput} />
      <FinesseStamps fullOutput={fullOutput} />
      <Box>
        {mcts && <AlphaMuBars mctsData={mcts} />}
        {mcts && <AlphaMuTiming mctsData={mcts} />}
      </Box>
      <RawFields fullOutput={fullOutput} record={record} excludeKeys={AM_EXCLUDE} />
      {(candidateRaw || ddDiag) && (
        <Box sx={{ mt: 0.5 }}>
          {candidateRaw && (
            <CollapseSection title="候选对比">
              <Box component="pre" sx={preStyle}>
                {typeof candidateRaw === 'string' ? candidateRaw : JSON.stringify(candidateRaw, null, 2)}
              </Box>
            </CollapseSection>
          )}
          {ddDiag && (
            <CollapseSection title="DDS诊断">
              <Box component="pre" sx={preStyle}>{typeof ddDiag === 'string' ? ddDiag : JSON.stringify(ddDiag, null, 2)}</Box>
            </CollapseSection>
          )}
        </Box>
      )}
    </>
  )
}

// ── 完美 DD 引擎视图：全知精确分，单次求解候选 ──
export function PerfectEngineView({ record, fullOutput }) {
  const mcts = parseMcts(fullOutput)
  return (
    <>
      <SuitCountsTable fullOutput={fullOutput} />
      <FinesseStamps fullOutput={fullOutput} />
      <RawFields fullOutput={fullOutput} record={record} excludeKeys={FINESSE_KEYS} />
      {mcts && <DdBars mctsData={mcts} scoringMode="avg_tricks" />}
    </>
  )
}

// 引擎分派：非 LLM 引擎无输入模式，viewMode 仅 LLM 使用
export function EngineView({ record, fullOutput, viewMode }) {
  const engine = record.used_engine || ''
  if (engine === 'alphamu') return <AlphaMuEngineView record={record} fullOutput={fullOutput} />
  if (engine === 'dd') return <DdEngineView record={record} fullOutput={fullOutput} />
  if (engine === 'perfect') return <PerfectEngineView record={record} fullOutput={fullOutput} />
  return <LlmEngineView record={record} fullOutput={fullOutput} viewMode={viewMode} />
}