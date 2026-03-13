import { useEffect, useRef, memo } from "react";

interface AnimatedForkPathProps {
  progress: number; // 0.0 to 1.0
  className?: string;
}

function AnimatedForkPath({ progress, className = "" }: AnimatedForkPathProps) {
  const pathAlphaRef = useRef<SVGPathElement>(null);
  const pathBetaRef = useRef<SVGPathElement>(null);
  const nodeRootRef = useRef<SVGCircleElement>(null);
  const nodeAlphaRef = useRef<SVGCircleElement>(null);
  const nodeBetaRef = useRef<SVGCircleElement>(null);

  useEffect(() => {
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    
    // Animate SVG paths based on progress
    if (pathAlphaRef.current && pathBetaRef.current) {
      const pathLength = 1000; // Fixed length matching the HTML reference
      const offset = pathLength * (1 - progress);
      
      pathAlphaRef.current.style.strokeDasharray = `${pathLength}`;
      pathAlphaRef.current.style.strokeDashoffset = `${offset}`;
      
      pathBetaRef.current.style.strokeDasharray = `${pathLength}`;
      pathBetaRef.current.style.strokeDashoffset = `${offset}`;

      // Disable transition if reduced motion is preferred
      if (prefersReducedMotion) {
        pathAlphaRef.current.style.transition = "none";
        pathBetaRef.current.style.transition = "none";
      }
    }

    // Show endpoint nodes when progress is complete
    if (progress >= 0.95) {
      if (nodeAlphaRef.current) {
        nodeAlphaRef.current.style.opacity = "1";
        if (prefersReducedMotion) {
          nodeAlphaRef.current.style.transition = "none";
        }
      }
      if (nodeBetaRef.current) {
        nodeBetaRef.current.style.opacity = "1";
        if (prefersReducedMotion) {
          nodeBetaRef.current.style.transition = "none";
        }
      }
    }
  }, [progress]);

  return (
    <div className={`relative ${className}`}>
      <svg
        className="w-full h-full"
        viewBox="0 0 200 150"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ filter: "drop-shadow(0 0 8px rgba(212, 168, 67, 0.4))" }}
      >
        {/* Gradients */}
        <defs>
          <linearGradient id="gradient-blue" x1="100" y1="100" x2="40" y2="20" gradientUnits="userSpaceOnUse">
            <stop stopColor="#4a6fa5" />
            <stop offset="1" stopColor="#4a6fa5" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="gradient-amber" x1="100" y1="100" x2="160" y2="20" gradientUnits="userSpaceOnUse">
            <stop stopColor="#d4a843" />
            <stop offset="1" stopColor="#d4a843" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Root Path (stem from bottom to fork point) */}
        <path
          d="M100 150 V100"
          stroke="#333"
          strokeWidth="2"
          strokeLinecap="round"
        />

        {/* Left path (Alpha - Blue) - from fork point up-left */}
        <path
          ref={pathAlphaRef}
          d="M100 100 C 100 70, 40 70, 40 20"
          stroke="url(#gradient-blue)"
          strokeWidth="3"
          strokeLinecap="round"
          fill="none"
          style={{
            strokeDasharray: 1000,
            strokeDashoffset: 1000,
            transition: "stroke-dashoffset 2s ease-in-out",
            willChange: "stroke-dashoffset",
          }}
        />

        {/* Right path (Beta - Amber) - from fork point up-right */}
        <path
          ref={pathBetaRef}
          d="M100 100 C 100 70, 160 70, 160 20"
          stroke="url(#gradient-amber)"
          strokeWidth="3"
          strokeLinecap="round"
          fill="none"
          style={{
            strokeDasharray: 1000,
            strokeDashoffset: 1000,
            transition: "stroke-dashoffset 2s ease-in-out",
            willChange: "stroke-dashoffset",
          }}
        />

        {/* Glow nodes */}
        <circle 
          ref={nodeRootRef}
          cx="100" 
          cy="100" 
          r="4" 
          fill="#4a6fa5" 
          className="shadow-lg"
          style={{ transition: "all 0.5s ease-out" }}
        />
        
        <circle
          ref={nodeAlphaRef}
          cx="40"
          cy="20"
          r="3"
          fill="#4a6fa5"
          className="opacity-0"
          style={{ 
            transition: "all 0.5s ease-out",
            willChange: "opacity",
          }}
        />
        
        <circle
          ref={nodeBetaRef}
          cx="160"
          cy="20"
          r="3"
          fill="#d4a843"
          className="opacity-0"
          style={{ 
            transition: "all 0.5s ease-out",
            willChange: "opacity",
          }}
        />
      </svg>
    </div>
  );
}

export default memo(AnimatedForkPath);
