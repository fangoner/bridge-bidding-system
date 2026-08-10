import { BRIDGE_POSITIONS } from './position'

const VALID_CARDS = new Set(['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'])
const SUIT_KEYS = ['spades', 'hearts', 'diamonds', 'clubs']

/**
 * 校验手牌
 * 允许部分位置无牌（完全无牌视为未编辑该家），有牌则必须恰好13张
 * @param {Object} hands - { '南': {spades,hearts,diamonds,clubs,hcp}, ... }
 * @returns {{valid: boolean, errors: string[], warnings: string[]}}
 */
export function validateHands(hands) {
  const errors = []
  const warnings = []
  if (!hands) {
    return { valid: false, errors: ['手牌数据为空'], warnings }
  }

  const positions = BRIDGE_POSITIONS
  const allCards = new Map()
  let totalCards = 0
  let emptyPositions = []

  for (const pos of positions) {
    const hand = hands[pos]
    if (!hand) {
      emptyPositions.push(pos)
      continue
    }
    let posTotal = 0
    for (const suit of SUIT_KEYS) {
      const cards = (hand[suit] || '').toUpperCase()
      // 校验合法字符
      for (const c of cards) {
        if (!VALID_CARDS.has(c)) {
          errors.push(`${pos}家${suitName(suit)}含非法字符: ${c}`)
          continue
        }
        const cardKey = `${suit}:${c}`
        if (allCards.has(cardKey)) {
          errors.push(`${pos}家${suitName(suit)}的${c}与${allCards.get(cardKey)}重复`)
        } else {
          allCards.set(cardKey, `${pos}家${suitName(suit)}`)
        }
        posTotal++
        totalCards++
      }
      // 校验单花色内部重复
      const seen = new Set()
      for (const c of cards) {
        if (seen.has(c)) {
          errors.push(`${pos}家${suitName(suit)}内${c}重复`)
        }
        seen.add(c)
      }
    }
    // 位置完全无牌（0张）：允许，视为该位置未编辑
    if (posTotal === 0) {
      emptyPositions.push(pos)
    } else if (posTotal !== 13) {
      // 有牌但不满13张：错误（要么0张，要么13张）
      errors.push(`${pos}家共${posTotal}张牌，应为13张（或0张表示未编辑）`)
    }
  }

  // 只有四家都有牌时才校验总数52（防止与"部分位置无牌"重复报警）
  if (emptyPositions.length === 0 && totalCards !== 52) {
    errors.push(`四家总牌数${totalCards}张，应为52张`)
  }

  return { valid: errors.length === 0, errors, warnings }
}

/**
 * 校验叫牌序列
 * @param {Array<{position, bid}>} bids - 叫牌数组
 * @param {string} dealer - 发牌人 (南/西/北/东)，可选
 * @returns {{valid: boolean, errors: string[], warnings: string[], normalized: Array}}
 */
