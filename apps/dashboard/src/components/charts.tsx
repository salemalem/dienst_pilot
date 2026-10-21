"use client";

import type { ReactNode } from "react";

/** A one-line distribution: each person is a dot, the median a tick. `label` is the text alternative. */
export function DotStrip({
  values,
  min,
  max,
  median,
  mean,
  label,
}: {
  values: number[];
  min: number;
  max: number;
  median: number;
  mean: number;
  label: string;
}): ReactNode {
  const W = 560;
  const pad = 14;
  const span = Math.max(max - min, 1);
  const x = (v: number): number => pad + ((v - min) / span) * (W - pad * 2);
  const stack = new Map<number, number>();
  return (
    <svg
      viewBox={`0 0 ${String(W)} 74`}
      role="img"
      aria-label={label}
      className="h-auto w-full max-w-[640px]"
    >
      <line x1={pad} x2={W - pad} y1={50} y2={50} stroke="var(--rule-strong)" strokeWidth={1} />
      {values.map((v, i) => {
        const n = stack.get(v) ?? 0;
        stack.set(v, n + 1);
        return (
          <circle
            key={`${String(v)}-${String(i)}`}
            cx={x(v)}
            cy={44 - n * 8}
            r={3.5}
            fill="var(--ink)"
            fillOpacity={0.8}
          />
        );
      })}
      <line
        x1={x(median)}
        x2={x(median)}
        y1={46}
        y2={58}
        stroke="var(--action)"
        strokeWidth={2.5}
      />
      <line
        x1={x(mean)}
        x2={x(mean)}
        y1={46}
        y2={54}
        stroke="var(--ink-muted)"
        strokeWidth={1.5}
        strokeDasharray="2 2"
      />
      <text x={pad} y={70} fontSize={12} fill="var(--ink-muted)" className="num-small">
        {min}
      </text>
      <text
        x={W - pad}
        y={70}
        fontSize={12}
        fill="var(--ink-muted)"
        textAnchor="end"
        className="num-small"
      >
        {max}
      </text>
    </svg>
  );
}

/** A small bar chart (overtime per month). Always paired with a table with the same numbers. */
export function Bars({
  items,
  label,
}: {
  items: { key: string; label: string; value: number; text: string }[];
  label: string;
}): ReactNode {
  const H = 120;
  const barW = 36;
  const gap = 14;
  const max = Math.max(1, ...items.map((i) => i.value));
  const W = items.length * (barW + gap) + gap;
  return (
    <svg
      viewBox={`0 0 ${String(W)} ${String(H + 40)}`}
      role="img"
      aria-label={label}
      className="h-auto w-full max-w-[720px]"
    >
      <line x1={0} x2={W} y1={H} y2={H} stroke="var(--rule-strong)" />
      {items.map((it, i) => {
        const h = (it.value / max) * (H - 16);
        const x = gap + i * (barW + gap);
        return (
          <g key={it.key}>
            <rect x={x} y={H - h} width={barW} height={h} fill="var(--ink)" fillOpacity={0.75} />
            <text
              x={x + barW / 2}
              y={H - h - 4}
              fontSize={11}
              textAnchor="middle"
              fill="var(--ink)"
              className="num-small"
            >
              {it.text}
            </text>
            <text
              x={x + barW / 2}
              y={H + 16}
              fontSize={11}
              textAnchor="middle"
              fill="var(--ink-muted)"
            >
              {it.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
