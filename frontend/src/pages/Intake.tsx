import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import ValuesChips from "../components/ValuesChips";
import WritingSampleInput from "../components/WritingSampleInput";
import { useToast } from "../components/Toast";
import { useDivergeAuth } from "../hooks/useAuth";
import { sanitizeInput, sanitizeFinancialInput, validateDecisionInput } from "../utils/security";
import { TEMPLATES } from "../utils/constants";
import { getTurnstileToken } from "../utils/turnstile";
import VoiceButton from "../components/VoiceButton";
import type { DecisionInput } from "../types";

const slideVariants = { enter: { opacity: 0, x: 20 }, center: { opacity: 1, x: 0 }, exit: { opacity: 0, x: -20 } };

const FINANCIAL_KEYWORDS = new Set([
  "job", "career", "salary", "pay", "work", "offer", "startup", "company",
  "business", "position", "promotion", "quit", "resign", "employed", "freelance",
  "move", "relocate", "city", "school", "study", "degree", "mba", "tuition",
  "rent", "retire", "income", "save", "invest",
]);

function isFinancialDecision(pathA: string, pathB: string, templateId?: string): boolean {
  const template = TEMPLATES.find((t) => t.id === templateId);
  if (template) return template.category === "financial";
  const words = `${pathA} ${pathB}`.toLowerCase().split(/\s+/);
  return words.some((w) => FINANCIAL_KEYWORDS.has(w));
}

