import { useNavigate } from "react-router-dom";

export default function Landing() {
  const navigate = useNavigate();
  const goDecide = () => navigate("/decide");

  return (
    <div className="bg-void overflow-x-hidden">
      {/* Hero Section */}
      <section className="relative min-h-[80vh] flex items-center justify-center pt-24 px-6 mb-12">
        <div className="text-center max-w-4xl">
          <p className="text-path-risk mb-4 tracking-[0.4em] text-sm font-display animate-pulse-slow">
            SIC MUNDUS CREATUS EST
          </p>
          <h1 className="text-4xl md:text-6xl font-black mb-6 leading-tight font-display tracking-[0.1em]">
            The 2 AM <span className="text-path-risk glow-amber">Crossroads</span>
          </h1>
          <p className="text-lg md:text-xl text-gray-400 font-light mb-10 max-w-2xl mx-auto leading-relaxed">
            Career pivot or stay put? New city or familiar ground? Your mind is a maze of &ldquo;what ifs.&rdquo; We are the exit.
          </p>
          <div className="flex items-center justify-center">
            <button
              className="w-full md:w-auto px-8 py-3 bg-path-risk text-void font-bold uppercase tracking-widest hover:bg-white transition-all cursor-pointer text-sm"
              onClick={goDecide}
            >
              Step Into The Rift
            </button>
          </div>
        </div>
      </section>

      {/* Core Value Prop */}
      <section id="engine" className="py-20 bg-void border-y border-white/5">
        <div className="max-w-7xl mx-auto px-6 text-center">
          <h2 className="text-path-risk text-2xl md:text-4xl font-display tracking-[0.1em] mb-4">
            &ldquo;Inaction is the most expensive decision.&rdquo;
          </h2>
          <div className="h-1 w-16 bg-path-safe mx-auto mb-6" />
          <p className="text-gray-500 max-w-xl mx-auto italic text-sm md:text-base">
            Every moment spent in indecision is a branch of reality you&rsquo;ve allowed to wither. Diverge doesn&rsquo;t just predict; it forces you to inhabit the consequences.
          </p>
        </div>
      </section>

      {/* The Mirror Section */}
      <section id="mirror" className="py-24 bg-void overflow-hidden">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid md:grid-cols-2 gap-16 items-center">
            {/* Split visual — two contrasting paths */}
            <div className="relative">
              <div className="grid grid-cols-2 gap-0 aspect-[4/5] overflow-hidden border border-white/10">
                {/* Path Alpha side */}
                <div className="bg-gradient-to-b from-path-safe/20 to-void flex flex-col items-center justify-center p-8 border-r border-white/10">
                  <span className="font-display text-path-safe text-6xl font-black mb-4">&alpha;</span>
                  <span className="text-xs uppercase tracking-widest text-path-safe/60">Safety</span>
                  <div className="mt-8 space-y-3 text-left w-full">
                    <div className="h-2 bg-path-safe/20 rounded w-full" />
                    <div className="h-2 bg-path-safe/15 rounded w-4/5" />
                    <div className="h-2 bg-path-safe/10 rounded w-3/5" />
                    <div className="h-2 bg-path-safe/30 rounded w-full" />
                    <div className="h-2 bg-path-safe/15 rounded w-2/3" />
                  </div>
                </div>
                {/* Path Beta side */}
                <div className="bg-gradient-to-b from-path-risk/20 to-void flex flex-col items-center justify-center p-8">
                  <span className="font-display text-path-risk text-6xl font-black mb-4">&beta;</span>
                  <span className="text-xs uppercase tracking-widest text-path-risk/60">Risk</span>
                  <div className="mt-8 space-y-3 text-left w-full">
                    <div className="h-2 bg-path-risk/15 rounded w-full" />
                    <div className="h-2 bg-path-risk/20 rounded w-4/5" />
                    <div className="h-2 bg-path-risk/25 rounded w-full" />
                    <div className="h-2 bg-path-risk/15 rounded w-3/4" />
                    <div className="h-2 bg-path-risk/10 rounded w-1/2" />
                  </div>
                </div>
              </div>
            </div>

            <div>
              <h3 className="text-path-risk text-xs tracking-[0.3em] font-display mb-3">ROUND 3: THE MIRROR</h3>
              <h2 className="text-3xl md:text-5xl font-display tracking-[0.1em] mb-6 leading-tight">
                Face Your <span className="text-path-safe glow-blue">Counterpart</span>
              </h2>
              <p className="text-base text-gray-400 mb-6">
                The Mirror is where the math ends and the soul begins. Diverge doesn&rsquo;t just show data&mdash;it simulates the version of you that chose the other path, then forces a direct debate between who you are and who you could become.
              </p>
              <div className="space-y-4">
                <div className="flex gap-4 items-start">
                  <div className="w-6 h-6 rounded-full border border-path-risk flex-shrink-0 flex items-center justify-center text-path-risk text-[10px]">1</div>
                  <p className="text-xs text-gray-300">Watch two AI agents argue your decision from opposite sides, in real time.</p>
                </div>
                <div className="flex gap-4 items-start">
                  <div className="w-6 h-6 rounded-full border border-path-risk flex-shrink-0 flex items-center justify-center text-path-risk text-[10px]">2</div>
                  <p className="text-xs text-gray-300">See the financial, emotional, and identity trade-offs mapped across 10 years.</p>
                </div>
                <div className="flex gap-4 items-start">
                  <div className="w-6 h-6 rounded-full border border-path-risk flex-shrink-0 flex items-center justify-center text-path-risk text-[10px]">3</div>
                  <p className="text-xs text-gray-300">Interject mid-debate to challenge either agent with your own context.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* The 5 Rounds */}
      <section id="rounds" className="py-24 bg-[#050505]">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-display tracking-[0.1em] mb-3">The Simulation Engine</h2>
            <p className="text-path-risk tracking-widest text-xs uppercase">Chronological Debate Sequence</p>
          </div>
          <div className="grid md:grid-cols-5 gap-3 relative">
            {/* Connecting Line Background */}
            <div className="hidden md:block absolute top-1/2 left-0 w-full h-px bg-white/10 -z-0" />

            {/* Round 1 */}
            <div className="bg-void p-6 border border-white/5 relative z-10 hover:border-path-risk transition-colors group">
              <span className="text-path-risk font-display text-lg mb-3 block">01</span>
              <h4 className="font-display tracking-[0.1em] text-base mb-2 group-hover:text-path-risk transition-colors">The Fork</h4>
              <p className="text-[10px] text-gray-500 uppercase mb-3 tracking-tighter">Year 1</p>
              <p className="text-xs text-gray-400">The immediate split. Your first 12 months diverge&mdash;one path plays it safe, the other bets everything.</p>
            </div>

            {/* Round 2 */}
            <div className="bg-void p-6 border border-white/5 relative z-10 hover:border-path-risk transition-colors group">
              <span className="text-path-risk font-display text-lg mb-3 block">02</span>
              <h4 className="font-display tracking-[0.1em] text-base mb-2 group-hover:text-path-risk transition-colors">The Ledger</h4>
              <p className="text-[10px] text-gray-500 uppercase mb-3 tracking-tighter">Year 2-3</p>
              <p className="text-xs text-gray-400">The compounding costs. Alpha and Beta debate money, health, relationships, and opportunity cost.</p>
            </div>

            {/* Round 3 — highlighted */}
            <div className="bg-void p-6 border border-path-risk/50 relative z-10 shadow-[0_0_20px_rgba(212,168,67,0.1)] group">
              <span className="text-path-risk font-display text-lg mb-3 block">03</span>
              <h4 className="font-display tracking-[0.1em] text-base mb-2 text-path-risk">The Mirror</h4>
              <p className="text-[10px] text-gray-500 uppercase mb-3 tracking-tighter">Year 5</p>
              <p className="text-xs text-gray-400">Identity crisis. The person you become in each path confronts your current core values.</p>
            </div>

            {/* Round 4 */}
            <div className="bg-void p-6 border border-white/5 relative z-10 hover:border-path-risk transition-colors group">
              <span className="text-path-risk font-display text-lg mb-3 block">04</span>
              <h4 className="font-display tracking-[0.1em] text-base mb-2 group-hover:text-path-risk transition-colors">The Ghost</h4>
              <p className="text-[10px] text-gray-500 uppercase mb-3 tracking-tighter">Year 10</p>
              <p className="text-xs text-gray-400">The long view. What do you regret? What are you grateful for? Which version sleeps better?</p>
            </div>

            {/* Round 5 */}
            <div className="bg-void p-6 border border-white/5 relative z-10 hover:border-path-risk transition-colors group">
              <span className="text-path-risk font-display text-lg mb-3 block">05</span>
              <h4 className="font-display tracking-[0.1em] text-base mb-2 group-hover:text-path-risk transition-colors">The Knot</h4>
              <p className="text-[10px] text-gray-500 uppercase mb-3 tracking-tighter">Final Words</p>
              <p className="text-xs text-gray-400">The verdict. Both timelines make their closing argument. You choose The Path of Least Regret.</p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-24 relative">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <h2 className="text-3xl md:text-5xl font-display tracking-[0.1em] mb-8">
            Will you watch your life, or <span className="text-path-risk">live it?</span>
          </h2>
          <div className="bg-void p-10 border border-white/5 inline-block w-full">
            <h3 className="text-path-risk tracking-widest mb-6 font-display text-sm">YOUR DECISION AWAITS</h3>
            <button
              className="bg-path-risk text-void px-12 py-4 text-base font-bold uppercase tracking-widest hover:brightness-125 transition-all cursor-pointer"
              onClick={goDecide}
            >
              Start Your Debate
            </button>
            <p className="text-gray-600 text-[10px] mt-4 uppercase tracking-tighter">No account required. Free to use.</p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 border-t border-white/10 text-center">
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row justify-between items-center gap-8">
          <p className="text-gray-600 text-sm tracking-widest">&copy; 2025 DIVERGE &mdash; TEAM SIC MUNDUS</p>
          <p className="text-gray-600 text-xs italic">Sic Mundus Creatus Est &mdash; Thus the world is created.</p>
        </div>
      </footer>
    </div>
  );
}
