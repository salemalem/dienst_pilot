import type { Role } from "./session";

export type NavId = "w1" | "w2" | "w3" | "w4" | "w6" | "w7" | "w8" | "w10" | "w12" | "w11" | "w13";

export interface NavItem {
  id: NavId;
  href: string;
  /** Lucide icon name (the design system's one-icon-per-screen table). */
  roles: Role[];
  group: "planning" | "operation" | "review" | "admin";
}

const PLANNER: Role[] = ["planner"];

/** Screens, their routes and who may open them (API roles: planner, oversight, admin). */
export const NAV: NavItem[] = [
  { id: "w1", href: "/", roles: PLANNER, group: "planning" },
  { id: "w2", href: "/wunschphase", roles: PLANNER, group: "planning" },
  { id: "w3", href: "/varianten", roles: PLANNER, group: "planning" },
  { id: "w4", href: "/dienstplan", roles: PLANNER, group: "planning" },
  { id: "w6", href: "/anfragen", roles: PLANNER, group: "operation" },
  { id: "w7", href: "/ausfaelle", roles: PLANNER, group: "operation" },
  { id: "w8", href: "/fairness", roles: ["planner", "oversight"], group: "review" },
  { id: "w10", href: "/protokoll", roles: ["planner", "oversight"], group: "review" },
  { id: "w12", href: "/aufsicht", roles: ["oversight"], group: "review" },
  { id: "w13", href: "/ki-transparenz", roles: ["planner", "oversight", "admin"], group: "review" },
  { id: "w11", href: "/regeln", roles: ["planner", "admin"], group: "admin" },
];

/** Where a role lands after signing in. */
export function homeFor(role: Role): string {
  return role === "oversight" ? "/aufsicht" : role === "admin" ? "/regeln" : "/";
}

export function allowed(pathname: string, role: Role): boolean {
  const base = pathname.replace(/^\/(de|en)/, "") || "/";
  const item = NAV.find((n) =>
    n.href === "/" ? base === "/" : base === n.href || base.startsWith(`${n.href}/`),
  );
  return item ? item.roles.includes(role) : true;
}
