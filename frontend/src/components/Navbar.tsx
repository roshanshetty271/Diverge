import { Link } from "react-router-dom";
import ForkPath from "./ForkPath";
import { isCognitoConfigured } from "../utils/auth";

export default function Navbar() {
  return (
    <nav className="h-12 flex items-center justify-between px-6 border-b border-surface-light/30">
      <Link to="/" className="flex items-center gap-2 text-ivory hover:text-path-risk transition-colors">
        <ForkPath variant="icon" />
        <span className="font-display text-sm tracking-[0.15em] uppercase" style={{ fontWeight: 400 }}>Diverge</span>
      </Link>
      <div className="flex items-center gap-4">
        {isCognitoConfigured() && (
          <Link to="/journal" className="text-ivory-faint text-xs font-mono tracking-wider uppercase hover:text-ivory transition-colors">
            Journal
          </Link>
        )}
        <Link to="/crisis" className="text-ivory-faint/60 text-[11px] hover:text-ivory-faint transition-colors">
          Need help?
        </Link>
      </div>
    </nav>
  );
}
