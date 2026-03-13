import { Link, useNavigate } from "react-router-dom";
import { isCognitoConfigured } from "../utils/auth";

export default function Navbar() {
  const navigate = useNavigate();
  const goDecide = () => navigate("/decide");

  return (
    <nav className="fixed top-0 w-full z-50 bg-void/90 border-b border-white/10 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-6 py-2.5 flex justify-between items-center">
        <Link to="/" className="text-path-risk font-display text-lg font-bold tracking-widest hover:brightness-110 transition-all">
          DIVERGE
        </Link>
        <div className="hidden md:flex items-center space-x-6">
          <Link to="/decide" className="text-[10px] uppercase tracking-widest text-gray-400 hover:text-path-risk transition-colors">Decide</Link>
          {isCognitoConfigured() && (
            <Link to="/journal" className="text-[10px] uppercase tracking-widest text-gray-400 hover:text-path-risk transition-colors">Journal</Link>
          )}
          <Link to="/crisis" className="text-[9px] uppercase tracking-widest text-gray-500 hover:text-ivory transition-colors">Crisis Resources</Link>
        </div>
        <button
          className="px-4 py-1.5 border border-path-risk text-path-risk text-[10px] uppercase tracking-widest hover:bg-path-risk hover:text-void transition-all duration-500 cursor-pointer"
          onClick={goDecide}
        >
          Begin Simulation
        </button>
      </div>
    </nav>
  );
}
