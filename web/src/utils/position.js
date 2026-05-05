export const isHumanPosition = (roles, pos) => roles?.[pos] === 'human'

export const hasAnyHuman = (roles) => Object.values(roles || {}).some(r => r === 'human')

export const getHumanPositions = (roles) => Object.keys(roles || {}).filter(p => roles[p] === 'human')

export const getPartnerPosition = (position) => {
  const partners = { '南': '北', '北': '南', '东': '西', '西': '东' }
  return partners[position]
}
