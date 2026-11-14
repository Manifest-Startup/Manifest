import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useMutation } from "@apollo/client/react";
import { useNavigate } from "react-router-dom";

import { SUBMIT_SURVEY } from "features/core/apollo/queries";
import { useMessage } from "features/notifications/context/MessageContext";
import { useSurveyAnalytics } from "features/feedback/useSurveyAnalytics";

import SurveyShell from "./SurveyShell";

const INVESTOR_ROLES = new Set(["Investor", "Advisor or mentor"]);

const ROLE_OPTIONS = [
  "Founder (building a company)",
  "Aspiring founder",
  "Investor",
  "Advisor or mentor",
  "Student",
  "Other",
];

const STAGE_OPTIONS = ["Idea only / exploring", "Pre-seed", "Seed or later", "Not applicable / prefer not to say"];

const GOAL_OPTIONS = [
  "Validate whether an idea is worth pursuing",
  "Turn an idea into investor- or team-ready artifacts",
  "Compare an idea against the market or similar companies",
  "Find startups to invest in, advise, or follow",
  "Browse discovery / pitch-style content",
  "General curiosity",
  "Other",
];

const TOOL_OPTIONS = [
  "Google Docs / Word",
  "Notion or similar wiki",
  "ChatGPT / other AI chat",
  "Spreadsheets / Airtable",
  "Slides / Canva",
  "Whiteboard / FigJam / Miro",
  "Mostly in my head",
  "Other",
];

const VALUE_PROP_OPTIONS = [
  "AI turns a rough idea into structured startup documents",
  "Market / comparable research that sharpens or validates the idea",
  "Investor- or share-ready outputs without starting from scratch",
  "Collaboration with co-founders or contributors",
  "Discovery, pitch reels, or the startup social layer",
  "One workspace instead of a pile of tools",
  "Not sure yet",
];

const FAMILIARITY_OPTIONS = [
  "Very familiar — I use AI tools regularly for work",
  "Somewhat — I have tried them a few times",
  "Limited — I mostly use traditional docs, slides, or spreadsheets",
  "New — I am exploring what AI can do for startups",
  "Prefer not to say",
];

const INVESTOR_FOCUS_OPTIONS = [
  "Team, narrative, and founder fit",
  "Market size, timing, and dynamics",
  "Traction, metrics, or milestones",
  "Product, demo, or technical proof",
  "Financial model and unit economics",
  "It depends — I do not have a single default",
];

const INVESTOR_DEALFLOW_OPTIONS = [
  "Warm introductions from my network",
  "Events, pitch days, or accelerators",
  "Platforms, databases, or deal-flow tools",
  "Social feeds or short-form content (e.g. pitch-style reels)",
  "Inbound applications or cold outreach",
  "Other / mixed sources",
];

const BETTER_MEANS_OPTIONS = [
  "Speed — from rough idea to credible artifacts faster",
  "Structure — less blank-page friction; clearer sections",
  "Quality — stronger first drafts I can ship or share",
  "Trust — I understand what the AI did and can verify it",
  "Collaboration — easier to loop in co-founders or advisors",
  "Discovery — finding or comparing ideas and founders",
  "Momentum — easier to keep moving instead of stalling out",
  "Consolidation — fewer tools to juggle",
  "Not sure yet",
];

const BIGGEST_BARRIER_OPTIONS = [
  "Knowing whether the idea is actually worth pursuing",
  "Turning rough thinking into a clear story or plan",
  "Doing market research or finding comparable companies",
  "Scoping the product or roadmap",
  "Legal, incorporation, or admin overhead",
  "Finding co-founders, collaborators, or advisors",
  "Getting customer or investor interest",
  "Keeping momentum and following through consistently",
  "Other / mixed blockers",
];

const FIRST_OUTPUT_OPTIONS = [
  "A one-page idea summary I could share",
  "A market / comparable research brief",
  "A business model canvas",
  "A pitch deck",
  "A PRD or product roadmap",
  "Legal starter documents or formation checklist",
  "A financial model or assumptions sheet",
  "A shareable founder page for collaborators or investors",
];

