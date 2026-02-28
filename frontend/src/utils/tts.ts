import { DEBATE_BASE } from "./constants";

let pollyFailed = false;
const POLLY_TIMEOUT_MS = 4000;

const VOICE_MAP_MALE: [string, string] = ["Matthew", "Stephen"];
const VOICE_MAP_FEMALE: [string, string] = ["Joanna", "Ruth"];
const VOICE_MAP_NEUTRAL: [string, string] = ["Matthew", "Ruth"];

const FEMALE_NAMES = new Set([
  "mary", "patricia", "jennifer", "linda", "elizabeth", "barbara", "susan",
  "jessica", "sarah", "karen", "nancy", "lisa", "betty", "dorothy", "sandra",
  "ashley", "emily", "donna", "michelle", "carol", "amanda", "melissa",
  "deborah", "stephanie", "rebecca", "sharon", "laura", "cynthia", "kathleen",
  "amy", "angela", "shirley", "anna", "brenda", "pamela", "emma", "nicole",
  "helen", "samantha", "katherine", "christine", "debra", "rachel", "carolyn",
  "janet", "catherine", "maria", "heather", "diane", "ruth", "julie", "olivia",
  "joyce", "virginia", "victoria", "kelly", "lauren", "christina", "joan",
  "evelyn", "judith", "megan", "andrea", "cheryl", "hannah", "jacqueline",
  "martha", "gloria", "teresa", "ann", "sara", "madison", "frances", "kathryn",
  "janice", "jean", "abigail", "alice", "judy", "sophia", "grace", "denise",
  "amber", "doris", "marilyn", "danielle", "beverly", "isabella", "theresa",
  "diana", "natalie", "brittany", "charlotte", "marie", "kayla", "alexis", "lori",
]);

export function detectVoiceGender(name: string | null | undefined): "male" | "female" | "neutral" {
  if (!name) return "neutral";
  const lower = name.trim().toLowerCase();
  if (FEMALE_NAMES.has(lower)) return "female";
  if (lower.length > 0) return "male";
  return "neutral";
}

export function getVoicePair(name: string | null | undefined): [string, string] {
  const gender = detectVoiceGender(name);
  if (gender === "female") return VOICE_MAP_FEMALE;
  if (gender === "male") return VOICE_MAP_MALE;
  return VOICE_MAP_NEUTRAL;
}

let currentAudio: HTMLAudioElement | null = null;
let currentUtterance: SpeechSynthesisUtterance | null = null;
let speakGeneration = 0;
let activeAbort: AbortController | null = null;

const stopListeners = new Set<() => void>();

export function onSpeakingStopped(cb: () => void): () => void {
  stopListeners.add(cb);
  return () => { stopListeners.delete(cb); };
}

export function stopSpeaking() {
  speakGeneration++;

  if (activeAbort) {
    activeAbort.abort();
    activeAbort = null;
  }
  if (currentAudio) {
    currentAudio.onended = null;
    currentAudio.onerror = null;
    currentAudio.pause();
    currentAudio.src = "";
    currentAudio = null;
  }
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
  if (currentUtterance) {
    currentUtterance.onend = null;
    currentUtterance.onerror = null;
    currentUtterance = null;
  }
  stopListeners.forEach((cb) => cb());
}

export function isTTSAvailable(): boolean {
  return true;
}

type SpeakCallbacks = {
  onStart?: () => void;
  onEnd?: () => void;
};

async function speakWithPolly(text: string, voiceId: string, gen: number, callbacks: SpeakCallbacks): Promise<boolean> {
  if (pollyFailed) return false;

  const controller = new AbortController();
  activeAbort = controller;
  const timer = setTimeout(() => controller.abort(), POLLY_TIMEOUT_MS);

  try {
    const res = await fetch(`${DEBATE_BASE}/api/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice_id: voiceId }),
      signal: controller.signal,
    });
    clearTimeout(timer);
    activeAbort = null;

    if (gen !== speakGeneration) return false;
    if (!res.ok) throw new Error(`Polly returned ${res.status}`);

    const blob = await res.blob();
    if (blob.size < 100) throw new Error("Empty audio");
    if (gen !== speakGeneration) return false;

    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudio = audio;

    return new Promise((resolve) => {
      audio.onplay = () => { if (gen === speakGeneration) callbacks.onStart?.(); };
      audio.onended = () => {
        URL.revokeObjectURL(url);
        currentAudio = null;
        if (gen === speakGeneration) callbacks.onEnd?.();
        resolve(true);
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        currentAudio = null;
        if (gen === speakGeneration) callbacks.onEnd?.();
        resolve(false);
      };
      audio.play().catch(() => {
        URL.revokeObjectURL(url);
        currentAudio = null;
        resolve(false);
      });
    });
  } catch {
    clearTimeout(timer);
    activeAbort = null;
    pollyFailed = true;
    return false;
  }
}

function speakWithBrowser(text: string, voiceId: string, gen: number, callbacks: SpeakCallbacks): boolean {
  if (!window.speechSynthesis) return false;

  const utterance = new SpeechSynthesisUtterance(text);
  currentUtterance = utterance;

  const voices = window.speechSynthesis.getVoices();
  const isFemaleVoice = ["Joanna", "Ruth", "Danielle"].includes(voiceId);
  const preferred = voices.find((v) =>
    isFemaleVoice ? v.name.includes("Female") || v.name.includes("Samantha") : v.name.includes("Male") || v.name.includes("Daniel")
  );
  if (preferred) utterance.voice = preferred;

  utterance.rate = 1.0;
  utterance.pitch = isFemaleVoice ? 1.1 : 0.9;

  utterance.onstart = () => { if (gen === speakGeneration) callbacks.onStart?.(); };
  utterance.onend = () => {
    currentUtterance = null;
    if (gen === speakGeneration) callbacks.onEnd?.();
  };
  utterance.onerror = () => {
    currentUtterance = null;
    if (gen === speakGeneration) callbacks.onEnd?.();
  };

  window.speechSynthesis.speak(utterance);
  return true;
}

export async function speak(text: string, voiceId: string, callbacks: SpeakCallbacks = {}): Promise<void> {
  stopSpeaking();
  const gen = speakGeneration;

  const pollyWorked = await speakWithPolly(text, voiceId, gen, callbacks);
  if (pollyWorked || gen !== speakGeneration) return;

  const browserWorked = speakWithBrowser(text, voiceId, gen, callbacks);
  if (!browserWorked && gen === speakGeneration) {
    callbacks.onEnd?.();
  }
}
