import { MIN_SAFE_DISTANCE } from '../config/thresholds'

export { MIN_SAFE_DISTANCE }
export const DEFECT_SAFETY = { NONE: 1, S1: 0.8, S2: 0.4, S3: 0 }

const distanceOf = (state, track) => {
  const value = state[`distance_to_switch_${track}`] ?? state.distance_to_switch
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : Infinity
}
export const checkRules = (track, state) => {
  const defect = state[`track_${track}_defect`] || 'NONE'
  const distance = distanceOf(state, track)
  return [
    {
      rule: 'Target track is not occupied',
      passed: !state[`track_${track}_occupied`],
    },
    { rule: 'No S3 defect on target track', passed: defect !== 'S3' },
    {
      rule: 'Switch mechanism is available',
      passed: state[`switch_${track}_available`] !== false,
    },
    {
      rule: 'Train is not too close to switch',
      passed: distance >= MIN_SAFE_DISTANCE,
    },
  ]
}
const score = (track, state) => {
  if (!checkRules(track, state).every((rule) => rule.passed)) return null
  const defect = state[`track_${track}_defect`] || 'NONE'
  const availability = state[`track_${track}_occupied`] ? 0 : 1
  const distance = distanceOf(state, track)
  return Number(
    (
      0.5 * DEFECT_SAFETY[defect] +
      0.25 * availability +
      0.15 * Math.min(distance / MIN_SAFE_DISTANCE, 1) +
      0.1 * Number(state.delay_score ?? 1)
    ).toFixed(4),
  )
}
const confidence = (winner, loser) =>
  loser === null
    ? 0.5
    : Number(Math.min(0.99, Math.max(0, 0.5 + (winner - loser) / 2)).toFixed(2))
const reason = (target, state) => {
  const other = target === 'A' ? 'B' : 'A'
  const parts = [`Track ${target} selected`]
  const defect = state[`track_${target}_defect`] || 'NONE'
  if (defect !== 'NONE') parts.push(`Track ${target} has ${defect} defect`)
  if (state[`track_${other}_occupied`]) parts.push(`Track ${other} is occupied`)
  else if (state[`track_${other}_defect`])
    parts.push(`Track ${other} has ${state[`track_${other}_defect`]} defect`)
  return `${parts.join('. ')}.`
}

export function decide(
  state,
  { trainId = 'train_0', switchId = 'switch_0', position = 0 } = {},
) {
  const scoreA = score('A', state)
  const scoreB = score('B', state)
  const base = {
    timestamp: new Date().toISOString(),
    train_id: trainId,
    switch_id: switchId,
    position,
    raw_scores: { A: scoreA, B: scoreB },
  }
  if (scoreA === null && scoreB === null)
    return {
      ...base,
      action: 'EMERGENCY_STOP',
      action_level: 'EMERGENCY',
      target_track: null,
      confidence: 0,
      rules_checked: checkRules('A', state),
      reason: 'No safe track available - both blocked.',
    }
  const target =
    scoreA !== null && (scoreB === null || scoreA >= scoreB) ? 'A' : 'B'
  const winner = target === 'A' ? scoreA : scoreB
  const loser = target === 'A' ? scoreB : scoreA
  const defect = state[`track_${target}_defect`]
  return {
    ...base,
    action: target === 'A' ? 'MAINTAIN' : 'SWITCH',
    action_level: defect === 'S2' ? 'WARNING' : 'NORMAL',
    target_track: `Track ${target}`,
    confidence: confidence(winner, loser),
    rules_checked: checkRules(target, state),
    reason: reason(target, state),
  }
}
