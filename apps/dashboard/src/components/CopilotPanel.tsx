"use client";

import { unwrap, type components } from "@dienstpilot/api-client";
import { BookOpenText, PencilLine, SendHorizontal, Sparkles, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useId, useState, type ReactNode } from "react";

import { EngineBadge } from "@/components/EngineBadge";
import { Button, ICON, useToast } from "@/components/ui";
import { useAction } from "@/lib/hooks";
import { useSession } from "@/lib/session";

type AskOut = components["schemas"]["AskOut"];

interface Turn {
  question: string;
  proposed: boolean;
  /** Set while the agent works; the answer arrives by polling. */
  pending: boolean;
  out: AskOut | null;
}

const POLL_MS = 1000;
const POLL_TRIES = 120;
const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

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
    setText("");
    const index = turns.length;
    const update = (patch: Partial<Turn>): void => {
      setTurns((prev) => prev.map((x, i) => (i === index ? { ...x, ...patch } : x)));
    };
    setTurns((prev) => [...prev, { question, proposed: false, pending: true, out: null }]);
    try {
      let out = await unwrap(api.POST("/copilot/ask", { body: { question, language: locale } }));
      for (let n = 0; out.status === "running" && out.run_id && n < POLL_TRIES; n++) {
        await sleep(POLL_MS);
        out = await unwrap(
          api.GET("/copilot/runs/{run_id}", { params: { path: { run_id: out.run_id } } }),
        );
      }
      update({ pending: false, out });
    } catch (e) {
      setTurns((prev) => prev.filter((_, i) => i !== index));
      throw e;
    }
  });
  const propose = useAction(async (index: number) => {
    const turn = turns[index];
    if (!turn?.out) return;
    await unwrap(
      api.POST("/copilot/proposals", {
        body: { title: turn.question.slice(0, 120), body: turn.out.answer, kind: "change" },
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
          <>
            {(["sample", "sampleWhatIf", "sampleDraft"] as const).map((key) => (
              <Button
                key={key}
                variant="pencil"
                onClick={() => void ask.run(t(key))}
                disabled={ask.pending}
                className="!h-auto !whitespace-normal py-2 text-left"
              >
                {t(key)}
              </Button>
            ))}
          </>
        ) : null}
        {turns.map((turn, i) => (
          <div key={`${turn.question}-${String(i)}`} className="flex flex-col gap-2">
            <p className="body-strong m-0">{turn.question}</p>
            {turn.pending || !turn.out ? (
              <p className="caption m-0 text-ink-muted" role="status">
                {t("working")}
              </p>
            ) : (
              <Answer
                out={turn.out}
                proposed={turn.proposed}
                busy={propose.pending}
                onPropose={() => void propose.run(i)}
              />
            )}
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

/** One answer: who wrote it, what it rests on, what the validator said, and the one action. */
function Answer({
  out,
  proposed,
  busy,
  onPropose,
}: {
  out: AskOut;
  proposed: boolean;
  busy: boolean;
  onPropose: () => void;
}): ReactNode {
  const t = useTranslations("w9");
  const ai = useTranslations("ai");
  const rules = useTranslations("rules");
  const tag = (code: string): string =>
    rules.has(code as "coverage") ? rules(code as "coverage") : code;
  const sources = out.sources ?? [];
  const citations = out.citations ?? [];
  if (out.status === "failed")
    return (
      <p role="alert" className="body m-0 text-alert">
        {t("runFailed")}
      </p>
    );
  return (
    <div className="dp-sugg" data-ai={out.ai_generated ? "true" : "false"}>
      <span className="dp-sugg-tag label">
        <PencilLine {...ICON} />
        {t("answer")}
        <EngineBadge engine={out.engine} />
        {out.ai_generated ? (
          <span className="caption inline-flex items-center gap-1 whitespace-nowrap rounded-mark border border-rule-strong px-2 py-0.5 text-ink-muted">
            <Sparkles {...ICON} size={12} />
            {out.replayed ? ai("recorded") : ai("generated")}
          </span>
        ) : null}
      </span>
      {out.fallback ? (
        <p className="caption m-0 text-pencil" role="note" data-testid="copilot-fallback">
          {t("fallbackNote")}
        </p>
      ) : null}
      <p className="dp-sugg-body body" data-testid="copilot-answer">
        {out.answer}
      </p>
      {out.what_if && !out.fallback ? (
        <div className="body m-0 flex flex-col gap-1" data-testid="copilot-whatif">
          <span className="label">
            {t("whatIfTitle")} {out.what_if.validator_version ?? ""}
          </span>
          <span>{out.what_if.valid ? t("whatIfValid") : t("whatIfInvalid")}</span>
          {out.what_if.violations.length > 0 ? (
            <ul className="caption m-0 flex list-none flex-col gap-1 p-0 text-ink-muted">
              {out.what_if.violations.map((v, i) => (
                <li key={`${v.rule}-${v.date}-${String(i)}`}>
                  {tag(v.rule)} · {v.date}
                  {v.person ? ` · ${v.person}` : ""}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {sources.length > 0 ? (
        <details className="caption text-ink-muted" data-testid="copilot-sources">
          <summary>
            {t("sources")} ({String(sources.length)})
          </summary>
          <ul className="m-0 flex list-none flex-col gap-1 p-0 pt-1">
            {sources.map((s, i) => (
              <li key={`${s.tool}-${String(i)}`}>
                {s.label}
                {Object.keys(s.args).length > 0 ? ` (${Object.values(s.args).join(", ")})` : ""}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {citations.length > 0 ? (
        <ul className="caption m-0 flex list-none flex-col gap-1 p-0">
          {citations.map((c) => (
            <li key={c} className="flex items-center gap-1 text-ink-muted">
              <BookOpenText {...ICON} size={14} />
              <span>
                {t("source")}: {c}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {out.note ? <p className="caption m-0 text-ink-muted">{out.note}</p> : null}
      {out.understood && !out.fallback ? (
        <div className="dp-sugg-actions">
          <Button
            variant="secondary"
            disabled={proposed || busy}
            onClick={onPropose}
            icon={<PencilLine {...ICON} />}
          >
            {proposed ? t("proposed") : t("createProposal")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
