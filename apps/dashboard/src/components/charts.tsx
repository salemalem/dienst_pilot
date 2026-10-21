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

export interface CoverageDay {
  date: string;
  short: number;
  expected: number;
  low: number;
  high: number;
  weekday: string;
  label: string;
  weekend: boolean;
  today: boolean;
  expectedText: string;
}

/**
 * Expected absences per day as a dotted band (the forecast's range) with a dot (its value):
 * dashed means "estimate, not a plan". Always paired with a table of the same numbers.
 */
export function CoverageChart({
  days,
  label,
  todayLabel,
  axisLabel,
}: {
  days: CoverageDay[];
  label: string;
  todayLabel: string;
  axisLabel: string;
}): ReactNode {
  const colW = 56;
  const left = 92;
  const top = 12;
  const plot = 118;
  const W = left + days.length * colW + 8;
  const yMax = Math.max(6, Math.ceil(Math.max(0, ...days.map((d) => d.high))));
  const y = (v: number): number => top + plot - (v / yMax) * plot;
  const ticks = [0, Math.round(yMax / 2), yMax];
  return (
    <svg
      viewBox={`0 0 ${String(W)} ${String(top + plot + 74)}`}
      role="img"
      aria-label={label}
      className="h-auto w-full min-w-[760px]"
    >
      {days.map((d, i) => (
        <g key={d.date} transform={`translate(${String(left + i * colW)} 0)`}>
          <rect
            width={colW}
            height={plot + top + 62}
            fill={d.today ? "var(--action-wash)" : d.weekend ? "var(--sheet-sunk)" : "transparent"}
          />
          <line x1={0} x2={0} y1={0} y2={plot + top + 62} stroke="var(--rule)" />
          <rect
            x={colW / 2 - 11}
            y={y(d.high)}
            width={22}
            height={Math.max(4, y(d.low) - y(d.high))}
            fill="var(--pencil-wash)"
            stroke="var(--pencil)"
            strokeDasharray="3 2"
            strokeWidth={1.5}
          />
          <circle cx={colW / 2} cy={y(d.expected)} r={4} fill="var(--ink)" />
          <text
            x={colW / 2}
            y={top + plot + 20}
            textAnchor="middle"
            fontSize={13}
            fill={d.today ? "var(--action)" : "var(--ink-muted)"}
          >
            {d.weekday}
          </text>
          <text
            x={colW / 2}
            y={top + plot + 36}
            textAnchor="middle"
            fontSize={13}
            fontWeight={650}
            fill={d.today ? "var(--action)" : "var(--ink)"}
            className="num-small"
          >
            {d.label}
          </text>
          <text
            x={colW / 2}
            y={top + plot + 52}
            textAnchor="middle"
            fontSize={12}
            fontStyle="italic"
            fill="var(--ink-muted)"
            className="num-small"
          >
            {d.expectedText}
          </text>
          {d.today ? (
            <text
              x={colW / 2}
              y={top + plot + 68}
              textAnchor="middle"
              fontSize={12}
              fill="var(--ink)"
            >
              {todayLabel}
            </text>
          ) : null}
        </g>
      ))}
      <line
        x1={left}
        x2={left + days.length * colW}
        y1={top + plot}
        y2={top + plot}
        stroke="var(--rule-strong)"
      />
      {ticks.map((tick) => (
        <g key={tick}>
          <line
            x1={left}
            x2={left + days.length * colW}
            y1={y(tick)}
            y2={y(tick)}
            stroke="var(--rule)"
            strokeDasharray={tick === 0 ? undefined : "2 4"}
          />
          <text
            x={left - 8}
            y={y(tick) + 4}
            textAnchor="end"
            fontSize={12}
            fill="var(--ink-muted)"
            className="num-small"
          >
            {tick === yMax ? `${String(tick)} ${axisLabel}` : String(tick)}
          </text>
        </g>
      ))}
    </svg>
  );
}
