"use client";

import ReactMarkdown from "react-markdown";

export function MarkdownView({ children }: { children: string }) {
  return (
    <div className="prose-stage">
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  );
}
