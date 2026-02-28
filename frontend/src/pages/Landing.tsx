import { useNavigate } from "react-router-dom";
import { StaggerGroup, StaggerItem } from "../components/Stagger";

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 relative bg-atmosphere">
      <StaggerGroup className="flex flex-col items-center text-center relative z-10">
        <StaggerItem>
          <h1 className="font-display text-5xl md:text-6xl text-ivory tracking-[0.25em] uppercase" style={{ fontWeight: 400 }}>Diverge</h1>
        </StaggerItem>
        <StaggerItem className="mt-8 max-w-md">
          <p className="text-ivory-dim italic text-lg leading-relaxed">Every decision has two costs.</p>
          <p className="text-ivory-dim italic text-lg leading-relaxed mt-1">The cost of doing it &mdash; and the cost of not doing it.</p>
        </StaggerItem>
        <StaggerItem className="mt-4">
          <p className="text-ivory-faint text-sm">Watch two versions of your future self argue it out.</p>
        </StaggerItem>
        <StaggerItem className="mt-12">
          <button onClick={() => navigate("/decide")} className="px-8 py-4 rounded-lg text-ivory text-base bg-transparent border border-path-risk transition-colors duration-300 cursor-pointer hover:shadow-[0_0_20px_rgba(212,168,67,0.12)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-path-risk">
            I have a decision to make
          </button>
        </StaggerItem>
      </StaggerGroup>
      <div className="absolute bottom-8 text-center z-10">
        <p className="text-ivory-faint text-xs tracking-widest uppercase">Sic Mundus Creatus Est</p>
        <p className="text-ivory-faint/50 text-xs italic mt-1">Thus the world is created.</p>
      </div>
    </div>
  );
}
