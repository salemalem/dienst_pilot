"use client";

import { unwrap } from "@dienstpilot/api-client";

import { addMonths } from "./fmt";
import { useQuery, type Query } from "./hooks";

export interface Planning {
  /** The month being planned: the open window's month, else the month after the published one. */
  month: string | null;
  /** While the request window is open, runs are trial runs and cannot be published. */
  windowOpen: boolean;
  overview: Query<Awaited<ReturnType<typeof loadOverview>>>;
}

function loadOverview(api: Parameters<Parameters<typeof useQuery>[0]>[0]) {
  return unwrap(api.GET("/planner/overview"));
}

export function usePlanning(): Planning {
  const overview = useQuery(loadOverview, []);
  const o = overview.data;
  const month = o
    ? ((
        o.window?.roster_month ?? (o.published_month ? addMonths(o.published_month, 1) : null)
      )?.slice(0, 7) ?? null)
    : null;
  return { month, windowOpen: Boolean(o?.window), overview };
}
