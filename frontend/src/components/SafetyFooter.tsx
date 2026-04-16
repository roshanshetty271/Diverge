export default function SafetyFooter() {
  return (
    <footer className="w-full text-center py-3 px-4">
      <p className="text-gray-500 text-xs">
        Not a substitute for professional help. Crisis?{" "}
        <a href="tel:988" className="underline underline-offset-2 hover:text-ivory-faint transition-colors">
          Call 988
        </a>
        .
      </p>
    </footer>
  );
}
