import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation } from "@apollo/client/react";
import { useNavigate } from "react-router-dom";

import { SUBMIT_SURVEY } from "features/core/apollo/queries";
import { useMessage } from "features/notifications/context/MessageContext";
import { useSurveyAnalytics } from "features/feedback/useSurveyAnalytics";

import SurveyShell from "./SurveyShell";

const OUTPUT_OPTIONS = [
  "Idea description / editor",
  "Pitch deck generation",
  "Product requirements (PRD)",
  "Provisional patent / IP draft",
  "Business model canvas",
  "Similar ideas / comparables",
  "Publishing an idea / pitch reel",
  "Pitch Reels feed",
  "Messaging",
  "Collaboration / sharing",
  "Voice assistant",
  "API / docs",
  "None of these yet",
];

const SESSION_OPTIONS = [
  "First real session",
  "2–5 working sessions",
  "6–15 working sessions",
  "More than 15 sessions",
];

const PRIMARY_TASK_OPTIONS = [
  "Generate or refine documents (deck, PRD, canvas, patent, etc.)",
  "Capture or structure my idea in the editor",
  "Browse Pitch Reels or published ideas",
  "Message someone or collaborate on an idea",
  "Publish or share an idea externally",
  "Mostly exploring — no single goal yet",
];

const MAIN_BENEFIT_OPTIONS = [
  "It gives shape to rough ideas faster",
  "It creates drafts instead of making me start from a blank page",
  "It helps me research markets, comparables, or adjacent ideas",
  "It makes sharing with collaborators or investors easier",
  "It helps me discover ideas, founders, or opportunities",
  "It gives me momentum or confidence to keep moving",
  "I am not getting enough value yet",
];

const PMF_OPTIONS = [
  "Very disappointed",
  "Somewhat disappointed",
  "Not disappointed",
  "I haven't used it enough yet",
];

function outputsImplyReels(outputs: string[] | undefined): boolean {
  const o = outputs || [];
  return o.includes("Pitch Reels feed") || o.includes("Publishing an idea / pitch reel");
}

export type ProductFeedbackAnswers = {
  usage_sessions?: string;
  primary_task?: string;
  progress_score?: number;
  progress_note?: string;
  main_benefit?: string;
  outputs?: string[];
  ai_quality?: number;
  ai_quality_na?: boolean;
  deliverable_score?: number;
  ease_score?: number;
  pmf_disappointment?: string;
  easiest?: string;
  confusing?: string;
  used_reels?: "yes" | "no";
  reels_helpful?: number;
  reels_feedback?: string;
  tried_collab?: "yes" | "no";
  collab_blocker?: string;
  nps?: number;
  top_fix?: string;
};

type StepKey =
  | "welcome"
  | "usage_sessions"
  | "primary_task"
  | "progress"
  | "main_benefit"
  | "outputs"
  | "ai_quality"
  | "deliverable"
  | "ease"
  | "pmf"
  | "ux"
  | "reels"
  | "reels_detail"
  | "collab"
  | "nps"
  | "top_fix";

function buildSteps(a: ProductFeedbackAnswers): StepKey[] {
  const reelsFromUsage = outputsImplyReels(a.outputs);

  const s: StepKey[] = [
    "welcome",
    "usage_sessions",
    "primary_task",
    "progress",
    "main_benefit",
    "outputs",
    "ai_quality",
    "deliverable",
    "ease",
    "pmf",
    "ux",
  ];

  if (reelsFromUsage) {
    s.push("reels_detail");
  } else {
    s.push("reels");
    if (a.used_reels === "yes") {
      s.push("reels_detail");
    }
  }

  s.push("collab", "nps", "top_fix");
  return s;
}

