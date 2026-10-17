// The height a generated section has to come out at: no taller than the original
// and at most SLACK shorter (24px, or 4% of a tall section). render.mjs pads a section
// that fits to exactly the original height, so both versions of a pair are the same
// size and the page below does not move; generate.mjs asks the model to revise one
// that does not fit, and run.mjs decides whether another round is needed.
export function range(h) {
  const slack = Math.max(24, Math.round(h * 0.04))
  return { min: h - slack, max: h }
}

export const fits = (h, actual) => {
  const { min, max } = range(h)
  return actual >= min && actual <= max
}
