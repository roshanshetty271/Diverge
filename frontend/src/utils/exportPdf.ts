import jsPDF from "jspdf";
import type { DebateResponse, DecisionInput, Resource } from "../types";

const VOID = "#0a0a0a";
const IVORY = "#f0ece2";
const DIM = "#a09a8e";
const SAFE = "#4a6fa5";
const RISK = "#d4a843";

function stripMarkdown(t: string): string {
  return t
    .replace(/\*\*/g, "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}

function resolveResources(debate: DebateResponse): Resource[] {
  const structured = debate.timeline?.stage_06_what_to_explore_next || [];
  if (structured.length > 0) {
    return structured.slice(0, 3).map((item) => ({
      type: item.type,
      title: item.title,
      author: item.author,
      url: item.url,
      why: stripMarkdown(item.why_it_helps || ""),
    }));
  }

  return (debate.resources || []).slice(0, 3);
}

export function generateDebatePdf(debate: DebateResponse, input: DecisionInput | null): void {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const margin = 20;
  const contentW = pageW - margin * 2;
  let y = margin;

  // Background
  doc.setFillColor(VOID);
  doc.rect(0, 0, pageW, doc.internal.pageSize.getHeight(), "F");

  // Title
  doc.setFont("helvetica", "bold");
  doc.setFontSize(22);
  doc.setTextColor(IVORY);
  doc.text("DIVERGE", pageW / 2, y, { align: "center" });
  y += 8;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(DIM);
  doc.text("Decision Intelligence Report", pageW / 2, y, { align: "center" });
  y += 12;

  // Decision
  const pathA = input?.path_a || "Option A";
  const pathB = input?.path_b || "Option B";

  doc.setFontSize(12);
  doc.setTextColor(SAFE);
  doc.text(pathA, pageW / 2 - 5, y, { align: "right", maxWidth: contentW / 2 - 10 });
  doc.setTextColor(DIM);
  doc.text("vs.", pageW / 2, y, { align: "center" });
  doc.setTextColor(RISK);
  doc.text(pathB, pageW / 2 + 5, y, { align: "left", maxWidth: contentW / 2 - 10 });
  y += 12;

  // Separator
  doc.setDrawColor(DIM);
  doc.setLineWidth(0.3);
  doc.line(margin, y, pageW - margin, y);
  y += 8;

  // Rounds
  for (const round of debate.transcript) {
    if (y > 260) {
      doc.addPage();
      doc.setFillColor(VOID);
      doc.rect(0, 0, pageW, doc.internal.pageSize.getHeight(), "F");
      y = margin;
    }

    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    doc.setTextColor(IVORY);
    doc.text(`Round ${round.round_number}: ${round.round_name}`, margin, y);
    y += 6;

    // Alpha
    doc.setFont("helvetica", "bold");
    doc.setFontSize(8);
    doc.setTextColor(SAFE);
    doc.text(pathA, margin, y);
    y += 4;
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(DIM);
    const alphaLines = doc.splitTextToSize(round.alpha.slice(0, 500), contentW);
    doc.text(alphaLines, margin, y);
    y += alphaLines.length * 3.5 + 4;

    // Beta
    doc.setFont("helvetica", "bold");
    doc.setTextColor(RISK);
    doc.text(pathB, margin, y);
    y += 4;
    doc.setFont("helvetica", "normal");
    doc.setTextColor(DIM);
    const betaLines = doc.splitTextToSize(round.beta.slice(0, 500), contentW);
    doc.text(betaLines, margin, y);
    y += betaLines.length * 3.5 + 8;
  }

  // Verdict
  if (debate.verdict) {
    if (y > 220) {
      doc.addPage();
      doc.setFillColor(VOID);
      doc.rect(0, 0, pageW, doc.internal.pageSize.getHeight(), "F");
      y = margin;
    }

    doc.setDrawColor(RISK);
    doc.setLineWidth(0.5);
    doc.line(margin, y, margin + 20, y);
    y += 6;

    doc.setFont("helvetica", "bold");
    doc.setFontSize(12);
    doc.setTextColor(IVORY);
    doc.text("THE VERDICT", margin, y);
    y += 8;

    doc.setFont("helvetica", "normal");
    doc.setFontSize(9);
    doc.setTextColor(DIM);
    const verdictClean = stripMarkdown(debate.verdict);
    const verdictLines = doc.splitTextToSize(verdictClean, contentW);
    for (const line of verdictLines) {
      if (y > 275) {
        doc.addPage();
        doc.setFillColor(VOID);
        doc.rect(0, 0, pageW, doc.internal.pageSize.getHeight(), "F");
        y = margin;
      }
      doc.text(line, margin, y);
      y += 4;
    }
    y += 6;
  }

  // Resources
  const resources: Resource[] = resolveResources(debate);
  if (resources.length > 0) {
    if (y > 250) {
      doc.addPage();
      doc.setFillColor(VOID);
      doc.rect(0, 0, pageW, doc.internal.pageSize.getHeight(), "F");
      y = margin;
    }

    doc.setFont("helvetica", "bold");
    doc.setFontSize(10);
    doc.setTextColor(IVORY);
    doc.text("WHAT TO EXPLORE NEXT", margin, y);
    y += 6;

    for (const r of resources) {
      doc.setFont("helvetica", "bold");
      doc.setFontSize(8);
      doc.setTextColor(IVORY);
      doc.text(`[${r.type.toUpperCase()}] ${r.title} — ${r.author}`, margin, y);
      y += 4;
      doc.setFont("helvetica", "normal");
      doc.setTextColor(DIM);
      doc.text(r.why, margin + 2, y, { maxWidth: contentW - 4 });
      y += 6;
    }
  }

  // Footer
  y = doc.internal.pageSize.getHeight() - 15;
  doc.setFont("helvetica", "italic");
  doc.setFontSize(8);
  doc.setTextColor(DIM);
  doc.text("Sic Mundus Creatus Est. \u2014 Diverge", pageW / 2, y, { align: "center" });

  const fileName = `diverge-${pathA.slice(0, 20).replace(/\s+/g, "-")}-vs-${pathB.slice(0, 20).replace(/\s+/g, "-")}.pdf`;
  doc.save(fileName);
}
