"use client";

/** Engaging async states: a spinner with rotating, context-aware messages
 * (the Claude-style "visible thinking"), or skeleton placeholders. */
import { useEffect, useState } from "react";

const DEFAULT_MESSAGES = [
  "Ładowanie danych…",
  "Jeszcze chwila…",
];

export function LoadingMessages({
  messages = DEFAULT_MESSAGES,
  intervalMs = 1800,
}: {
  messages?: string[];
  intervalMs?: number;
}) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    const timer = setInterval(
      () => setIndex((current) => (current + 1) % messages.length),
      intervalMs,
    );
    return () => clearInterval(timer);
  }, [messages.length, intervalMs]);

  return (
    <div className="loading-line" role="status" aria-live="polite">
      <span className="loading-dot" />
      <span key={index} className="loading-text">
        {messages[index]}
      </span>
    </div>
  );
}

/** Generic skeleton block; compose into rows/cards via style props. */
export function Skeleton({
  height = 16,
  width = "100%",
  radius = 6,
  style,
}: {
  height?: number;
  width?: number | string;
  radius?: number;
  style?: React.CSSProperties;
}) {
  return (
    <span
      className="skeleton"
      style={{ height, width, borderRadius: radius, ...style }}
      aria-hidden="true"
    />
  );
}

export function SkeletonRows({ rows = 3, height = 42 }: { rows?: number; height?: number }) {
  return (
    <div style={{ display: "grid", gap: 10, margin: "12px 0" }}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} height={height} radius={8} />
      ))}
    </div>
  );
}

export function SkeletonCards({ cards = 6 }: { cards?: number }) {
  return (
    <div className="grid-cards" style={{ margin: "12px 0" }}>
      {Array.from({ length: cards }, (_, i) => (
        <Skeleton key={i} height={64} radius={8} />
      ))}
    </div>
  );
}
