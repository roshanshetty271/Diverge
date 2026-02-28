interface Props {
  value: string;
  onChange: (value: string) => void;
}

const MAX_CHARS = 2000;
const MIN_CHARS = 50;

export default function WritingSampleInput({ value = "", onChange }: Props) {
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value.slice(0, MAX_CHARS));
  };
  const charCount = value.length;
  const isTooShort = charCount > 0 && charCount < MIN_CHARS;

  return (
    <div>
      <textarea value={value} onChange={handleChange} placeholder="texts, emails, tweets, voice notes — whatever feels like you..." maxLength={MAX_CHARS} aria-label="Writing samples for voice matching"
        className="w-full min-h-[120px] resize-y bg-surface border border-surface-light rounded-lg p-4 text-ivory text-sm font-mono leading-relaxed placeholder:text-ivory-faint focus:border-path-risk focus:outline-none transition-colors duration-200" />
      <div className="flex justify-between items-center mt-1.5">
        {isTooShort && <p className="text-ivory-faint text-xs">A bit more helps — need at least {MIN_CHARS} characters</p>}
        <p className="text-ivory-faint text-xs font-mono ml-auto">{charCount.toLocaleString()} / {MAX_CHARS.toLocaleString()}</p>
      </div>
    </div>
  );
}