export function validateBidding(bids, dealer = null) {
  const errors = []
  const warnings = []

  if (!bids || bids.length === 0) {
    return { valid: false, errors: ['叫牌序列为空'], warnings, normalized: [] }
  }

  // 标准化每条叫品
  const normalized = bids.map(b => {
    let bid = (b.bid || '').trim()
    // 花色符号转字母
    const suitMap = { '♠': 'S', '♥': 'H', '♦': 'D', '♣': 'C' }
    bid = bid.replace(/[♠♥♦♣]/g, s => suitMap[s] || s)
    // 标准化pass
    if (['不叫', 'Pass', 'PASS', 'P', 'p', '-', '/', '', 'pass='].includes(bid) || bid.toLowerCase() === 'pass') {
      bid = 'pass'
    }
    if (['加倍', 'Double', 'D', 'd'].includes(bid)) bid = 'X'
    if (['再加倍', 'Redouble', 'RD', 'rd'].includes(bid)) bid = 'XX'
    // 去除 "=" 标记
    bid = bid.replace(/=/g, '')
    return { position: b.position, bid }
  }).filter(b => b.bid !== '')

  // 1. 位置合法性
  for (const b of normalized) {
    if (!BRIDGE_POSITIONS.includes(b.position)) {
      errors.push(`非法位置: ${b.position}`)
    }
  }

  // 2. 位置顺时针连续性（如果提供dealer则从dealer开始；否则按序列第一个位置开始）
  if (normalized.length > 0 && BRIDGE_POSITIONS.includes(normalized[0].position)) {
    const startPos = dealer && BRIDGE_POSITIONS.includes(dealer) ? dealer : normalized[0].position
    if (dealer && normalized[0].position !== dealer) {
      errors.push(`第一条叫品位置(${normalized[0].position})与发牌人(${dealer})不一致`)
    }
    const startIdx = BRIDGE_POSITIONS.indexOf(startPos)
    normalized.forEach((b, i) => {
      const expectedPos = BRIDGE_POSITIONS[(startIdx + i) % 4]
      if (b.position !== expectedPos) {
        errors.push(`第${i + 1}条叫品位置应为${expectedPos}，实际为${b.position}`)
      }
    })
  }

  // 3. 叫品合法性与阶数递增
  const suitRank = { C: 1, D: 2, H: 3, S: 4, N: 5 }
  let lastSubstantiveBid = null
  let lastBidType = null // 'bid', 'X', 'XX', 'pass'
  let lastSubstantiveSide = null // 'NS' or 'EW'

  for (let i = 0; i < normalized.length; i++) {
    const { position, bid } = normalized[i]
    const bidType = bid === 'pass' ? 'pass' : bid === 'X' ? 'X' : bid === 'XX' ? 'XX' : 'bid'

    if (bidType === 'bid') {
      const match = bid.match(/^([1-7])([CDHS]|NT)$/i)
      if (!match) {
        errors.push(`第${i + 1}条叫品"${bid}"格式不合法`)
        continue
      }
      const level = parseInt(match[1])
      const suit = match[2].toUpperCase()[0]
      // 与上一实质性叫品比较阶数
      if (lastSubstantiveBid) {
        const lastMatch = lastSubstantiveBid.match(/^([1-7])([CDHS]|NT)$/i)
        if (lastMatch) {
          const lastLevel = parseInt(lastMatch[1])
          const lastSuit = lastMatch[2].toUpperCase()[0]
          let ok = false
          if (level > lastLevel) ok = true
          else if (level === lastLevel && suitRank[suit] > suitRank[lastSuit]) ok = true
          if (!ok) {
            errors.push(`第${i + 1}条叫品"${bid}"不高于上一实质性叫品"${lastSubstantiveBid}"`)
          }
        }
      }
      lastSubstantiveBid = bid
      lastSubstantiveSide = ['南', '北'].includes(position) ? 'NS' : 'EW'
    } else if (bidType === 'X') {
      // 加倍：上一实质性叫品必须来自右手对手（即对方阵营），且上一条叫品不是X/XX
      if (!lastSubstantiveBid) {
        errors.push(`第${i + 1}条叫品"X"无实质叫品可加倍`)
      } else {
        const mySide = ['南', '北'].includes(position) ? 'NS' : 'EW'
        if (lastSubstantiveSide === mySide) {
          errors.push(`第${i + 1}条叫品"X"不能加倍同伴的叫品`)
        }
        if (lastBidType === 'X' || lastBidType === 'XX') {
          errors.push(`第${i + 1}条叫品"X"不合法（连续加倍）`)
        }
      }
    } else if (bidType === 'XX') {
      // 再加倍：上一条叫品必须是对方阵营的X
      if (lastBidType !== 'X') {
        errors.push(`第${i + 1}条叫品"XX"前一叫品不是X`)
      } else {
        // X 来自对方阵营（已在 X 校验中确认 X 是对方对己方实质叫品的加倍）
        // 这里再检查 XX 的发起方应当是被X一方的搭档（即与实质叫品同阵营）
        if (lastSubstantiveSide) {
          const mySide = ['南', '北'].includes(position) ? 'NS' : 'EW'
          if (lastSubstantiveSide !== mySide) {
            errors.push(`第${i + 1}条叫品"XX"只能再加倍对方对己方的加倍`)
          }
        }
      }
    }
    lastBidType = bidType
  }

  // 4. 流局检查（4个pass开局）
  if (normalized.length === 4 && normalized.every(b => b.bid === 'pass')) {
    warnings.push('四家全pass（流局）')
  }

  // 5. 叫牌结束检查：最后一个实质叫品后必须恰好3个pass
  if (normalized.length > 0) {
    let lastSubIdx = -1
    for (let i = normalized.length - 1; i >= 0; i--) {
      if (normalized[i].bid !== 'pass') {
        lastSubIdx = i
        break
      }
    }
    if (lastSubIdx >= 0) {
      const trailingPasses = normalized.length - 1 - lastSubIdx
      if (trailingPasses !== 3) {
        warnings.push(`最后一个实质叫品后${trailingPasses}个pass，标准为3个`)
      }
    } else if (normalized.length > 4) {
      warnings.push('叫牌序列过长且无实质叫品')
    }
  }

  return { valid: errors.length === 0, errors, warnings, normalized }
}

function suitName(key) {
  return { spades: '黑桃', hearts: '红心', diamonds: '方块', clubs: '草花' }[key] || key
}
