import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation } from "@apollo/client/react";
import { useSafeQuery } from "features/common-ui/api/useSafeQuery";
import Button from "features/common-ui/Button";
import {
  CONTINUE_IDEA_QUALIFICATION,
  CREATE_IDEA,
  GET_IDEA_QUALIFICATION_SESSION,
  START_IDEA_QUALIFICATION,
} from "features/core/apollo/queries";

type Role = "assistant" | "user" | string;

interface TranscriptItem {
  role: Role;
  content: string;
  ts?: string | null;
}

interface QualificationSession {
  id: string;
  status: "in_progress" | "complete" | "abandoned" | string;
  initialIdeaText: string;
  nextQuestion: string | null;
  turnCount: number;
  qualificationScore: number | null;
  qualificationExplanation: string | null;
  transcript: TranscriptItem[];
}

const IdeaQualificationPage: React.FC = () => {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const sessionId = params.get("session");

  const [seedText, setSeedText] = useState("");
  const [reply, setReply] = useState("");
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  const { data, loading: loadingSession, refetch } = useSafeQuery(
    GET_IDEA_QUALIFICATION_SESSION,
    { variables: { sessionId }, skip: !sessionId, fetchPolicy: "cache-and-network" },
  );

  const [startSession, { loading: starting, error: startError }] = useMutation(
    START_IDEA_QUALIFICATION,
  );
  const [continueSession, { loading: continuing, error: continueError }] =
    useMutation(CONTINUE_IDEA_QUALIFICATION);
  const [createIdea, { loading: creatingIdea }] = useMutation(CREATE_IDEA);

  const session: QualificationSession | undefined =
    (data as { ideaQualificationSession?: QualificationSession } | undefined)
      ?.ideaQualificationSession;

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.transcript?.length, session?.status]);

  const onStart = async () => {
    const text = seedText.trim();
    if (!text) return;
    const result = await startSession({ variables: { initialIdeaText: text } });
    const newId = (
      result.data as { startIdeaQualification?: QualificationSession } | undefined
    )?.startIdeaQualification?.id;
    if (newId) {
      setParams({ session: newId });
      setSeedText("");
    }
  };

  const onReply = async () => {
    if (!sessionId) return;
    const text = reply.trim();
    if (!text) return;
    setReply("");
    await continueSession({
      variables: { sessionId, userMessage: text },
    });
    await refetch();
  };

  const onConvertToIdea = async () => {
    if (!session) return;
    const title =
      session.initialIdeaText.length > 60
        ? session.initialIdeaText.slice(0, 57) + "..."
        : session.initialIdeaText;
    const result = await createIdea({
      variables: { title, description: session.initialIdeaText },
    });
    const ideaId = (
      result.data as { createIdea?: { ideaId?: string } } | undefined
    )?.createIdea?.ideaId;
    if (ideaId) {
      navigate(`/ideas/${ideaId}`);
    } else {
      navigate("/ideas");
    }
  };

  const onAbandon = () => {
    setParams({});
  };

  const errorMessage =
    (startError && startError.message) ||
    (continueError && continueError.message) ||
    null;

  if (!sessionId) {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-6 sm:px-5">
        <header className="flex flex-col gap-2">
          <h1 className="manifest-page-title">
            Let's qualify your idea
          </h1>
          <p className="text-sm leading-relaxed text-neutral600 dark:text-gray300">
            Tell me what you're trying to build. I'll ask a few questions to
            understand whether the idea — and you — are ready to start
            generating a business model.
          </p>
        </header>
        <textarea
          value={seedText}
          onChange={(e) => setSeedText(e.target.value)}
          placeholder="Describe your idea in a sentence or two…"
          rows={5}
          className="w-full resize-none rounded-2xl border border-stone200 bg-white/90 px-4 py-3 text-sm leading-relaxed text-neutral900 shadow-none focus:border-accent-300 focus:outline-none focus:ring-2 focus:ring-accent-200 dark:border-neutral700 dark:bg-neutral900/85 dark:text-white"
        />
        <div className="flex items-center justify-end gap-3">
          <Button
            type="button"
            variant="primary"
            disabled={starting || !seedText.trim()}
            onClick={onStart}
          >
            {starting ? "Starting…" : "Start qualification"}
          </Button>
        </div>
        {errorMessage ? (
          <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
        ) : null}
      </section>
    );
  }

  if (loadingSession && !session) {
    return (
      <section className="mx-auto w-full max-w-2xl px-4 py-6 sm:px-5 text-sm text-neutral600 dark:text-gray300">
        Loading session…
      </section>
    );
  }

  if (!session) {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-4 py-6 sm:px-5">
        <p className="text-sm text-neutral600 dark:text-gray300">
          Session not found.
        </p>
        <div>
          <Button variant="secondary" onClick={onAbandon}>
            Start a new session
          </Button>
        </div>
      </section>
    );
  }

  const isComplete = session.status === "complete";

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-4 py-8">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight text-neutral900 dark:text-white">
          Qualification — turn {session.turnCount}
        </h1>
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            isComplete
              ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
              : "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
          }`}
        >
          {isComplete ? "Complete" : "In progress"}
        </span>
      </header>

      <div className="flex flex-col gap-3 rounded-3xl border border-stone200 bg-white/70 p-4 shadow-none dark:border-neutral700 dark:bg-neutral900/70">
        {session.transcript.map((item, idx) => (
          <TranscriptBubble key={`${item.role}-${idx}`} item={item} />
        ))}
        <div ref={transcriptEndRef} />
      </div>

      {isComplete ? (
        <CompletionPanel
          score={session.qualificationScore}
          explanation={session.qualificationExplanation}
          onConvert={onConvertToIdea}
          converting={creatingIdea}
        />
      ) : (
        <div className="flex flex-col gap-3">
          <textarea
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                onReply();
              }
            }}
            placeholder="Type your reply… (⌘+Enter to send)"
            rows={3}
            disabled={continuing}
            className="w-full resize-none rounded-2xl border border-stone200 bg-white/90 px-4 py-3 text-sm leading-relaxed text-neutral900 shadow-none focus:border-accent-300 focus:outline-none focus:ring-2 focus:ring-accent-200 disabled:opacity-50 dark:border-neutral700 dark:bg-neutral900/85 dark:text-white"
          />
          <div className="flex items-center justify-between gap-3">
            <Button variant="ghost" onClick={onAbandon} disabled={continuing}>
              Start over
            </Button>
            <Button
              variant="primary"
              onClick={onReply}
              disabled={continuing || !reply.trim()}
            >
              {continuing ? "Thinking…" : "Send"}
            </Button>
          </div>
        </div>
      )}

      {errorMessage ? (
        <p className="text-sm text-red-600 dark:text-red-400">{errorMessage}</p>
      ) : null}
    </section>
  );
};

const TranscriptBubble: React.FC<{ item: TranscriptItem }> = ({ item }) => {
  const isUser = item.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? "bg-blue500 text-white"
            : "border border-stone200 bg-white text-neutral900 dark:border-neutral700 dark:bg-neutral800 dark:text-white"
        }`}
      >
        {item.content}
      </div>
    </div>
  );
};

