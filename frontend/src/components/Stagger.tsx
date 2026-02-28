import { motion } from "framer-motion";
import type { ReactNode } from "react";

const container = { hidden: {}, show: { transition: { staggerChildren: 0.25 } } };
const item = { hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: "easeOut" } } };

interface Props {
  children: ReactNode;
  className?: string;
}

export function StaggerGroup({ children, className = "" }: Props) {
  return <motion.div variants={container} initial="hidden" animate="show" className={className}>{children}</motion.div>;
}

export function StaggerItem({ children, className = "" }: Props) {
  return <motion.div variants={item} className={className}>{children}</motion.div>;
}
