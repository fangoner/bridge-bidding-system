/**
 * 叫牌序列工具函数
 * 统一使用字符串格式: "(南)1NT-(西)pass-(北)2C-(东)pass-"
 */

/**
 * 将叫牌序列字符串解析为数组
 * @param {string} sequenceStr - 叫牌序列字符串，如 "(南)1NT-(西)pass-"
 * @returns {Array<{position: string, bid: string}>} - 叫牌数组
 */
export function parseBiddingSequence(sequenceStr) {
  if (!sequenceStr || typeof sequenceStr !== 'string') {
    return []
  }
  
  const bids = []
  // 匹配 (位置)叫品 格式
  const regex = /\(([南北东西])\)([^-]+)/g
  let match
  
  while ((match = regex.exec(sequenceStr)) !== null) {
    bids.push({
      position: match[1],
      bid: match[2].trim()
    })
  }
  
  return bids
}

/**
 * 将叫牌数组转换为字符串
 * @param {Array<{position: string, bid: string}>} bids - 叫牌数组
 * @returns {string} - 叫牌序列字符串
 */
export function formatBiddingSequence(bids) {
  if (!Array.isArray(bids) || bids.length === 0) {
    return ''
  }
  
  return bids.map(b => `(${b.position})${b.bid}`).join('-') + '-'
}

/**
 * 添加一个叫品到序列
 * @param {string} sequenceStr - 当前序列字符串
 * @param {string} position - 位置 (南/西/北/东)
 * @param {string} bid - 叫品
 * @returns {string} - 新的序列字符串
 */
export function addBidToSequence(sequenceStr, position, bid) {
  const bidStr = `(${position})${bid}-`
  return sequenceStr + bidStr
}

/**
 * 获取最后一个实质性叫品（非pass）
 * @param {string} sequenceStr - 叫牌序列字符串
 * @returns {{position: string, bid: string}|null}
 */
export function getLastRealBid(sequenceStr) {
  const bids = parseBiddingSequence(sequenceStr)
  for (let i = bids.length - 1; i >= 0; i--) {
    if (bids[i].bid.toLowerCase() !== 'pass') {
      return bids[i]
    }
  }
  return null
}

/**
 * 获取当前定约
 * @param {string} sequenceStr - 叫牌序列字符串
 * @returns {string|null} - 当前定约，如 "1NT" 或 null
 */
export function getCurrentContract(sequenceStr) {
  const lastRealBid = getLastRealBid(sequenceStr)
  return lastRealBid ? lastRealBid.bid : null
}

/**
 * 检查叫牌是否结束（连续3个pass且已有实质性叫品）
 * @param {string} sequenceStr - 叫牌序列字符串
 * @returns {boolean}
 */
export function isBiddingComplete(sequenceStr) {
  const bids = parseBiddingSequence(sequenceStr)
  if (bids.length < 4) return false
  
  // 检查是否有实质性叫品
  const hasRealBid = bids.some(b => b.bid.toLowerCase() !== 'pass')
  if (!hasRealBid) return false
  
  // 检查最后3个是否都是pass
  const last3 = bids.slice(-3)
  return last3.every(b => b.bid.toLowerCase() === 'pass')
}

/**
 * 获取下一个叫牌位置
 * @param {string} sequenceStr - 叫牌序列字符串
 * @param {string} dealer - 发牌人 (南/西/北/东)
 * @returns {string} - 下一个叫牌位置
 */
import { BRIDGE_POSITIONS } from './position'

export function getNextBidder(sequenceStr, dealer) {
  const positions = BRIDGE_POSITIONS
  const bids = parseBiddingSequence(sequenceStr)
  
  if (bids.length === 0) {
    return dealer
  }
  
  const lastPosition = bids[bids.length - 1].position
  const lastIndex = positions.indexOf(lastPosition)
  return positions[(lastIndex + 1) % 4]
}
