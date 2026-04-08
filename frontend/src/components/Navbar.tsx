import { Link, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
export default function Navbar() {
  const navigate = useNavigate();
  const goDecide = () => navigate("/decide");
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };

    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <nav className={`fixed top-0 w-full z-50 border-b border-white/10 backdrop-blur-md transition-all duration-300 ${
      scrolled ? "bg-void" : "bg-void/90"
    }`}>
      <div className="max-w-7xl mx-auto px-6 py-2.5 flex justify-between items-center">
        <Link to="/" className="text-path-risk font-display text-lg font-bold tracking-widest hover:brightness-110 transition-all">
          DIVERGE
        </Link>
        <div className="hidden md:flex items-center space-x-8">
          <Link to="/decide" className="text-xs uppercase tracking-widest text-gray-400 hover:text-path-risk transition-colors">Decide</Link>
          <Link to="/journal" className="text-xs uppercase tracking-widest text-gray-400 hover:text-path-risk transition-colors">Journal</Link>
          <Link to="/crisis" className="text-xs uppercase tracking-widest text-gray-400 hover:text-path-risk transition-colors">Crisis Resources</Link>
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
