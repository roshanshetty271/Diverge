import { VALUES } from "../utils/constants";

interface Props {
  selected: string[];
  onChange: (values: string[]) => void;
  max?: number;
}

export default function ValuesChips({ selected = [], onChange, max = 3 }: Props) {
  const toggle = (value: string) => {
    if (selected.includes(value)) onChange(selected.filter((v) => v !== value));
    else if (selected.length < max) onChange([...selected, value]);
  };
  const atMax = selected.length >= max;

  return (
    <div className="flex flex-wrap gap-2">
      {VALUES.map((value) => {
        const isSelected = selected.includes(value);
        const isDimmed = atMax && !isSelected;
        return (
          <button key={value} type="button" onClick={() => toggle(value)} disabled={isDimmed && !isSelected} aria-pressed={isSelected}
            className={`px-4 py-2 rounded-full text-sm transition-all duration-200 cursor-pointer ${isSelected ? "border border-path-risk text-ivory" : isDimmed ? "border border-surface-light text-ivory-faint opacity-40 cursor-default" : "border border-surface-light text-ivory-dim hover:border-ivory-dim"}`}>
            {value}
          </button>
        );
      })}
    </div>
  );
}
