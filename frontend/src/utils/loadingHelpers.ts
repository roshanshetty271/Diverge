/**
 * Calculate progress value from completed rounds
 * @param completedRounds - Number of completed rounds (0-5)
 * @param totalRounds - Total number of rounds (always 5)
 * @returns Progress value between 0.05 and 1.0
 */
export function calculateProgress(completedRounds: number, totalRounds: number): number {
  if (totalRounds <= 0) {
    return 0.05;
  }

  const baseProgress = completedRounds / totalRounds;
  
  // Ensure minimum progress for initial visual feedback
  if (baseProgress < 0.05) {
    return 0.05;
  }

  // Cap at 1.0
  if (baseProgress > 1.0) {
    return 1.0;
  }

  return baseProgress;
}

/**
 * Calculate SVG stroke-dashoffset for path animation
 * @param pathLength - Total length of the SVG path
 * @param progress - Progress value (0.0 to 1.0)
 * @returns Stroke-dashoffset value
 */
export function calculateStrokeDashoffset(pathLength: number, progress: number): number {
  return pathLength * (1 - progress);
}
