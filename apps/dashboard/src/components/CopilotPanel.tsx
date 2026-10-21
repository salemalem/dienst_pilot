"use client";

import { unwrap } from "@dienstpilot/api-client";
import { BookOpenText, PencilLine, SendHorizontal, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useId, useState, type ReactNode } from "react";

import { EngineBadge, type EngineLabel } from "@/components/EngineBadge";
import { Button, ICON, useToast } from "@/components/ui";
import { useAction } from "@/lib/hooks";
import { useSession } from "@/lib/session";

interface Turn {
  question: string;
  answer: string;
  citations: string[];
  understood: boolean;
  engine: EngineLabel;
  proposed: boolean;
}

/** W9: the copilot (C8). It explains and cites; it can only create a proposal, never publish. */
export function CopilotPanel({ onClose }: { onClose: () => void }): ReactNode {
  const t = useTranslations("w9");
  const locale = useLocale() as "de" | "en";
  const { api } = useSession();
  const toast = useToast();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const inputId = useId();

  const ask = useAction(async (question: string) => {
    const a = await unwrap(api.POST("/copilot/ask", { body: { question, language: locale } }));
    setTurns((prev) => [...prev, { question, ...a, proposed: false }]);
    setText("");
  });
  const propose = useAction(async (index: number) => {
    const turn = turns[index];
    if (!turn) return;
    await unwrap(
      api.POST("/copilot/proposals", {
        body: { title: turn.question.slice(0, 120), body: turn.answer },
      }),
    );
    setTurns((prev) => prev.map((x, i) => (i === index ? { ...x, proposed: true } : x)));
    toast.show(t("proposalCreated"));
  });

  return (
    <aside
      id="copilot"
      aria-label={t("title")}
      className="flex w-[360px] flex-none flex-col gap-3 border-l border-rule bg-sheet p-4"
    >
      <div className="flex items-center gap-2">
        <h2 className="heading m-0 flex-1">{t("title")}</h2>
        <Button
          variant="quiet"
          className="dp-iconbtn"
          aria-label={t("close")}
          onClick={onClose}
          icon={<X {...ICON} />}
        />
      </div>
      <p className="caption m-0 text-ink-muted">{t("note")}</p>
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto" aria-live="polite">
        {turns.length === 0 ? (
          <Button
            variant="pencil"
            onClick={() => void ask.run(t("sample"))}
            disabled={ask.pending}
            className="!h-auto !whitespace-normal py-2 text-left"
          >
            {t("sample")}
          </Button>
        ) : null}
        {turns.map((turn, i) => (
          <div key={`${turn.question}-${String(i)}`} className="flex flex-col gap-2">
            <p className="body-strong m-0">{turn.question}</p>
            <div className="dp-sugg">
              <span className="dp-sugg-tag label">
                <PencilLine {...ICON} />
                {t("answer")}
                <EngineBadge engine={turn.engine} />
              </span>
              <p className="dp-sugg-body body">{turn.answer}</p>
              {turn.citations.length > 0 ? (
                <ul className="caption m-0 flex list-none flex-col gap-1 p-0">
                  {turn.citations.map((c) => (
                    <li key={c} className="flex items-center gap-1 text-ink-muted">
                      <BookOpenText {...ICON} size={14} />
                      <span>
                        {t("source")}: {c}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
              {turn.understood ? (
                <div className="dp-sugg-actions">
                  <Button
                    variant="secondary"
                    disabled={turn.proposed || propose.pending}
                    onClick={() => void propose.run(i)}
                    icon={<PencilLine {...ICON} />}
                  >
                    {turn.proposed ? t("proposed") : t("createProposal")}
                  </Button>
                </div>
              ) : null}
            </div>
          </div>
        ))}
        {ask.error ? (
          <p role="alert" className="body m-0 text-alert">
            {t("askFailed")}
          </p>
        ) : null}
      </div>
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) void ask.run(text.trim());
        }}
      >
        <div className="dp-field flex-1">
          <label htmlFor={inputId} className="label">
            {t("question")}
          </label>
          <input
            id={inputId}
            className="dp-input"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
            }}
          />
        </div>
        <Button
          variant="primary"
          type="submit"
          aria-label={t("send")}
          disabled={ask.pending || !text.trim()}
          icon={<SendHorizontal {...ICON} />}
        />
      </form>
    </aside>
  );
}
