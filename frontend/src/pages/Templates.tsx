import { useNavigate } from "react-router-dom";
import { StaggerGroup, StaggerItem } from "../components/Stagger";
import { TEMPLATES } from "../utils/constants";
import type { TemplateOption } from "../types";

export default function Templates() {
  const navigate = useNavigate();

  const handleSelect = (t: TemplateOption) => {
    navigate("/intake", { state: { pathA: t.pathA, pathB: t.pathB, templateId: t.id } });
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 py-16">
      <StaggerGroup className="w-full max-w-3xl">
        <StaggerItem className="text-center mb-10">
          <h1 className="font-display text-2xl text-ivory" style={{ fontWeight: 400 }}>What&rsquo;s on your mind?</h1>
          <p className="text-ivory-dim text-sm mt-2">Pick what&rsquo;s closest, or write your own.</p>
        </StaggerItem>
        <StaggerItem>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {TEMPLATES.map((t) => (
              <button key={t.id} onClick={() => handleSelect(t)}
                className={`text-left p-6 rounded-lg bg-surface border border-surface-light transition-colors duration-200 cursor-pointer group hover:border-path-risk focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-path-risk border-l-[3px] ${t.category === "financial" ? "border-l-path-risk" : "border-l-path-safe"}`}>
                <span className="text-ivory text-base block mb-1.5">{t.title}</span>
                <span className="text-ivory-dim text-sm italic block">&ldquo;{t.question}&rdquo;</span>
              </button>
            ))}
          </div>
        </StaggerItem>
        <StaggerItem className="text-center mt-8">
          <div className="flex items-center gap-4 justify-center">
            <span className="h-px w-12 bg-surface-light" />
            <span className="text-ivory-faint text-xs uppercase tracking-widest">or</span>
            <span className="h-px w-12 bg-surface-light" />
          </div>
          <button onClick={() => navigate("/intake", { state: { pathA: "", pathB: "", templateId: "custom" } })}
            className="mt-4 text-ivory-dim text-sm cursor-pointer transition-colors duration-200 hover:text-path-risk">
            Something else entirely&hellip;
          </button>
        </StaggerItem>
      </StaggerGroup>
    </div>
  );
}
