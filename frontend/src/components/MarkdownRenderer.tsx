/**
 * MarkdownRenderer — lightweight Markdown-to-HTML renderer.
 *
 * Supports: headings (h1–h3), bold, italic, inline code, fenced code blocks,
 * unordered lists, ordered lists, blockquotes, horizontal rules, and paragraphs.
 *
 * Zero external dependencies — implemented with a single-pass regex pipeline
 * that is safe against XSS (no dangerouslySetInnerHTML used; output is
 * constructed from React elements).
 */

import React from "react";

interface Props {
  content: string;
  className?: string;
}

// ─── Token types ──────────────────────────────────────────────────────────────

type Block =
  | { kind: "h1" | "h2" | "h3"; text: string }
  | { kind: "hr" }
  | { kind: "code_block"; lang: string; code: string }
  | { kind: "blockquote"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] }
  | { kind: "paragraph"; text: string }
  | { kind: "blank" };

// ─── Block-level parser ───────────────────────────────────────────────────────

function parseBlocks(md: string): Block[] {
  const lines = md.split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    const fenceMatch = line.match(/^```(\w*)/);
    if (fenceMatch) {
      const lang = fenceMatch[1] || "";
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // consume closing ```
      blocks.push({ kind: "code_block", lang, code: codeLines.join("\n") });
      continue;
    }

    // Headings
    const h3 = line.match(/^###\s+(.*)/);
    if (h3) { blocks.push({ kind: "h3", text: h3[1] }); i++; continue; }
    const h2 = line.match(/^##\s+(.*)/);
    if (h2) { blocks.push({ kind: "h2", text: h2[1] }); i++; continue; }
    const h1 = line.match(/^#\s+(.*)/);
    if (h1) { blocks.push({ kind: "h1", text: h1[1] }); i++; continue; }

    // Horizontal rule
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      blocks.push({ kind: "hr" }); i++; continue;
    }

    // Blockquote
    if (line.startsWith("> ")) {
      blocks.push({ kind: "blockquote", text: line.slice(2) }); i++; continue;
    }

    // Unordered list
    if (/^[-*+]\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*+]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*+]\s/, ""));
        i++;
      }
      blocks.push({ kind: "ul", items });
      continue;
    }

    // Ordered list
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, ""));
        i++;
      }
      blocks.push({ kind: "ol", items });
      continue;
    }

    // Blank line
    if (line.trim() === "") {
      blocks.push({ kind: "blank" }); i++; continue;
    }

    // Paragraph — collect consecutive non-special lines
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^(#|>|[-*+]|\d+\.|\`\`\`)/.test(lines[i]) &&
      !/^(-{3,}|\*{3,}|_{3,})$/.test(lines[i].trim())
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length > 0) {
      blocks.push({ kind: "paragraph", text: paraLines.join(" ") });
    } else {
      i++;
    }
  }

  return blocks;
}

// ─── Inline renderer (bold, italic, inline code, links) ──────────────────────

function renderInline(text: string): React.ReactNode[] {
  // Split on **bold**, *italic*, `code`, keeping delimiters
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={idx}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return <em key={idx}>{part.slice(1, -1)}</em>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={idx}
          className="px-1 py-0.5 rounded text-[11px] bg-surface-4 text-text-accent font-mono"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

// ─── Block renderer ───────────────────────────────────────────────────────────

function renderBlock(block: Block, idx: number): React.ReactNode {
  switch (block.kind) {
    case "h1":
      return (
        <h2 key={idx} className="text-sm font-bold text-text-primary mt-3 mb-1.5 leading-tight">
          {renderInline(block.text)}
        </h2>
      );
    case "h2":
      return (
        <h3 key={idx} className="text-xs font-bold text-text-primary mt-2.5 mb-1 uppercase tracking-wide">
          {renderInline(block.text)}
        </h3>
      );
    case "h3":
      return (
        <h4 key={idx} className="text-xs font-semibold text-text-secondary mt-2 mb-0.5">
          {renderInline(block.text)}
        </h4>
      );
    case "hr":
      return <hr key={idx} className="border-border my-2" />;
    case "code_block":
      return (
        <pre
          key={idx}
          className="my-2 p-2 rounded bg-surface-DEFAULT border border-border overflow-x-auto"
        >
          <code className="code-block text-[11px] text-text-primary leading-6">
            {block.code}
          </code>
        </pre>
      );
    case "blockquote":
      return (
        <blockquote
          key={idx}
          className="border-l-2 border-text-accent pl-2 my-1 text-text-muted italic text-xs"
        >
          {renderInline(block.text)}
        </blockquote>
      );
    case "ul":
      return (
        <ul key={idx} className="list-none my-1 space-y-0.5">
          {block.items.map((item, j) => (
            <li key={j} className="flex items-start gap-1.5 text-xs text-text-secondary">
              <span className="mt-1 flex-shrink-0 w-1 h-1 rounded-full bg-text-muted" aria-hidden="true" />
              <span>{renderInline(item)}</span>
            </li>
          ))}
        </ul>
      );
    case "ol":
      return (
        <ol key={idx} className="list-none my-1 space-y-0.5 counter-reset-item">
          {block.items.map((item, j) => (
            <li key={j} className="flex items-start gap-1.5 text-xs text-text-secondary">
              <span className="flex-shrink-0 text-text-muted font-mono text-[10px] mt-0.5 w-4">{j + 1}.</span>
              <span>{renderInline(item)}</span>
            </li>
          ))}
        </ol>
      );
    case "paragraph":
      return (
        <p key={idx} className="text-xs text-text-secondary leading-relaxed my-1">
          {renderInline(block.text)}
        </p>
      );
    case "blank":
      return null;
    default:
      return null;
  }
}

// ─── Main component ───────────────────────────────────────────────────────────

export function MarkdownRenderer({ content, className = "" }: Props) {
  const blocks = parseBlocks(content);
  return (
    <div className={`markdown-body ${className}`}>
      {blocks.map((block, idx) => renderBlock(block, idx))}
    </div>
  );
}
