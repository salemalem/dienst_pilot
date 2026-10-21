"use client";

import { Moon, Sun } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState, type ReactNode } from "react";

import { Button, ICON } from "./ui";

const KEY = "dp-theme";

/** Inline in <head>: sets the theme before first paint (no flash). Stored choice, else the OS setting. */
export const THEME_SCRIPT = `try{var s=localStorage.getItem("${KEY}");var d=s?s==="dark":matchMedia("(prefers-color-scheme: dark)").matches;document.documentElement.classList.toggle("dp-dark",d)}catch(e){}`;

/** Light and dark are both first-class; the choice is kept in this browser. */
export function ThemeSwitch(): ReactNode {
  const t = useTranslations("theme");
  const [dark, setDark] = useState(false);
  useEffect(() => {
    setDark(document.documentElement.classList.contains("dp-dark"));
  }, []);
  return (
    <Button
      variant="secondary"
      aria-pressed={dark}
      aria-label={dark ? t("toLight") : t("toDark")}
      title={dark ? t("toLight") : t("toDark")}
      className="dp-iconbtn"
      icon={dark ? <Sun {...ICON} /> : <Moon {...ICON} />}
      onClick={() => {
        const next = !dark;
        document.documentElement.classList.toggle("dp-dark", next);
        try {
          localStorage.setItem(KEY, next ? "dark" : "light");
        } catch {
          // Storage blocked: the choice lasts for this page view.
        }
        setDark(next);
      }}
    />
  );
}
