"use client";

import {
  CalendarClock,
  CalendarDays,
  Columns3,
  Cpu,
  Eye,
  Inbox,
  LayoutDashboard,
  PanelRight,
  Scale,
  ScrollText,
  Settings,
  UserX,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState, type ReactNode } from "react";

import { EnvBadge } from "@/components/EnvBadge";
import { CopilotPanel } from "@/components/CopilotPanel";
import { LocaleSwitch } from "@/components/LocaleSwitch";
import { ThemeSwitch } from "@/components/ThemeSwitch";
import { Button, ICON } from "@/components/ui";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { useFmt } from "@/lib/fmt";
import { useQuery } from "@/lib/hooks";
import { allowed, homeFor, NAV, type NavId } from "@/lib/nav";
import { PERSONAS, useSession } from "@/lib/session";
import { unwrap } from "@dienstpilot/api-client";

const ICONS: Record<NavId, LucideIcon> = {
  w1: LayoutDashboard,
  w2: CalendarClock,
  w3: Columns3,
  w4: CalendarDays,
  w6: Inbox,
  w7: UserX,
  w8: Scale,
  w10: ScrollText,
  w12: Eye,
  w11: Settings,
  w13: Cpu,
};

const GROUPS = ["planning", "operation", "review", "admin"] as const;

function Clock(): ReactNode {
  const t = useTranslations("shell");
  const fmt = useFmt();
  const clock = useQuery((api) => unwrap(api.GET("/clock")), []);
  if (!clock.data) return null;
  const d = new Date(clock.data.now);
  return (
    <span className="num-small text-ink-muted" title={t("clockTitle")}>
      {fmt.weekday(clock.data.now.slice(0, 10))} {fmt.date(d)}, {fmt.time(d)}
    </span>
  );
}

function PersonaSelect(): ReactNode {
  const t = useTranslations("persona");
  const { persona, switchPersona, me } = useSession();
  const router = useRouter();
  return (
    <label className="flex items-center gap-2">
      <span className="label text-ink-muted">{t("label")}</span>
      <select
        className="dp-input label !h-8 !w-auto"
        value={persona}
        onChange={(e) => {
          const next = PERSONAS.find((p) => p === e.target.value);
          if (!next) return;
          void switchPersona(next).then(() => {
            router.push(
              homeFor(next === "vogel" ? "oversight" : next === "it-admin" ? "admin" : "planner"),
            );
          });
        }}
        data-role={me.role}
      >
        {PERSONAS.map((p) => (
          <option key={p} value={p}>
            {t(p)}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Left navigation, top bar and the collapsible copilot panel (C8) around every screen. */
export function Shell({ children }: { children: ReactNode }): ReactNode {
  const t = useTranslations();
  const { me } = useSession();
  const pathname = usePathname();
  const [copilot, setCopilot] = useState(false);
  const isPlanner = me.role === "planner";
  const overview = useQuery(
    (api) => (isPlanner ? unwrap(api.GET("/planner/overview")) : Promise.resolve(null)),
    [isPlanner, pathname],
  );
  const fmt = useFmt();
  const counts: Partial<Record<NavId, number>> = {
    w6:
      (overview.data?.pending_leave ?? 0) +
      (overview.data?.escalations ?? 0) +
      (overview.data?.open_proposals ?? 0),
  };
  const planning = overview.data?.planning_month ?? null;

  useEffect(() => {
    document.querySelector<HTMLElement>("[data-page-title]")?.focus({ preventScroll: true });
  }, [pathname]);

  const items = NAV.filter((n) => n.roles.includes(me.role));
  const permitted = allowed(pathname, me.role);

  return (
    <div
      className="flex min-h-screen flex-col"
      data-copilot={copilot ? "open" : "closed"}
      data-role={me.role}
    >
      <a
        href="#main"
        className="label absolute left-2 top-2 z-50 -translate-y-16 rounded-control bg-ink px-3 py-2 text-on-ink focus:translate-y-0"
      >
        {t("shell.skip")}
      </a>
      <header className="flex min-h-14 flex-wrap items-center gap-x-4 gap-y-2 border-b border-rule bg-sheet px-6 py-2">
        <span className="title">{t("app.name")}</span>
        <span className="label text-ink-muted">{t("app.department")}</span>
        <span className="flex-1" />
        <Clock />
        <EnvBadge />
        <PersonaSelect />
        <LocaleSwitch />
        <ThemeSwitch />
        {isPlanner ? (
          <Button
            variant="secondary"
            aria-expanded={copilot}
            aria-controls="copilot"
            icon={<PanelRight {...ICON} />}
            onClick={() => {
              setCopilot((v) => !v);
            }}
          >
            {t("w9.toggle")}
          </Button>
        ) : null}
      </header>
      <div className="flex min-h-0 flex-1">
        <nav
          aria-label={t("shell.nav")}
          className="shell-nav flex w-[232px] flex-none flex-col gap-0.5 border-r border-rule bg-paper px-2 py-4"
        >
          {GROUPS.map((g) => {
            const group = items.filter((i) => i.group === g);
            if (group.length === 0) return null;
            return (
              <div key={g} className="flex flex-col gap-0.5">
                <span className="caption nav-label px-3 pb-1 pt-4 text-ink-muted">
                  {g === "planning" && planning
                    ? t("nav.group.planningMonth", { month: fmt.month(planning) })
                    : t(`nav.group.${g}`)}
                </span>
                {group.map((i) => {
                  const Icon = ICONS[i.id];
                  const active = i.href === "/" ? pathname === "/" : pathname.startsWith(i.href);
                  const count = counts[i.id];
                  return (
                    <Link
                      key={i.id}
                      href={i.href}
                      aria-current={active ? "page" : undefined}
                      aria-label={t(`nav.${i.id}`)}
                      title={t(`nav.${i.id}`)}
                      className={`label flex h-10 items-center gap-3 rounded-control px-3 no-underline ${
                        active ? "bg-action-wash text-action" : "text-ink hover:bg-sheet-sunk"
                      }`}
                    >
                      <Icon size={20} strokeWidth={1.75} absoluteStrokeWidth aria-hidden />
                      <span className="nav-label flex-1">{t(`nav.${i.id}`)}</span>
                      {count ? (
                        <span className="num-small nav-label text-ink-muted">{count}</span>
                      ) : null}
                    </Link>
                  );
                })}
              </div>
            );
          })}
        </nav>
        <main id="main" className="flex min-w-0 flex-1 flex-col gap-6 px-8 py-6">
          {permitted ? (
            children
          ) : (
            <div className="flex flex-col gap-3">
              <h1 className="display m-0" tabIndex={-1} data-page-title>
                {t("shell.noAccessTitle")}
              </h1>
              <p className="body m-0">{t("shell.noAccessFix")}</p>
              <Link href={homeFor(me.role)} className="label text-action underline">
                {t("shell.toHome")}
              </Link>
            </div>
          )}
        </main>
        {isPlanner && copilot ? (
          <CopilotPanel
            onClose={() => {
              setCopilot(false);
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
