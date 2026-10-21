/** The numbers a solver run reports per variant (`RunOut.variants[].metrics`, untyped in the schema). */
export interface VariantMetrics {
  wishRate: number;
  wishesGranted: number;
  wishesTotal: number;
  importantGranted: number;
  importantTotal: number;
  burdenSpread: number;
  burdenMax: number;
  burdenMin: number;
  overtimeHours: number;
  isolatedNights: number;
  status: string;
}

export function variantMetrics(raw: Record<string, unknown> | null): VariantMetrics | null {
  if (!raw) return null;
  const n = (k: string): number => (typeof raw[k] === "number" ? raw[k] : 0);
  return {
    wishRate: n("wish_rate"),
    wishesGranted: n("wishes_granted"),
    wishesTotal: n("wishes_total"),
    importantGranted: n("important_granted"),
    importantTotal: n("important_total"),
    burdenSpread: n("burden_spread"),
    burdenMax: n("burden_max"),
    burdenMin: n("burden_min"),
    overtimeHours: n("overtime_hours"),
    isolatedNights: n("isolated_nights"),
    status: typeof raw.status === "string" ? raw.status : "",
  };
}
