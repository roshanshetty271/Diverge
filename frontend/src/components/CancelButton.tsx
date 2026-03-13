interface CancelButtonProps {
  onCancel: () => void;
}

export default function CancelButton({ onCancel }: CancelButtonProps) {
  return (
    <button
      onClick={onCancel}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onCancel();
        }
      }}
      className="text-[10px] uppercase tracking-[0.2em] text-white/20 hover:text-white/60 focus:text-white/60 focus:outline-none transition-colors duration-300 cursor-pointer"
      aria-label="Cancel ongoing debate simulation"
      tabIndex={0}
    >
      Cancel Simulation
    </button>
  );
}
