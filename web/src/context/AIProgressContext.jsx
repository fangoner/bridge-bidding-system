/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState } from 'react'

// AI 轮询进度文案（叫牌/打牌共用）独立 Context：
// 进度文案每次轮询都可能更新（最快 300ms 一次），若放在 GameContext 会导致
// 所有 useGame 消费者（含整棵牌桌子树）每次轮询都重渲染。
// value / setter 拆成两个 Context：生产者（App）只订阅稳定 setter，自身不因文案更新重渲染；
// 消费者（叫牌/打牌详情面板）订阅 value，仅面板子树局部重渲染。
const AIProgressValueContext = createContext(null)
const AIProgressSetterContext = createContext(() => {})

export function AIProgressProvider({ children }) {
  const [aiProgress, setAiProgress] = useState(null)
  return (
    <AIProgressSetterContext.Provider value={setAiProgress}>
      <AIProgressValueContext.Provider value={aiProgress}>
        {children}
      </AIProgressValueContext.Provider>
    </AIProgressSetterContext.Provider>
  )
}

export function useAIProgress() {
  return useContext(AIProgressValueContext)
}

export function useAIProgressSetter() {
  return useContext(AIProgressSetterContext)
}
