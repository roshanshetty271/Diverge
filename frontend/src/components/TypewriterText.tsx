import { motion } from "framer-motion";

interface Props {
  text: string;
  speed?: number;
}

export default function TypewriterText({ text, speed = 0.04 }: Props) {
  if (!text) return null;
  const words = text.split(" ");

  return (
    <span>
      {words.map((word, i) => (
        <motion.span
          key={i}
          className="inline"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: i * speed, duration: 0.05 }}
        >
          {word}{i < words.length - 1 ? " " : ""}
        </motion.span>
      ))}
    </span>
  );
}