export default function Intake() {
  const location = useLocation();
  const navigate = useNavigate();
  const initial = (location.state || {}) as { pathA?: string; pathB?: string; templateId?: string };

  const { toast } = useToast();
  const { isAuthenticated } = useDivergeAuth();
  const [step, setStep] = useState(0);
  const [userName, setUserName] = useState("");
  const [userAge, setUserAge] = useState("");
  const [pathA, setPathA] = useState(initial.pathA || "");
  const [pathB, setPathB] = useState(initial.pathB || "");
  const [salary, setSalary] = useState("");
  const [salaryNew, setSalaryNew] = useState("");
  const [savings, setSavings] = useState("");
  const [context, setContext] = useState("");
  const [values, setValues] = useState<string[]>([]);
  const [writingSample, setWritingSample] = useState("");
  const [startingDebate, setStartingDebate] = useState(false);

  const showMoney = isFinancialDecision(pathA, pathB, initial.templateId);

  const totalSteps = showMoney ? 4 : 3;
  const displayStep = () => {
    if (step === 0) return 1;
    if (step === 1) return 2;
    if (step === 2) return 3;
    return showMoney ? 4 : 3;
  };

  const startDebate = async () => {
    const { valid, errors } = validateDecisionInput(pathA, pathB);
    if (!valid) { errors.forEach((e) => toast(e)); return; }

    const payload: DecisionInput = {
      path_a: sanitizeInput(pathA),
      path_b: sanitizeInput(pathB),
      user_name: userName.trim() || null,
      age: userAge ? parseInt(userAge, 10) : null,
      financial_context: salary || salaryNew || savings
        ? `Current income: $${sanitizeFinancialInput(salary) || "unknown"}/yr. New path income: $${sanitizeFinancialInput(salaryNew) || "unknown"}/yr. Savings: $${sanitizeFinancialInput(savings) || "unknown"}.`
        : null,
      values: values.length > 0 ? values.join(", ") : null,
      constraints: sanitizeInput(context) || null,
      writing_samples: sanitizeInput(writingSample) || null,
    };

    setStartingDebate(true);
    try {
      const captchaToken = !isAuthenticated ? await getTurnstileToken("debate_start") : null;
      navigate("/loading", {
        state: { input: payload, captchaToken },
      });
    } catch (err) {
      toast(err instanceof Error ? err.message : "Please verify you're human and try again.");
    } finally {
      setStartingDebate(false);
    }
  };

  const canProceed = pathA.trim() && pathB.trim();

  const handleAddContext = () => {
    if (showMoney) {
      setStep(2);
    } else {
      setStep(3);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 py-16">
      <div className="w-full max-w-xl">
        <AnimatePresence mode="wait">
          {step === 0 && (
            <motion.div key="step0" variants={slideVariants} initial="enter" animate="center" exit="exit" transition={{ duration: 0.6 }}>
              <h1 className="font-display text-xl text-ivory" style={{ fontWeight: 400 }}>What should we call you?</h1>
              <p className="text-ivory-dim text-sm mt-2">Makes the debate feel like it's actually about you.</p>
              <div className="flex gap-3 mt-8">
                <input
                  type="text" value={userName} onChange={(e) => setUserName(e.target.value.slice(0, 50))}
                  placeholder="First name"
                  aria-label="Your name"
                  autoFocus
                  onKeyDown={(e) => e.key === "Enter" && setStep(1)}
                  className="flex-1 bg-surface border border-surface-light rounded-lg p-4 text-ivory text-base focus:border-path-risk focus:outline-none placeholder:text-ivory-faint transition-colors duration-200"
                />
                <input
                  type="number" value={userAge} onChange={(e) => setUserAge(e.target.value.slice(0, 3))}
                  placeholder="Age"
                  aria-label="Your age"
                  min={13} max={120}
                  onKeyDown={(e) => e.key === "Enter" && setStep(1)}
                  className="w-20 bg-surface border border-surface-light rounded-lg p-4 text-ivory text-base text-center focus:border-path-risk focus:outline-none placeholder:text-ivory-faint transition-colors duration-200"
                />
              </div>
              <div className="flex gap-3 mt-8">
                <button onClick={() => setStep(1)} className="flex-1 py-3 px-6 rounded-lg text-sm bg-path-risk text-void font-medium cursor-pointer transition-opacity duration-200">
                  {userName.trim() ? `Hey, ${userName.trim()}` : "Continue"} &rarr;
                </button>
                <button onClick={() => setStep(1)} className="flex-1 py-3 px-6 rounded-lg text-sm bg-transparent border border-surface-light text-ivory-dim hover:border-ivory-dim transition-colors duration-200 cursor-pointer">
                  Skip
                </button>
              </div>
            </motion.div>
          )}

          {step === 1 && (
            <motion.div key="step1" variants={slideVariants} initial="enter" animate="center" exit="exit" transition={{ duration: 0.6 }}>
              <button onClick={() => setStep(0)} className="text-gray-500 text-xs font-mono hover:text-gray-300 transition-colors cursor-pointer mb-4">&larr; Back</button>
              <h1 className="font-display text-xl text-ivory" style={{ fontWeight: 400 }}>
                {userName.trim() ? `${userName.trim()}, you're deciding between:` : "You\u2019re deciding between:"}
              </h1>
              <div className="mt-8 space-y-3">
                <div className="flex gap-2">
                  <input type="text" value={pathA} onChange={(e) => setPathA(e.target.value)} placeholder="Option A&#x2026;" aria-label="Option A"
                    className="flex-1 bg-surface border border-surface-light rounded-lg p-4 text-ivory text-base focus:border-path-risk focus:outline-none placeholder:text-ivory-faint transition-colors duration-200" />
                  <VoiceButton onResult={(text) => setPathA((prev) => prev ? `${prev} ${text}` : text)} className="self-center" />
                </div>
                <p className="text-ivory-faint text-xs text-center uppercase tracking-widest">vs</p>
                <div className="flex gap-2">
                  <input type="text" value={pathB} onChange={(e) => setPathB(e.target.value)} placeholder="Option B&#x2026;" aria-label="Option B"
                    className="flex-1 bg-surface border border-surface-light rounded-lg p-4 text-ivory text-base focus:border-path-risk focus:outline-none placeholder:text-ivory-faint transition-colors duration-200" />
                  <VoiceButton onResult={(text) => setPathB((prev) => prev ? `${prev} ${text}` : text)} className="self-center" />
                </div>
              </div>
              <p className="text-ivory-dim text-sm mt-8 leading-relaxed">Want to add some context? The more you share, the more specific the debate will be.</p>
              <p className="text-ivory-faint text-xs italic mt-1">Everything is optional.</p>
              <div className="flex gap-3 mt-8">
                <button onClick={handleAddContext} disabled={!canProceed} className="flex-1 py-3 px-6 rounded-lg text-sm bg-path-risk text-void font-medium disabled:opacity-30 disabled:cursor-not-allowed transition-opacity duration-200 cursor-pointer">Add context &rarr;</button>
                <button onClick={() => void startDebate()} disabled={!canProceed || startingDebate} className="flex-1 py-3 px-6 rounded-lg text-sm bg-transparent border border-surface-light text-ivory-dim disabled:opacity-30 disabled:cursor-not-allowed hover:border-path-safe transition-colors duration-200 cursor-pointer">
                  {startingDebate ? "Verifying..." : "Skip &mdash; just debate"}
                </button>
              </div>
            </motion.div>
          )}

          {step === 2 && (
            <motion.div key="step2" variants={slideVariants} initial="enter" animate="center" exit="exit" transition={{ duration: 0.6 }}>
              <button onClick={() => setStep(1)} className="text-gray-500 text-xs font-mono hover:text-gray-300 transition-colors cursor-pointer mb-4">&larr; Back</button>
              <h2 className="font-display text-xl text-ivory" style={{ fontWeight: 400 }}>The money stuff</h2>
              <p className="text-ivory-dim text-sm mt-1">Helps the debate be specific about finances.</p>
              <div className="mt-8 space-y-5">
                {[{ label: "What do you make now?", val: salary, set: setSalary }, { label: "What would the other path pay?", val: salaryNew, set: setSalaryNew }, { label: "How much do you have saved?", val: savings, set: setSavings }].map(({ label, val, set }) => (
                  <div key={label}>
                    <label className="text-ivory-dim text-sm block mb-1.5">{label}</label>
                    <div className="relative">
                      <span className="absolute left-4 top-1/2 -translate-y-1/2 text-ivory-faint font-mono text-sm">$</span>
                      <input type="number" value={val} onChange={(e) => set(e.target.value)} placeholder="rough estimate is fine"
                        className="w-full bg-surface border border-surface-light rounded-lg p-4 pl-8 text-ivory font-mono text-sm text-right focus:border-path-risk focus:outline-none placeholder:text-ivory-faint placeholder:font-body placeholder:text-left transition-colors duration-200" />
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex gap-3 mt-8">
                <button onClick={() => setStep(3)} className="flex-1 py-3 px-6 rounded-lg text-sm bg-path-risk text-void font-medium cursor-pointer transition-opacity duration-200">That&rsquo;s enough &#10003;</button>
                <button onClick={() => setStep(3)} className="flex-1 py-3 px-6 rounded-lg text-sm bg-transparent border border-surface-light text-ivory-dim hover:border-ivory-dim transition-colors duration-200 cursor-pointer">One more thing &rarr;</button>
              </div>
            </motion.div>
          )}

          {step === 3 && (
            <motion.div key="step3" variants={slideVariants} initial="enter" animate="center" exit="exit" transition={{ duration: 0.6 }}>
              <button onClick={() => setStep(showMoney ? 2 : 1)} className="text-gray-500 text-xs font-mono hover:text-gray-300 transition-colors cursor-pointer mb-4">&larr; Back</button>
              <h2 className="font-display text-xl text-ivory" style={{ fontWeight: 400 }}>What&rsquo;s the situation?</h2>
              <p className="text-ivory-dim text-sm mt-1">Why is this decision hard? Any background that would help.</p>
              <textarea
                value={context}
                onChange={(e) => setContext(e.target.value.slice(0, 500))}
                placeholder="e.g. I've been thinking about this for months. The thing that scares me is&#x2026;"
                rows={3}
                className="w-full mt-4 bg-surface border border-surface-light rounded-lg p-4 text-ivory text-sm leading-relaxed resize-none focus:border-path-risk focus:outline-none placeholder:text-ivory-faint transition-colors duration-200"
              />
              <p className="text-ivory-faint text-[11px] font-mono text-right mt-1">{context.length} / 500</p>

              <div className="mt-8">
                <h2 className="font-display text-xl text-ivory" style={{ fontWeight: 400 }}>What matters most?</h2>
                <p className="text-ivory-dim text-sm mt-1">Pick up to 3.</p>
                <div className="mt-4"><ValuesChips selected={values} onChange={setValues} /></div>
              </div>
              <div className="mt-8">
                <h2 className="font-display text-xl text-ivory" style={{ fontWeight: 400 }}>How do you talk?</h2>
                <p className="text-ivory-dim text-sm mt-1">Paste a few texts or emails that sound like you. This makes the debate personal.</p>
                <div className="mt-4"><WritingSampleInput value={writingSample} onChange={setWritingSample} /></div>
              </div>
              <p className="text-ivory-faint text-[11px] mt-10 text-center leading-relaxed">
                Diverge is a decision exploration tool, not therapy or medical advice.<br />
                If you&rsquo;re in crisis, call <a href="tel:988" className="underline underline-offset-2">988</a> or text HOME to 741741.
              </p>
              <button onClick={() => void startDebate()} disabled={startingDebate} className="w-full mt-4 py-4 rounded-lg text-base bg-path-risk text-void font-medium tracking-wide cursor-pointer transition-colors duration-200 hover:shadow-[0_0_24px_rgba(212,168,67,0.15)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-path-risk disabled:opacity-60 disabled:cursor-not-allowed">
                {startingDebate ? "Verifying..." : "Start the debate \u2192"}
              </button>
            </motion.div>
          )}
        </AnimatePresence>
        <div className="mt-10">
          <div className="w-full h-0.5 bg-surface-light rounded-full overflow-hidden">
            <motion.div className="h-full bg-path-risk" animate={{ width: `${(displayStep() / totalSteps) * 100}%` }} transition={{ duration: 0.6 }} />
          </div>
          <p className="text-ivory-faint text-xs font-mono mt-2 text-center">Step {displayStep()} of {totalSteps}</p>
        </div>
      </div>
    </div>
  );
}
