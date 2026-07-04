const TRICK_VALUE = { '♣': 20, '♦': 20, '♥': 30, '♠': 30, 'NT': 30 }
const NT_FIRST = 10

export function calcScore(level, suit, doubled, redoubled, tricksMade, vul) {
  const needed = level + 6
  const diff = tricksMade - needed
  if (diff >= 0) return contractMade(level, suit, doubled, redoubled, diff, vul)
  return contractDown(-diff, doubled, redoubled, vul)
}

function contractMade(level, suit, doubled, redoubled, overtricks, vul) {
  const mult = redoubled ? 4 : doubled ? 2 : 1
  let score = TRICK_VALUE[suit] * level * mult
  if (suit === 'NT') score += NT_FIRST * (doubled || redoubled ? mult : 1)

  if (overtricks > 0) {
    let each
    if (doubled || redoubled) each = vul ? (redoubled ? 400 : 200) : (redoubled ? 200 : 100)
    else each = TRICK_VALUE[suit]
    score += each * overtricks
  }

  if ((TRICK_VALUE[suit] * level) >= 100) score += vul ? 500 : 300  // game bonus
  else score += 50  // partscore

  if (level === 6) score += vul ? 750 : 500
  else if (level === 7) score += vul ? 1500 : 1000

  if (doubled) score += 50
  else if (redoubled) score += 100

  return score
}

function contractDown(undertricks, doubled, redoubled, vul) {
  let penalty = 0
  if (doubled || redoubled) {
    const perTrick = vul ? [200, 300, 300] : [100, 200, 200]
    for (let i = 1; i <= undertricks; i++) {
      penalty += i <= 3 ? perTrick[i - 1] : 300
    }
    if (redoubled) penalty *= 2
  } else {
    penalty = vul
      ? [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200, 1300][Math.min(undertricks - 1, 12)]
      : [50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650][Math.min(undertricks - 1, 12)]
  }
  return -penalty
}