const CompletionPanel: React.FC<{
  score: number | null;
  explanation: string | null;
  onConvert: () => void;
  converting: boolean;
}> = ({ score, explanation, onConvert, converting }) => {
  const band = useMemo(() => {
    if (score === null || score === undefined) return "Unscored";
    if (score >= 80) return "Strong";
    if (score >= 60) return "Promising";
    if (score >= 40) return "Significant gaps";
    return "Not yet ready";
  }, [score]);

  return (
    <div className="flex flex-col gap-4 rounded-3xl border border-stone200 bg-white/90 p-5 shadow-none dark:border-neutral700 dark:bg-neutral900/85">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <p className="text-xs font-semibold normal-case text-gray500 dark:text-gray400">
            Qualification score
          </p>
          <p className="mt-1 text-3xl font-semibold text-neutral900 dark:text-white">
            {score ?? "—"}
            <span className="ml-2 text-sm font-medium text-gray500 dark:text-gray400">
              / 100
            </span>
          </p>
        </div>
        <span className="rounded-full bg-stone100 px-3 py-1 text-xs font-semibold text-neutral700 dark:bg-neutral800 dark:text-gray200">
          {band}
        </span>
      </div>
      {explanation ? (
        <p className="text-sm leading-relaxed text-neutral700 dark:text-gray200">
          {explanation}
        </p>
      ) : null}
      <div className="flex items-center justify-end gap-3">
        <Button variant="primary" onClick={onConvert} disabled={converting}>
          {converting ? "Creating…" : "Convert to an idea"}
        </Button>
      </div>
    </div>
  );
};

export default IdeaQualificationPage;
