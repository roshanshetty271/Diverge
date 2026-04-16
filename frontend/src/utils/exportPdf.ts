import jsPDF from "jspdf";
import type { DebateResponse, DecisionInput, Resource } from "../types";

const VOID = "#0a0a0a";
const SURFACE = "#141414";
const IVORY = "#f0ece2";
const DIM = "#a09a8e";
const LIGHT = "#ccc5b9";
const SAFE = "#4a6fa5";
const RISK = "#d4a843";

const MARGIN = 20;
const LINE_H = 4.2;
const BODY_SIZE = 9;
const LABEL_SIZE = 8;
const HEADING_SIZE = 11;

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

function ensurePage(doc: jsPDF, y: number, needed: number): number {
  const pageH = doc.internal.pageSize.getHeight();
  if (y + needed > pageH - 15) {
    doc.addPage();
    doc.setFillColor(VOID);
    doc.rect(0, 0, doc.internal.pageSize.getWidth(), pageH, "F");
    return MARGIN;
  }
  return y;
}

function drawText(doc: jsPDF, text: string, x: number, y: number, maxW: number, lineH: number): number {
  const lines = doc.splitTextToSize(text, maxW);
  for (const line of lines) {
    y = ensurePage(doc, y, lineH + 2);
    doc.text(line, x, y);
    y += lineH;
  }
  return y;
}

export function generateDebatePdf(debate: DebateResponse, input: DecisionInput | null): void {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const contentW = pageW - MARGIN * 2;
  let y = MARGIN;

  // Background
  doc.setFillColor(VOID);
  doc.rect(0, 0, pageW, doc.internal.pageSize.getHeight(), "F");

  // Title
  doc.setFont("helvetica", "bold");
  doc.setFontSize(24);
  doc.setTextColor(RISK);
  doc.text("DIVERGE", pageW / 2, y, { align: "center" });
  y += 8;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(DIM);
  doc.text("Decision Intelligence Report", pageW / 2, y, { align: "center" });
  y += 14;

  // Decision
  const pathA = input?.path_a || "Option A";
  const pathB = input?.path_b || "Option B";

  doc.setFontSize(13);
  doc.setTextColor(SAFE);
  doc.text(pathA, pageW / 2 - 8, y, { align: "right", maxWidth: contentW / 2 - 12 });
  doc.setFontSize(10);
  doc.setTextColor(DIM);
  doc.text("vs.", pageW / 2, y, { align: "center" });
  doc.setFontSize(13);
  doc.setTextColor(RISK);
  doc.text(pathB, pageW / 2 + 8, y, { align: "left", maxWidth: contentW / 2 - 12 });
  y += 14;

  // Separator
  doc.setDrawColor(DIM);
  doc.setLineWidth(0.3);
  doc.line(MARGIN, y, pageW - MARGIN, y);
  y += 10;

  // Rounds
  for (const round of debate.transcript) {
    y = ensurePage(doc, y, 30);

    // Round heading
    doc.setFont("helvetica", "bold");
    doc.setFontSize(HEADING_SIZE);
    doc.setTextColor(IVORY);
    doc.text(`Round ${round.round_number}: ${round.round_name}`, MARGIN, y);
    y += 3;

    // Subtle line under heading
    doc.setDrawColor(SURFACE);
    doc.setLineWidth(0.2);
    doc.line(MARGIN, y, MARGIN + 40, y);
    y += 6;

    // Alpha
    doc.setFont("helvetica", "bold");
    doc.setFontSize(LABEL_SIZE);
    doc.setTextColor(SAFE);
    doc.text(pathA, MARGIN, y);
    y += 5;
    doc.setFont("helvetica", "normal");
    doc.setFontSize(BODY_SIZE);
    doc.setTextColor(LIGHT);
    y = drawText(doc, stripMarkdown(round.alpha), MARGIN, y, contentW, LINE_H);
    y += 5;

    // Beta
    y = ensurePage(doc, y, 15);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(LABEL_SIZE);
    doc.setTextColor(RISK);
    doc.text(pathB, MARGIN, y);
    y += 5;
    doc.setFont("helvetica", "normal");
    doc.setFontSize(BODY_SIZE);
    doc.setTextColor(LIGHT);
    y = drawText(doc, stripMarkdown(round.beta), MARGIN, y, contentW, LINE_H);
    y += 10;
  }

  // Verdict
  if (debate.verdict) {
    y = ensurePage(doc, y, 30);

    doc.setDrawColor(RISK);
    doc.setLineWidth(0.5);
    doc.line(MARGIN, y, MARGIN + 25, y);
    y += 7;

    doc.setFont("helvetica", "bold");
    doc.setFontSize(14);
    doc.setTextColor(IVORY);
    doc.text("THE VERDICT", MARGIN, y);
    y += 9;

    doc.setFont("helvetica", "normal");
    doc.setFontSize(BODY_SIZE);
    doc.setTextColor(LIGHT);
    y = drawText(doc, stripMarkdown(debate.verdict), MARGIN, y, contentW, LINE_H);
    y += 8;
  }

  // Resources
  const resources: Resource[] = resolveResources(debate);
  if (resources.length > 0) {
    y = ensurePage(doc, y, 25);

    doc.setFont("helvetica", "bold");
    doc.setFontSize(HEADING_SIZE);
    doc.setTextColor(IVORY);
    doc.text("WHAT TO EXPLORE NEXT", MARGIN, y);
    y += 8;

    for (const r of resources) {
      y = ensurePage(doc, y, 12);
      doc.setFont("helvetica", "bold");
      doc.setFontSize(LABEL_SIZE);
      doc.setTextColor(IVORY);
      doc.text(`[${r.type.toUpperCase()}] ${r.title} \u2014 ${r.author}`, MARGIN, y);
      y += 4.5;
      doc.setFont("helvetica", "normal");
      doc.setFontSize(BODY_SIZE);
      doc.setTextColor(DIM);
      y = drawText(doc, r.why, MARGIN + 2, y, contentW - 4, LINE_H);
      y += 4;
    }
  }

  // Ethical stance
  y = ensurePage(doc, y, 20);
  y += 6;
  doc.setDrawColor(DIM);
  doc.setLineWidth(0.2);
  doc.line(MARGIN + 40, y, pageW - MARGIN - 40, y);
  y += 6;
  doc.setFont("helvetica", "normal");
  doc.setFontSize(7);
  doc.setTextColor(DIM);
  doc.text("All metrics are AI estimates. This is not therapy, medical, or legal advice.", pageW / 2, y, { align: "center" });
  y += 4;
  doc.text("Your lived experience matters more than any model output.", pageW / 2, y, { align: "center" });

  // Footer
  const footerY = doc.internal.pageSize.getHeight() - 12;
  doc.setFont("helvetica", "italic");
  doc.setFontSize(8);
  doc.setTextColor(DIM);
  doc.text("Sic Mundus Creatus Est. \u2014 Diverge", pageW / 2, footerY, { align: "center" });

  const fileName = `diverge-${pathA.slice(0, 20).replace(/\s+/g, "-")}-vs-${pathB.slice(0, 20).replace(/\s+/g, "-")}.pdf`;
  doc.save(fileName);
}
