"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Shell } from "@/components/Shell";
import { ToastProvider } from "@/components/ui";
import { SessionProvider } from "@/lib/session";

/** Every screen runs signed in as a demo persona (Brandt by default) against the real API. */
export default function AppLayout({ children }: { children: ReactNode }): ReactNode {
  const t = useTranslations("shell");
  return (
    <SessionProvider
      loading={
        <p role="status" className="body p-8 text-ink-muted">
          {t("signingIn")}
        </p>
      }
      failed={
        <p role="alert" className="body p-8">
          {t("apiDown")}
        </p>
      }
    >
      <ToastProvider>
        <Shell>{children}</Shell>
      </ToastProvider>
    </SessionProvider>
  );
}