const TRUST_SIGNAL_OPTIONS = [
  "Citations or links behind claims and research",
  "Editable assumptions and calculations",
  "A clear explanation of what AI generated vs. what I provided",
  "Outputs that already look polished enough to share",
  "Proof that real founders or investors use it successfully",
  "A visible history of changes, collaborators, or iteration",
  "Not sure yet",
];

export type ResearchAnswers = {
  role?: string;
  role_other?: string;
  stage?: string;
  goal?: string;
  goal_other?: string;
  familiarity?: string;
  investor_focus?: string;
  investor_dealflow?: string;
  investor_gap?: string;
  tools?: string[];
  tools_other?: string;
  friction?: string;
  biggest_barrier?: string;
  first_output?: string;
  job_success?: string;
  value_prop?: string;
  trust_signal?: string;
  clarity?: string;
  better_means?: string;
  signup_intent?: number;
  wants_call?: "yes" | "no";
  call_email?: string;
  consent_required?: boolean;
  consent_contact?: boolean;
};

type StepKey =
  | "welcome"
  | "role"
  | "role_other"
  | "stage"
  | "goal"
  | "goal_other"
  | "familiarity"
  | "investor_focus"
  | "investor_dealflow"
  | "investor_gap"
  | "tools"
  | "friction"
  | "biggest_barrier"
  | "first_output"
  | "job_success"
  | "value_prop"
  | "trust_signal"
  | "clarity"
  | "better_means"
  | "signup"
  | "call"
  | "call_email"
  | "consent";

function buildSteps(a: ResearchAnswers): StepKey[] {
  const s: StepKey[] = ["welcome", "role"];
  if (a.role === "Other") {
    s.push("role_other");
  }
  if (a.role && !INVESTOR_ROLES.has(a.role)) {
    s.push("stage");
  }
  s.push("goal");
  if (a.goal === "Other") {
    s.push("goal_other");
  }
  s.push("familiarity");
  if (a.role && INVESTOR_ROLES.has(a.role)) {
    s.push("investor_focus", "investor_dealflow", "investor_gap");
  } else {
    s.push("tools", "friction", "biggest_barrier", "first_output");
  }
  s.push("job_success", "value_prop", "trust_signal", "clarity", "better_means", "signup", "call");
  if (a.wants_call === "yes") {
    s.push("call_email");
  }
  s.push("consent");
  return s;
}

const choiceClass = (selected: boolean) =>
  `w-full rounded-lg border px-4 py-3.5 text-left text-sm font-semibold transition-all [overflow-wrap:anywhere] break-words whitespace-normal sm:px-5 sm:py-4 ${
    selected
      ? "border-accent-500 bg-accent-50 text-accent-900 shadow-none dark:border-accent-400 dark:bg-accent-900/25 dark:text-accent-100"
      : "border-stone200 bg-white text-neutral900 hover:border-stone300 dark:border-neutral700 dark:bg-neutral900 dark:text-white dark:hover:border-neutral600"
  }`;