const choiceClass = (selected: boolean) =>
  `w-full rounded-lg border px-4 py-3.5 text-left text-sm font-semibold transition-all [overflow-wrap:anywhere] break-words whitespace-normal sm:px-5 sm:py-4 ${
    selected
      ? "border-accent-500 bg-accent-50 text-accent-900 shadow-none dark:border-accent-400 dark:bg-accent-900/25 dark:text-accent-100"
      : "border-stone200 bg-white text-neutral900 hover:border-stone300 dark:border-neutral700 dark:bg-neutral900 dark:text-white dark:hover:border-neutral600"
  }`;

const ProductFeedbackSurveyPage: React.FC = () => {
  const navigate = useNavigate();
  const { setMessage } = useMessage();
  const { captureSurvey } = useSurveyAnalytics();
  const [answers, setAnswers] = useState<ProductFeedbackAnswers>({ outputs: [] });
  const [stepIndex, setStepIndex] = useState(0);
  const [done, setDone] = useState(false);
  const [submitSurvey, { loading: submitting }] = useMutation(SUBMIT_SURVEY);

  const steps = useMemo(() => buildSteps(answers), [answers]);

  useEffect(() => {
    setStepIndex((i) => Math.min(Math.max(i, 0), Math.max(steps.length - 1, 0)));
  }, [steps.length]);

  const current = steps[stepIndex] ?? "welcome";
  const total = steps.length;

  const patch = useCallback((p: Partial<ProductFeedbackAnswers>) => {
    setAnswers((prev) => ({ ...prev, ...p }));
  }, []);

  const goNext = useCallback(() => {
    setStepIndex((i) => Math.min(i + 1, steps.length - 1));
  }, [steps.length]);

  const goBack = useCallback(() => {
    setStepIndex((i) => Math.max(i - 1, 0));
  }, []);

  const toggleOutput = (label: string) => {
    const cur = new Set(answers.outputs || []);
    if (cur.has(label)) {
      cur.delete(label);
    } else {
      cur.add(label);
    }
    patch({ outputs: Array.from(cur) });
  };

  const handleSubmit = async () => {
    try {
      await submitSurvey({
        variables: {
          input: {
            surveyType: "product_feedback",
            answersJson: JSON.stringify(answers),
            contactEmail: null,
          },
        },
      });
      captureSurvey("survey_completed", { track: "b", surface: "feedback_page" });
      setDone(true);
    } catch (e) {
      console.error(e);
      setMessage("Could not save feedback. Try again or use Account if the problem persists.", "error");
    }
  };

  if (done) {
    return (
      <div className="manifest-page min-h-screen">
        <div className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center px-4 py-12 text-center ps-[max(1rem,env(safe-area-inset-left,0px))] pe-[max(1rem,env(safe-area-inset-right,0px))] pb-[max(2rem,env(safe-area-inset-bottom,0px))] pt-[max(1rem,env(safe-area-inset-top,0px))] sm:px-6 sm:py-16">
          <div className="manifest-panel w-full rounded-lg border border-stone200 px-8 py-12 dark:border-neutral700">
            <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Thank you</p>
            <h1 className="mt-4 text-2xl font-semibold text-neutral900 dark:text-white">Feedback received</h1>
            <p className="mt-4 text-sm leading-7 text-gray500 dark:text-gray400">
              This directly shapes what we ship next. The visitor discovery survey at /research covers different questions — thank you if you
              contributed to both.
            </p>
            <button
              type="button"
              onClick={() => navigate("/ideas")}
              className="mt-8 inline-flex rounded-2xl bg-neutral900 px-8 py-3 text-sm font-semibold text-white dark:bg-white dark:text-neutral900"
            >
              Back to workspace
            </button>
          </div>
        </div>
      </div>
    );
  }

  const nextDisabled = (() => {
    switch (current) {
      case "welcome":
        return false;
      case "usage_sessions":
        return !answers.usage_sessions;
      case "primary_task":
        return !answers.primary_task;
      case "progress":
        return answers.progress_score == null;
      case "main_benefit":
        return !answers.main_benefit;
      case "outputs":
        return !answers.outputs?.length;
      case "ai_quality":
        return !answers.ai_quality_na && answers.ai_quality == null;
      case "deliverable":
        return answers.deliverable_score == null;
      case "ease":
        return answers.ease_score == null;
      case "pmf":
        return !answers.pmf_disappointment;
      case "ux":
        return false;
      case "reels":
        return !answers.used_reels;
      case "reels_detail":
        return answers.reels_helpful == null;
      case "collab":
        return !answers.tried_collab;
      case "nps":
        return answers.nps == null;
      case "top_fix":
        return false;
      default:
        return false;
    }
  })();

  const onPrimary = () => {
    if (current === "top_fix") {
      void handleSubmit();
      return;
    }
    goNext();
  };

  const shell = (props: Omit<React.ComponentProps<typeof SurveyShell>, "stepIndex" | "totalSteps" | "showBack" | "onBack" | "onNext">) => (
    <SurveyShell
      stepIndex={stepIndex}
      totalSteps={total}
      showBack={stepIndex > 0}
      onBack={goBack}
      onNext={onPrimary}
      nextLabel={current === "top_fix" ? "Submit feedback" : "Continue"}
      nextDisabled={nextDisabled}
      isSubmitting={submitting && current === "top_fix"}
      {...props}
    />
  );

  if (current === "welcome") {
    return shell({
      eyebrow: "Product experience",
      title: "Help us improve what you actually use in Manifest",
      description: (
        <>
          <p>
            <strong className="font-semibold text-neutral800 dark:text-gray200">This survey is only about the in-product experience</strong> — quality,
            navigation, specific features, and what to build next. Answers are saved for the product team.
          </p>
          <p>
            It is <strong className="font-semibold text-neutral800 dark:text-gray200">not</strong> the same as the short{" "}
            <strong className="font-semibold text-neutral800 dark:text-gray200">discovery survey</strong> on our marketing site ({` `}
            <span className="whitespace-nowrap font-medium text-accent-600 dark:text-accent-300">/research</span>
            {` `}), which is for visitors we are still learning to serve. If you took both, thank you — they feed different decisions.
          </p>
        </>
      ),
      children: null,
    });
  }

  if (current === "usage_sessions") {
    return shell({
      eyebrow: "Context",
      title: "How much time have you spent in Manifest so far?",
      description: "Rough sessions or visits — your best guess is fine.",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {SESSION_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.usage_sessions === opt)} onClick={() => patch({ usage_sessions: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "primary_task") {
    return shell({
      eyebrow: "Context",
      title: "What were you mainly trying to accomplish in your latest visits?",
      description: "Choose the closest option. This frames the rest of the questions.",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {PRIMARY_TASK_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.primary_task === opt)} onClick={() => patch({ primary_task: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "progress") {
    return shell({
      eyebrow: "Outcomes",
      title: "Has Manifest helped you make progress on an idea or project?",
      description: "1 = not at all, 5 = a great deal. Optional: one line on what changed.",
      children: (
        <div className="space-y-6">
          <div className="flex flex-wrap gap-2">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} type="button" className={choiceClass(answers.progress_score === n)} onClick={() => patch({ progress_score: n })}>
                {n}
              </button>
            ))}
          </div>
          <label className="block text-xs font-semibold uppercase tracking-[0.14em] text-gray500 dark:text-gray400">
            What changed? (optional)
            <input
              type="text"
              value={answers.progress_note || ""}
              onChange={(e) => patch({ progress_note: e.target.value })}
              className="mt-2 w-full rounded-lg border border-stone200 bg-white px-4 py-3 text-sm dark:border-neutral700 dark:bg-neutral900 dark:text-white"
              placeholder="e.g. Finally have a shareable one-pager…"
            />
          </label>
        </div>
      ),
    });
  }

  if (current === "main_benefit") {
    return shell({
      eyebrow: "Value",
      title: "What is the biggest benefit you are getting from Manifest today?",
      description: "Pick the closest answer, even if the benefit is still modest.",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {MAIN_BENEFIT_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.main_benefit === opt)} onClick={() => patch({ main_benefit: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "outputs") {
    return shell({
      eyebrow: "Usage",
      title: "Which parts have you used?",
      description: "Select all that apply.",
      children: (
        <div className="grid max-h-[min(55dvh,24rem)] gap-2 overflow-y-auto overscroll-y-contain pr-1 [-webkit-overflow-scrolling:touch] sm:max-h-[min(50dvh,28rem)] sm:gap-3">
          {OUTPUT_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass((answers.outputs || []).includes(opt))} onClick={() => toggleOutput(opt)}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "ai_quality") {
    return shell({
      eyebrow: "AI outputs",
      title: "How useful were AI-generated documents as a starting point?",
      description: "If you have not generated documents yet, choose N/A. 1 = not useful, 5 = very useful.",
      children: (
        <div className="space-y-4">
          <button
            type="button"
            className={choiceClass(!!answers.ai_quality_na)}
            onClick={() => patch({ ai_quality_na: true, ai_quality: undefined })}
          >
            N/A — I have not generated documents yet
          </button>
          <div className="flex flex-wrap gap-2">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                className={choiceClass(!answers.ai_quality_na && answers.ai_quality === n)}
                onClick={() => patch({ ai_quality: n, ai_quality_na: false })}
              >
                {n}
              </button>
            ))}
          </div>
        </div>
      ),
    });
  }

  if (current === "deliverable") {
    return shell({
      eyebrow: "Outcomes",
      title: "How close did Manifest get to something you would actually share, publish, or act on?",
      description: "1 = nowhere close, 5 = nearly ready with only minor touch-ups.",
      children: (
        <div className="flex flex-wrap gap-2">
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" className={choiceClass(answers.deliverable_score === n)} onClick={() => patch({ deliverable_score: n })}>
              {n}
              <span className="mt-0.5 block text-xs font-normal text-gray500 dark:text-gray400">
                {n === 1 ? "Nowhere close" : n === 5 ? "Nearly ready" : ""}
              </span>
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "ease") {
    return shell({
      eyebrow: "Effort",
      title: "How easy was it to accomplish what you came here to do?",
      description: "Think about your main task from a moment ago. 1 = very difficult, 5 = very easy.",
      children: (
        <div className="flex flex-wrap gap-2">
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" className={choiceClass(answers.ease_score === n)} onClick={() => patch({ ease_score: n })}>
              {n}
              <span className="mt-0.5 block text-xs font-normal text-gray500 dark:text-gray400">
                {n === 1 ? "Very hard" : n === 5 ? "Very easy" : ""}
              </span>
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "pmf") {
    return shell({
      eyebrow: "Retention",
      title: "If you could no longer use Manifest, how would you feel?",
      description: "This is one of the clearest early-stage signals of product pull.",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {PMF_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.pmf_disappointment === opt)} onClick={() => patch({ pmf_disappointment: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "ux") {
    return shell({
      eyebrow: "Usability",
      title: "What felt easiest? What felt most confusing?",
      description: "Optional but helpful — a phrase each is enough.",
      children: (
        <div className="space-y-4">
          <label className="block text-xs font-semibold uppercase tracking-[0.14em] text-gray500 dark:text-gray400">
            Easiest
            <input
              type="text"
              value={answers.easiest || ""}
              onChange={(e) => patch({ easiest: e.target.value })}
              className="mt-2 w-full rounded-lg border border-stone200 bg-white px-4 py-3 text-sm dark:border-neutral700 dark:bg-neutral900 dark:text-white"
            />
          </label>
          <label className="block text-xs font-semibold uppercase tracking-[0.14em] text-gray500 dark:text-gray400">
            Most confusing
            <input
              type="text"
              value={answers.confusing || ""}
              onChange={(e) => patch({ confusing: e.target.value })}
              className="mt-2 w-full rounded-lg border border-stone200 bg-white px-4 py-3 text-sm dark:border-neutral700 dark:bg-neutral900 dark:text-white"
            />
          </label>
        </div>
      ),
    });
  }

  if (current === "reels") {
    return shell({
      eyebrow: "Discovery",
      title: "Aside from what you already selected, have you used Pitch Reels (the immersive feed)?",
      description: "We ask because some people browse reels without publishing.",
      children: (
        <div className="grid gap-3 sm:grid-cols-2">
          <button type="button" className={choiceClass(answers.used_reels === "yes")} onClick={() => patch({ used_reels: "yes" })}>
            Yes
          </button>
          <button type="button" className={choiceClass(answers.used_reels === "no")} onClick={() => patch({ used_reels: "no" })}>
            No
          </button>
        </div>
      ),
    });
  }

  if (current === "reels_detail") {
    const implied = outputsImplyReels(answers.outputs);
    return shell({
      eyebrow: "Discovery",
      title: "Did Pitch Reels help you discover or understand ideas?",
      description: implied
        ? "You said you used reels or publishing — we would love specifics."
        : "Share how the feed landed for you.",
      children: (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                className={choiceClass(answers.reels_helpful === n)}
                onClick={() => patch({ reels_helpful: n })}
              >
                {n}
              </button>
            ))}
          </div>
          <label className="block text-xs font-semibold uppercase tracking-[0.14em] text-gray500 dark:text-gray400">
            What would make the feed more valuable?
            <textarea
              value={answers.reels_feedback || ""}
              onChange={(e) => patch({ reels_feedback: e.target.value })}
              rows={3}
              className="mt-2 w-full resize-none rounded-lg border border-stone200 bg-white px-4 py-3 text-sm dark:border-neutral700 dark:bg-neutral900 dark:text-white"
              placeholder="Optional"
            />
          </label>
        </div>
      ),
    });
  }

  if (current === "collab") {
    return shell({
      eyebrow: "Collaboration",
      title: "Did you try inviting others or messaging about an idea?",
      children: (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <button type="button" className={choiceClass(answers.tried_collab === "yes")} onClick={() => patch({ tried_collab: "yes" })}>
              Yes
            </button>
            <button type="button" className={choiceClass(answers.tried_collab === "no")} onClick={() => patch({ tried_collab: "no" })}>
              No
            </button>
          </div>
          {answers.tried_collab === "no" ? (
            <label className="block text-xs font-semibold uppercase tracking-[0.14em] text-gray500 dark:text-gray400">
              What stopped you? (optional)
              <input
                type="text"
                value={answers.collab_blocker || ""}
                onChange={(e) => patch({ collab_blocker: e.target.value })}
                className="mt-2 w-full rounded-lg border border-stone200 bg-white px-4 py-3 text-sm dark:border-neutral700 dark:bg-neutral900 dark:text-white"
              />
            </label>
          ) : null}
        </div>
      ),
    });
  }

  if (current === "nps") {
    return shell({
      eyebrow: "Recommendation",
      title: "How likely are you to recommend Manifest?",
      description: "0 = not at all, 10 = extremely likely.",
      children: (
        <div className="grid w-full grid-cols-6 gap-2 sm:grid-cols-11">
          {Array.from({ length: 11 }, (_, i) => i).map((n) => (
            <button key={n} type="button" className={`${choiceClass(answers.nps === n)} min-h-[2.75rem] text-center`} onClick={() => patch({ nps: n })}>
              {n}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "top_fix") {
    return shell({
      eyebrow: "Priorities",
      title: "What is the one thing we should build or fix first to help you move an idea forward?",
      children: (
        <textarea
          value={answers.top_fix || ""}
          onChange={(e) => patch({ top_fix: e.target.value })}
          rows={6}
          className="w-full resize-none rounded-lg border border-stone200 bg-white px-4 py-3 text-sm leading-7 text-neutral900 outline-none focus:border-accent-400 dark:border-neutral700 dark:bg-neutral900 dark:text-white"
          placeholder="Be as specific as you like."
        />
      ),
    });
  }

  return null;
};

export default ProductFeedbackSurveyPage;
