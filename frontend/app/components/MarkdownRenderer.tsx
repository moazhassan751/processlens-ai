"use client";

import React from "react";

interface MarkdownRendererProps {
  content: string;
  className?: string;
  accentColor?: "indigo" | "cyan" | "emerald" | "amber" | "purple";
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  className = "",
  accentColor = "indigo",
}) => {
  if (!content) return null;

  // Split into paragraphs / lines
  const lines = content.split(/\r?\n/);
  const elements: React.ReactNode[] = [];

  let currentList: string[] = [];
  let isNumberedList = false;

  const flushList = (keyPrefix: number) => {
    if (currentList.length === 0) return;
    const items = [...currentList];
    currentList = [];
    const isNum = isNumberedList;
    isNumberedList = false;

    elements.push(
      <ul
        key={`list-${keyPrefix}`}
        className={`my-2 space-y-1.5 pl-1 ${isNum ? "list-decimal list-inside" : ""}`}
      >
        {items.map((item, idx) => (
          <li key={idx} className="flex items-start gap-2 text-xs leading-relaxed text-slate-300">
            {!isNum && (
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-indigo-400 mt-1.5 shrink-0 shadow-sm shadow-indigo-500/50" />
            )}
            <span className="flex-1">{formatInline(item)}</span>
          </li>
        ))}
      </ul>
    );
  };

  const formatInline = (text: string): React.ReactNode => {
    // Regex replace **bold** with <strong>
    const parts = text.split(/(\*\*.*?\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**") && part.length >= 4) {
        const boldText = part.slice(2, -2);
        return (
          <strong key={i} className="font-semibold text-white tracking-wide">
            {boldText}
          </strong>
        );
      }
      return part;
    });
  };

  lines.forEach((rawLine, index) => {
    const line = rawLine.trim();

    // Empty line -> flush list
    if (!line) {
      flushList(index);
      return;
    }

    // Markdown Heading: ### Heading or ## Heading or # Heading
    if (line.startsWith("###") || line.startsWith("##") || line.startsWith("#")) {
      flushList(index);
      const cleanTitle = line.replace(/^#+\s*/, "");
      elements.push(
        <h4
          key={`heading-${index}`}
          className="text-xs font-bold uppercase tracking-wider text-indigo-300 mt-3 mb-1.5 flex items-center gap-2 border-b border-slate-800 pb-1"
        >
          <span className="w-1.5 h-3 bg-indigo-500 rounded-sm inline-block" />
          {formatInline(cleanTitle)}
        </h4>
      );
      return;
    }

    // Section title written as **SECTION TITLE** on its own line
    if (line.startsWith("**") && line.endsWith("**") && !line.includes(":") && line.length < 50) {
      flushList(index);
      const cleanTitle = line.slice(2, -2);
      elements.push(
        <h5
          key={`sec-${index}`}
          className="text-xs font-bold uppercase tracking-wider text-cyan-300 mt-2.5 mb-1 flex items-center gap-1.5"
        >
          <span className="w-1 h-2.5 bg-cyan-500 rounded-sm inline-block" />
          {cleanTitle}
        </h5>
      );
      return;
    }

    // Unordered List item: - item or * item
    if (line.startsWith("- ") || line.startsWith("* ")) {
      currentList.push(line.slice(2));
      return;
    }

    // Numbered List item: 1. item
    const numMatch = line.match(/^(\d+)\.\s+(.*)/);
    if (numMatch) {
      isNumberedList = true;
      currentList.push(numMatch[2]);
      return;
    }

    // Regular line / paragraph
    flushList(index);
    elements.push(
      <p key={`p-${index}`} className="text-xs leading-relaxed text-slate-300 my-1">
        {formatInline(line)}
      </p>
    );
  });

  flushList(lines.length);

  return <div className={`space-y-1 ${className}`}>{elements}</div>;
};
