const INJECTION_PATTERNS: RegExp[] = [
  /ignore\s+(all\s+)?previous\s+instructions?/gi,
  /you\s+are\s+now\s+/gi,
  /forget\s+(all\s+)?previous/gi,
  /system\s+prompt/gi,
  /\bact\s+as\b/gi,
  /\brole.?play\b/gi,
  /developer\s+mode/gi,
  /admin\s+mode/gi,
  /jailbreak/gi,
  /<script[^>]*>/gi,
  /javascript\s*:/gi,
  /on\w+\s*=\s*["']/gi,
];

export function sanitizeInput(text: string): string {
  if (!text) return "";
  let cleaned = text;
  INJECTION_PATTERNS.forEach((pattern) => { cleaned = cleaned.replace(pattern, ""); });
  cleaned = cleaned.replace(/\0/g, "");
  return cleaned.trim();
}

export function validateWritingSamples(text: string): { valid: boolean; error: string | null } {
  if (!text || text.trim().length === 0) return { valid: true, error: null };
  if (text.length < 50) return { valid: false, error: "Need at least 50 characters for voice matching." };
  if (text.length > 2000) return { valid: false, error: "Maximum 2,000 characters." };
  const alphaRatio = (text.match(/[a-zA-Z]/g) || []).length / text.length;
  if (alphaRatio < 0.5) return { valid: false, error: "Please paste actual writing — texts, emails, or notes." };
  return { valid: true, error: null };
}

export function validateDecisionInput(pathA: string, pathB: string): { valid: boolean; errors: string[] } {
  const errors: string[] = [];
  if (!pathA || pathA.trim().length < 2) errors.push("Option A is too short.");
  if (!pathB || pathB.trim().length < 2) errors.push("Option B is too short.");
  if (pathA && pathA.length > 200) errors.push("Option A is too long (max 200 characters).");
  if (pathB && pathB.length > 200) errors.push("Option B is too long (max 200 characters).");
  if (pathA && pathB && pathA.trim().toLowerCase() === pathB.trim().toLowerCase()) errors.push("Options A and B can't be the same.");
  return { valid: errors.length === 0, errors };
}

export function sanitizeFinancialInput(value: string): string {
  const num = parseFloat(value);
  if (isNaN(num) || num < 0 || num > 100_000_000) return "";
  return String(Math.round(num));
}