const ResearchSurveyPage: React.FC = () => {
  const navigate = useNavigate();
  const { setMessage } = useMessage();
  const { captureSurvey } = useSurveyAnalytics();
  const [answers, setAnswers] = useState<ResearchAnswers>({ tools: [] });
  const [stepIndex, setStepIndex] = useState(0);
  const [done, setDone] = useState(false);
  const [submitSurvey, { loading: submitting }] = useMutation(SUBMIT_SURVEY);

  const steps = useMemo(() => buildSteps(answers), [answers]);

  useEffect(() => {
    setStepIndex((i) => Math.min(Math.max(i, 0), Math.max(steps.length - 1, 0)));
  }, [steps.length]);

  const current = steps[stepIndex] ?? "welcome";
  const total = steps.length;

  const patch = useCallback((p: Partial<ResearchAnswers>) => {
    setAnswers((prev) => ({ ...prev, ...p }));
  }, []);

  const goNext = useCallback(() => {
    setStepIndex((i) => Math.min(i + 1, steps.length - 1));
  }, [steps.length]);

  const goBack = useCallback(() => {
    setStepIndex((i) => Math.max(i - 1, 0));
  }, []);

  const toggleTool = (label: string) => {
    const cur = new Set(answers.tools || []);
    if (cur.has(label)) {
      cur.delete(label);
    } else {
      cur.add(label);
    }
    patch({ tools: Array.from(cur) });
  };

  const handleSubmit = async () => {
    if (!answers.consent_required) {
      setMessage("Please accept the consent checkbox to continue.", "error");
      return;
    }
    const payload = {
      ...answers,
      consent_required: true,
    };
    try {
      await submitSurvey({
        variables: {
          input: {
            surveyType: "research",
            answersJson: JSON.stringify(payload),
            contactEmail: answers.call_email?.trim() || null,
          },
        },
      });
      captureSurvey("survey_completed", { track: "a", surface: "research_page" });
      setDone(true);
    } catch (e) {
      console.error(e);
      setMessage("We could not save your responses. Please try again.", "error");
    }
  };

  if (done) {
    return (
      <div className="manifest-page min-h-screen">
        <div className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center px-4 py-12 text-center ps-[max(1rem,env(safe-area-inset-left,0px))] pe-[max(1rem,env(safe-area-inset-right,0px))] pb-[max(2rem,env(safe-area-inset-bottom,0px))] pt-[max(1rem,env(safe-area-inset-top,0px))] sm:px-6 sm:py-16">
          <div className="manifest-panel w-full rounded-lg border border-stone200 px-8 py-12 dark:border-neutral700">
            <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Thank you</p>
            <h1 className="mt-4 text-2xl font-semibold text-neutral900 dark:text-white">Your perspective helps us build Manifest</h1>
            <p className="mt-4 text-sm leading-7 text-gray500 dark:text-gray400">
              If you shared an email for a research call, we may reach out. After you have used the workspace, you can also share{" "}
              <span className="font-semibold text-neutral800 dark:text-gray200">product experience feedback</span> from your account settings — that
              is a separate, shorter survey about quality and features, not this discovery flow.
            </p>
            <button
              type="button"
              onClick={() => navigate("/")}
              className="mt-8 inline-flex rounded-2xl bg-neutral900 px-8 py-3 text-sm font-semibold text-white dark:bg-white dark:text-neutral900"
            >
              Back to Manifest
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
      case "role":
        return !answers.role;
      case "role_other":
        return !(answers.role_other || "").trim();
      case "stage":
        return !answers.stage;
      case "goal":
        return !answers.goal;
      case "goal_other":
        return !(answers.goal_other || "").trim();
      case "familiarity":
        return !answers.familiarity;
      case "investor_focus":
        return !answers.investor_focus;
      case "investor_dealflow":
        return !answers.investor_dealflow;
      case "investor_gap":
        return false;
      case "biggest_barrier":
        return !answers.biggest_barrier;
      case "first_output":
        return !answers.first_output;
      case "job_success":
        return false;
      case "trust_signal":
        return !answers.trust_signal;
      case "better_means":
        return !answers.better_means;
      case "signup":
        return answers.signup_intent == null;
      case "call":
        return !answers.wants_call;
      case "call_email":
        return answers.wants_call === "yes" && !(answers.call_email || "").includes("@");
      case "consent":
        return !answers.consent_required;
      default:
        return false;
    }
  })();

  const onPrimary = () => {
    if (current === "consent") {
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
      nextLabel={current === "consent" ? "Submit survey" : "Continue"}
      nextDisabled={nextDisabled}
      isSubmitting={submitting && current === "consent"}
      {...props}
    />
  );

  if (current === "welcome") {
    return shell({
      eyebrow: "Discovery & positioning",
      title: "Help us understand what you need — before you judge the product",
      description: (
        <>
          <p>
            This flow is <strong className="font-semibold text-neutral800 dark:text-gray200">market and customer discovery</strong>: who you are,
            how you work today, and how we should explain Manifest. It is not a product-quality survey (you may not have logged in yet).
          </p>
          <p>
            Manifest is an AI workspace for turning startup ideas into structured documents, market research, collaboration, and discovery. About
            four minutes. Answers are stored securely and used for roadmap and messaging.
          </p>
        </>
      ),
      children: null,
    });
  }

  if (current === "role") {
    return shell({
      eyebrow: "About you",
      title: "Which best describes you?",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {ROLE_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.role === opt)} onClick={() => patch({ role: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "role_other") {
    return shell({
      eyebrow: "About you",
      title: "Tell us more",
      description: "How would you describe your role in one short phrase?",
      children: (
        <input
          type="text"
          value={answers.role_other || ""}
          onChange={(e) => patch({ role_other: e.target.value })}
          className="w-full rounded-lg border border-stone200 bg-white px-4 py-3.5 text-neutral900 shadow-inner outline-none focus:border-accent-400 dark:border-neutral700 dark:bg-neutral900 dark:text-white"
          placeholder="e.g. Corporate innovation lead"
        />
      ),
    });
  }

  if (current === "stage") {
    return shell({
      eyebrow: "Context",
      title: "What stage best fits you?",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {STAGE_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.stage === opt)} onClick={() => patch({ stage: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "goal") {
    return shell({
      eyebrow: "Goals",
      title: "What brought you to Manifest today?",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {GOAL_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.goal === opt)} onClick={() => patch({ goal: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "goal_other") {
    return shell({
      eyebrow: "Goals",
      title: "In a few words, what is your goal?",
      children: (
        <input
          type="text"
          value={answers.goal_other || ""}
          onChange={(e) => patch({ goal_other: e.target.value })}
          className="w-full rounded-lg border border-stone200 bg-white px-4 py-3.5 text-neutral900 outline-none focus:border-accent-400 dark:border-neutral700 dark:bg-neutral900 dark:text-white"
        />
      ),
    });
  }

  if (current === "familiarity") {
    return shell({
      eyebrow: "Context",
      title: "How familiar are you with AI tools for startup or knowledge work?",
      description: "This helps us calibrate how much we should explain versus assume.",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {FAMILIARITY_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.familiarity === opt)} onClick={() => patch({ familiarity: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "investor_focus") {
    return shell({
      eyebrow: "Investor lens",
      title: "When you first evaluate an early-stage opportunity, what do you weight most?",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {INVESTOR_FOCUS_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.investor_focus === opt)} onClick={() => patch({ investor_focus: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "investor_dealflow") {
    return shell({
      eyebrow: "Investor lens",
      title: "Where do most of the companies you evaluate come from?",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {INVESTOR_DEALFLOW_OPTIONS.map((opt) => (
            <button
              key={opt}
              type="button"
              className={choiceClass(answers.investor_dealflow === opt)}
              onClick={() => patch({ investor_dealflow: opt })}
            >
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "investor_gap") {
    return shell({
      eyebrow: "Investor lens",
      title: "What is usually missing or weak in first-pass founder materials?",
      description: "Optional — a sentence or two is enough.",
      children: (
        <textarea
          value={answers.investor_gap || ""}
          onChange={(e) => patch({ investor_gap: e.target.value })}
          placeholder="e.g. Clear ICP, believable milestones, comparable landscape…"
          rows={5}
          className="w-full resize-none rounded-lg border border-stone200 bg-white px-4 py-3 text-sm leading-7 text-neutral900 outline-none focus:border-accent-400 dark:border-neutral700 dark:bg-neutral900 dark:text-white"
        />
      ),
    });
  }

  if (current === "tools") {
    return shell({
      eyebrow: "Workflow",
      title: "How do you capture and develop startup ideas today?",
      description: "Select all that apply.",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {TOOL_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass((answers.tools || []).includes(opt))} onClick={() => toggleTool(opt)}>
              {opt}
            </button>
          ))}
          <label className="mt-2 block text-xs font-semibold uppercase tracking-[0.14em] text-gray500 dark:text-gray400">
            Other tools
            <input
              type="text"
              value={answers.tools_other || ""}
              onChange={(e) => patch({ tools_other: e.target.value })}
              className="mt-2 w-full rounded-lg border border-stone200 bg-white px-4 py-3 text-sm dark:border-neutral700 dark:bg-neutral900 dark:text-white"
              placeholder="Optional"
            />
          </label>
        </div>
      ),
    });
  }

  if (current === "friction") {
    return shell({
      eyebrow: "Workflow",
      title: "What is the biggest friction in how you develop or capture ideas today?",
      description: "Optional — one or two sentences. Think tools, handoffs, or mental load.",
      children: (
        <textarea
          value={answers.friction || ""}
          onChange={(e) => patch({ friction: e.target.value })}
          placeholder="Where does the process break down for you?"
          rows={5}
          className="w-full resize-none rounded-lg border border-stone200 bg-white px-4 py-3 text-sm leading-7 text-neutral900 outline-none focus:border-accent-400 dark:border-neutral700 dark:bg-neutral900 dark:text-white"
        />
      ),
    });
  }

  if (current === "biggest_barrier") {
    return shell({
      eyebrow: "Idea to reality",
      title: "What most often blocks you from turning an idea into something real?",
      description: "Pick the biggest bottleneck right now.",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {BIGGEST_BARRIER_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.biggest_barrier === opt)} onClick={() => patch({ biggest_barrier: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "first_output") {
    return shell({
      eyebrow: "Idea to reality",
      title: "If Manifest proved itself in your first session, what should it help you create first?",
      description: 'Pick the first output that would make you say "this is worth it."',
      children: (
        <div className="grid gap-2 sm:gap-3">
          {FIRST_OUTPUT_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.first_output === opt)} onClick={() => patch({ first_output: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "job_success") {
    return shell({
      eyebrow: "Jobs to be done",
      title: "If Manifest worked perfectly for you, what would be true a month from now?",
      description: "Optional — one short sentence is enough. Concrete outcomes beat vague praise.",
      children: (
        <textarea
          value={answers.job_success || ""}
          onChange={(e) => patch({ job_success: e.target.value })}
          placeholder="e.g. I could share a one-pager and deck without starting from scratch…"
          rows={4}
          className="w-full resize-none rounded-lg border border-stone200 bg-white px-4 py-3 text-sm leading-7 text-neutral900 outline-none focus:border-accent-400 dark:border-neutral700 dark:bg-neutral900 dark:text-white"
        />
      ),
    });
  }

  if (current === "value_prop") {
    return shell({
      eyebrow: "Positioning",
      title: "On the website today, which promise matters most to you?",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {VALUE_PROP_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.value_prop === opt)} onClick={() => patch({ value_prop: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "trust_signal") {
    return shell({
      eyebrow: "Trust",
      title: "What would make Manifest feel credible enough to rely on?",
      description: "Choose the strongest trust-builder.",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {TRUST_SIGNAL_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.trust_signal === opt)} onClick={() => patch({ trust_signal: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "clarity") {
    return shell({
      eyebrow: "Website & trust",
      title: "What felt unclear, overstated, or hard to believe about Manifest?",
      description: "Optional. We use this to tighten messaging, not to debate you.",
      children: (
        <textarea
          value={answers.clarity || ""}
          onChange={(e) => patch({ clarity: e.target.value })}
          placeholder="Optional"
          rows={5}
          className="w-full resize-none rounded-lg border border-stone200 bg-white px-4 py-3 text-sm leading-7 text-neutral900 outline-none focus:border-accent-400 dark:border-neutral700 dark:bg-neutral900 dark:text-white"
        />
      ),
    });
  }

  if (current === "better_means") {
    return shell({
      eyebrow: "Improvement vector",
      title: 'Thinking about your workflow, where would "meaningfully better" show up first?',
      description: "Choose the closest match. This is separate from which website headline appealed to you.",
      children: (
        <div className="grid gap-2 sm:gap-3">
          {BETTER_MEANS_OPTIONS.map((opt) => (
            <button key={opt} type="button" className={choiceClass(answers.better_means === opt)} onClick={() => patch({ better_means: opt })}>
              {opt}
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "signup") {
    const investorSide = answers.role ? INVESTOR_ROLES.has(answers.role) : false;
    const signupTitle = investorSide
      ? "How likely are you to create a free account this week to browse ideas, reels, or founder workspaces?"
      : "How likely are you to create a free account this week?";
    return shell({
      eyebrow: "Intent",
      title: signupTitle,
      children: (
        <div className="flex flex-wrap gap-2">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              className={choiceClass(answers.signup_intent === n)}
              onClick={() => patch({ signup_intent: n })}
            >
              {n}
              <span className="mt-0.5 block text-xs font-normal text-gray500 dark:text-gray400">
                {n === 1 ? "Not at all" : n === 5 ? "Very likely" : ""}
              </span>
            </button>
          ))}
        </div>
      ),
    });
  }

  if (current === "call") {
    return shell({
      eyebrow: "Follow-up",
      title: "Open to a 20-minute research video call?",
      children: (
        <div className="grid gap-3 sm:grid-cols-2">
          <button type="button" className={choiceClass(answers.wants_call === "yes")} onClick={() => patch({ wants_call: "yes" })}>
            Yes
          </button>
          <button type="button" className={choiceClass(answers.wants_call === "no")} onClick={() => patch({ wants_call: "no", call_email: "" })}>
            No
          </button>
        </div>
      ),
    });
  }

  if (current === "call_email") {
    return shell({
      eyebrow: "Follow-up",
      title: "Where should we reach you?",
      description: "Email for scheduling a short conversation.",
      children: (
        <input
          type="email"
          value={answers.call_email || ""}
          onChange={(e) => patch({ call_email: e.target.value })}
          className="w-full rounded-lg border border-stone200 bg-white px-4 py-3.5 text-neutral900 outline-none focus:border-accent-400 dark:border-neutral700 dark:bg-neutral900 dark:text-white"
          placeholder="you@company.com"
        />
      ),
    });
  }

  if (current === "consent") {
    return shell({
      eyebrow: "Submit",
      title: "Almost done",
      description:
        "This submission is discovery and positioning research only. Product experience feedback is collected separately after you use the app.",
      children: (
        <div className="space-y-4">
          <label className="flex cursor-pointer gap-3 rounded-lg border border-stone200 bg-stone50/80 p-4 dark:border-neutral700 dark:bg-neutral800/80">
            <input
              type="checkbox"
              checked={!!answers.consent_required}
              onChange={(e) => patch({ consent_required: e.target.checked })}
              className="mt-1 h-4 w-4 rounded border-stone300 text-accent-600"
            />
            <span className="text-sm leading-6 text-neutral800 dark:text-gray200">
              I agree that Manifest may use my responses to improve the product. <span className="font-semibold">(Required)</span>
            </span>
          </label>
          <label className="flex cursor-pointer gap-3 rounded-lg border border-stone200 bg-white p-4 dark:border-neutral700 dark:bg-neutral900">
            <input
              type="checkbox"
              checked={!!answers.consent_contact}
              onChange={(e) => patch({ consent_contact: e.target.checked })}
              className="mt-1 h-4 w-4 rounded border-stone300 text-accent-600"
            />
            <span className="text-sm leading-6 text-neutral800 dark:text-gray200">
              You may contact me about follow-up research or early access. (Optional)
            </span>
          </label>
        </div>
      ),
    });
  }

  return null;
};

export default ResearchSurveyPage;
