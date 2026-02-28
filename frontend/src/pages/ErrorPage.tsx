import { useNavigate } from "react-router-dom";
import { StaggerGroup, StaggerItem } from "../components/Stagger";

export default function ErrorPage() {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6">
      <StaggerGroup className="text-center">
        <StaggerItem><p className="font-display text-lg text-ivory-dim italic">&ldquo;The cycle is broken.&rdquo;</p></StaggerItem>
        <StaggerItem className="mt-6"><p className="text-ivory text-sm">Something went wrong.</p></StaggerItem>
        <StaggerItem className="mt-6">
          <button onClick={() => navigate("/")} className="px-6 py-3 rounded-lg text-sm border border-path-risk text-ivory cursor-pointer transition-all duration-200 hover:shadow-[0_0_16px_rgba(212,168,67,0.1)]">Go home</button>
        </StaggerItem>
      </StaggerGroup>
    </div>
  );
}
