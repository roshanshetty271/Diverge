import { useNavigate } from "react-router-dom";
import { CRISIS_RESOURCES } from "../utils/constants";

export default function CrisisResources() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 py-16 bg-void">
      <div className="max-w-md w-full text-center">
        <h1 className="font-display text-2xl text-ivory" style={{ fontWeight: 400 }}>
          We&rsquo;re not the right tool for this.
        </h1>
        <p className="text-ivory-dim text-sm mt-3 leading-relaxed">
          But these people are &mdash; they&rsquo;re free, confidential, and available 24/7.
        </p>

        <div className="mt-10 space-y-4 text-left">
          {CRISIS_RESOURCES.map((r) => (
            <div key={r.name} className="bg-surface rounded-lg border border-surface-light p-5">
              <p className="text-ivory text-base font-medium">{r.name}</p>
              <p className="text-path-risk text-sm font-mono mt-1">{r.action}</p>
              <p className="text-ivory-faint text-xs mt-1">{r.available}</p>
              {r.url && (
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-ivory-dim text-xs underline underline-offset-2 mt-2 inline-block hover:text-ivory transition-colors"
                >
                  {r.url.replace("https://", "")}
                </a>
              )}
            </div>
          ))}
        </div>

        <button
          onClick={() => navigate("/decide", { replace: true })}
          className="mt-10 px-8 py-3 rounded-lg text-sm border border-surface-light text-ivory-dim cursor-pointer transition-colors duration-200 hover:border-ivory-dim"
        >
          &larr; Go back
        </button>
      </div>
    </div>
  );
}
