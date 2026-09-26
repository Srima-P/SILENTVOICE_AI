/**
 * DiffViewer — renders a structured unified diff as a read-only code table.
 *
 * Props:
 *   diff  — list of DiffChunk objects (from ProposeChangeResponse.chunks /
 *            ProposedChange.diff).  Empty array renders "No changes detected."
 *
 * Visual states:
 *   kind === "added"   → green background + "+" prefix
 *   kind === "removed" → red background + "−" prefix
 *   kind === "context" → default surface + " " prefix
 *
 * No external diff library is used.  The structured DiffChunk data is rendered
 * directly — no text parsing required.
 */

import type { DiffChunk } from "@/types";

interface Props {
  diff: DiffChunk[];
}

export function DiffViewer({ diff }: Props) {
  if (diff.length === 0) {
    return (
      <p className="text-xs text-text-muted px-3 py-2 italic">
        No changes detected.
      </p>
    );
  }

  return (
    <div
      className="font-mono text-[11px] overflow-x-auto rounded border border-border bg-surface-2"
      aria-label="Diff preview"
    >
      {diff.map((chunk, chunkIdx) => (
        <div key={chunkIdx}>
          {/* Chunk header — mirrors unified diff @@ line */}
          <div
            className="px-3 py-0.5 text-text-muted bg-surface-3 border-b border-border select-none"
            aria-label={`Hunk @@ -${chunk.old_start},${chunk.old_count} +${chunk.new_start},${chunk.new_count} @@`}
          >
            <span className="text-text-accent/70">@@</span>{" "}
            <span>
              -{chunk.old_start},{chunk.old_count} +{chunk.new_start},{chunk.new_count}
            </span>{" "}
            <span className="text-text-accent/70">@@</span>
          </div>

          {/* Lines */}
          <table className="w-full border-collapse" role="table" aria-label={`Chunk ${chunkIdx + 1}`}>
            <tbody>
              {chunk.lines.map((line, lineIdx) => {
                const isAdded   = line.kind === "added";
                const isRemoved = line.kind === "removed";

                return (
                  <tr
                    key={lineIdx}
                    className={[
                      "leading-5",
                      isAdded   ? "bg-status-ok/10 text-status-ok"      : "",
                      isRemoved ? "bg-status-error/10 text-status-error" : "",
                      !isAdded && !isRemoved ? "text-text-secondary"     : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                  >
                    {/* Old line number */}
                    <td
                      className="w-9 px-1.5 text-right text-text-muted select-none border-r border-border/50 align-top"
                      aria-label={line.line_number_old !== null ? `Original line ${line.line_number_old}` : ""}
                    >
                      {line.line_number_old ?? ""}
                    </td>

                    {/* New line number */}
                    <td
                      className="w-9 px-1.5 text-right text-text-muted select-none border-r border-border/50 align-top"
                      aria-label={line.line_number_new !== null ? `New line ${line.line_number_new}` : ""}
                    >
                      {line.line_number_new ?? ""}
                    </td>

                    {/* Sign prefix */}
                    <td
                      className="w-4 px-1 text-center select-none align-top font-bold"
                      aria-hidden="true"
                    >
                      {isAdded ? "+" : isRemoved ? "−" : " "}
                    </td>

                    {/* Line content */}
                    <td className="px-1 whitespace-pre-wrap break-all align-top">
                      {line.content}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
