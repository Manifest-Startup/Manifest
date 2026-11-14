import PageHeader from "features/common-ui/PageHeader";
import React from "react";
import { Link } from "react-router-dom";

interface GuideScreenshot {
  src: string;
  alt: string;
  caption: string;
}

interface GuideSection {
  id: string;
  label: string;
  kicker: string;
  title: string;
  intro: string;
  steps: string[];
  details?: string[];
  tip?: string;
  screenshot?: GuideScreenshot;
  secondaryScreenshot?: GuideScreenshot;
}

const sections: GuideSection[] = [
  {
    id: "getting-started",
    label: "Getting started",
    kicker: "Start here",
    title: "Begin from the public landing page and orient yourself before you create anything.",
    intro:
      "The public homepage is designed to explain the product quickly, direct new users to sign up, and help returning users move into the main workspace.",
    steps: [
      "Open the home page to understand the main Manifest workflow and who the product is for.",
      "Use the primary call to action to move into account creation or sign in if you already have an account.",
      "If you are evaluating the product, use the public marketing and learn-more pages to understand the main value before you commit to a workspace.",
    ],
    details: [
      "The top navigation stays intentionally light. Once you are authenticated, the primary destinations become the ideas workspace and pitch reels.",
      "Docs live separately so they do not compete with the product's main working surfaces.",
    ],
    tip: "If the app is running in demo mode, the backend can auto-enable a sample identity when the database is not configured. That is useful for exploration, but it should not be treated like a production account.",
    screenshot: {
      src: "/docs/images/guide/landing-overview.png",
      alt: "Manifest landing page with primary calls to action and product overview sections.",
      caption: "The landing page introduces the founder workflow and provides the fastest path into the app.",
    },
  },
  {
    id: "auth-and-guest-mode",
    label: "Sign in and guest mode",
    kicker: "Access",
    title: "Choose between a full account and the guest path depending on how quickly you want to start.",
    intro:
      "Manifest supports standard account creation as well as a try-before-signup guest flow. Guest mode is useful when you want to experience the workspace immediately and decide later whether to create a full account.",
    steps: [
      "Use the authentication page to sign up or log in with your email-based account.",
      "If guest mode is available, start there when you want a fast, lower-friction way to explore the product.",
      "When you later create or log into a real account, the guest workspace can be merged into that full account so you keep the work you already created.",
    ],
    details: [
      "Guest accounts are intentionally limited. They can explore the workspace but cannot publish, message founders, invest, follow users, or invite collaborators until they upgrade to a full account.",
      "The merge step is one-time and tied to the guest session credentials stored client-side during the guest flow.",
    ],
    tip: "Use a full account as soon as you are ready to publish, collaborate, or use messaging. Guest mode is best for evaluation and early note capture.",
    screenshot: {
      src: "/docs/images/guide/auth-signup.png",
      alt: "Manifest authentication screen showing sign in and account creation form elements.",
      caption: "The auth screen is where you create a permanent account or return to an existing workspace.",
    },
  },
  {
    id: "ideas-workspace",
    label: "Ideas workspace",
    kicker: "Core workflow",
    title: "Most of your time in Manifest will happen inside the ideas workspace.",
    intro:
      "The ideas workspace is built around one shared idea object. Instead of scattering work across unrelated tools, Manifest lets you keep your note, business canvas, deck, requirements, patent draft, and supporting context connected.",
    steps: [
      "Open the ideas library from the left rail and either create a new idea or pick an existing one.",
      "Use the aspect list for that idea to switch between the main note, business model canvas, deck, requirements, patent, and costs views.",
      "Edit the main note to give Manifest the founder context it needs. Generated sections become more useful when the source note is specific and current.",
      "Use the right context panel to review owner information and similar-ideas output without losing your place in the main editor.",
    ],
    details: [
      "The idea title can be renamed directly from the workspace, which keeps the sidebar library and detail view aligned.",
      "The aspect labels in the UI are intentionally compact: Note, Canvas, Costs, Deck, Requirements, and Patent.",
      "Generated content stays tied to the current idea, so iterating the note and regenerating artifacts keeps the workspace coherent.",
    ],
    tip: "Treat the note as the source of truth. The clearer your note becomes, the better the generated artifacts tend to be.",
    screenshot: {
      src: "/docs/images/guide/ideas-workspace.png",
      alt: "Ideas workspace showing the left library, main editor, and right context panel.",
      caption: "The workspace combines idea selection, editing, generated artifacts, and context into one working screen.",
    },
  },
  {
    id: "focus-and-layout",
    label: "Layout and focus mode",
    kicker: "Deep work",
    title: "Collapse surrounding chrome when you want to focus on one idea.",
    intro:
      "The workspace layout is adjustable. You can collapse the library, collapse the context panel, or enter focus mode to make the editor the center of attention.",
    steps: [
      "Use the layout controls in the workspace to collapse the left library or right context panel when you need more writing space.",
      "Enter focus mode when you want the main idea surface to take over the workspace.",
      "Use `Cmd` + `Shift` + `F` on Mac, or `Ctrl` + `Shift` + `F` on Windows and Linux, to toggle focus mode from the keyboard.",
      "Press `Escape` to exit focus mode quickly.",
    ],
    details: [
      "Manifest remembers your workspace layout in local storage, so the app usually opens the way you left it.",
      "Voice commands can also trigger certain workspace layout actions, which is useful during hands-free browsing or demos.",
    ],
    tip: "Focus mode is especially useful when you are refining a note before regenerating downstream artifacts.",
    screenshot: {
      src: "/docs/images/guide/workspace-focus-mode.png",
      alt: "Ideas workspace in focus mode with surrounding side panels hidden.",
      caption: "Focus mode strips the workspace down so you can stay on the main note or document.",
    },
  },
  {
    id: "collaboration-and-publishing",
    label: "Collaboration and publishing",
    kicker: "Share work",
    title: "Bring other people into an idea only when the workspace is ready for that next step.",
    intro:
      "Manifest supports idea sharing and collaboration without turning every draft into a public artifact too early. Invite collaborators when you need joint work, and publish when you want the idea to participate in broader discovery and pitch-reel flows.",
    steps: [
      "Open the share controls from the active idea when you are ready to invite collaborators.",
      "Review invitations and collaborator roles carefully so the right people have the right level of access.",
      "Publish an idea only when you want it exposed to broader product surfaces such as messaging eligibility for non-owners and pitch-reel distribution.",
    ],
    details: [
      "Publishing changes product behavior. Non-owners can only start a conversation about an idea when that idea is published.",
      "Publishing can also sync the idea into the pitch-reels system, which is why it is treated as a meaningful milestone rather than a cosmetic toggle.",
    ],
    tip: "Invite collaborators during drafting. Publish only when the core note and generated materials are strong enough to represent the project well.",
    screenshot: {
      src: "/docs/images/guide/collaboration-share-modal.png",
      alt: "Share modal open on an idea, showing collaboration invite options.",
      caption: "The share flow helps you control when an idea stays private, becomes collaborative, or is ready to publish.",
    },
  },
  {
    id: "pitch-reels-and-messages",
    label: "Pitch reels and messages",
    kicker: "Discovery",
    title: "Use reels for discovery and messages for direct founder communication.",
    intro:
      "Pitch reels provide an immersive browsing experience for published ideas, while messaging supports direct conversations between users. These two surfaces work together: discovery happens in the feed, and deeper follow-up happens in conversations.",
    steps: [
      "Open Pitch Reels to browse published ideas in the immersive feed.",
      "Use the feed to explore ideas, react to what stands out, and move deeper into a founder or idea when you want more context.",
      "Open Messages to review existing conversations, unread counts, and discussion history.",
      "Start a new conversation about an idea only when that idea is published and the platform allows founder messaging for it.",
    ],
    details: [
      "Messaging is product-aware. If the idea is unpublished and you are not the owner, the app intentionally blocks that conversation path.",
      "Unread counts surface in the main profile dropdown so you can tell whether you have active founder conversations waiting.",
    ],
    tip: "Use reels to discover broadly, then messages to narrow into specific founder conversations once interest is real.",
    screenshot: {
      src: "/docs/images/guide/pitch-reels-feed.png",
      alt: "Pitch reels feed showing published idea cards in the immersive shorts interface.",
      caption: "Pitch Reels turn published ideas into a lightweight discovery surface for browsing and follow-up.",
    },
  },
  {
    id: "account-search-and-voice",
    label: "Account, search, and voice",
    kicker: "Power tools",
    title: "Round out your workflow with account settings, universal search, and voice controls.",
    intro:
      "Once your workspace is active, the supporting tools matter. Account settings help you manage profile and API access, universal search helps you move faster, and voice adds a hands-free control layer on top of the app.",
    steps: [
      "Open Account from the profile dropdown to manage profile details, connected settings, and API access.",
      "Use universal search from the navigation bar to jump into recent work and search across your workspace faster than manual browsing.",
      "Use the floating voice control when you want guided, hands-free navigation or app-control actions.",
      "Open the API reference when you need to create clients, issue keys, or integrate Manifest workflows with external tools.",
    ],
    details: [
      "API keys are managed in account settings, but they apply to `/api/v1` routes. The main GraphQL app API uses session auth instead.",
      "Manifest Voice exposes a deterministic app-control catalog behind the scenes, which is documented in the API reference as well.",
    ],
    tip: "If you are building on top of Manifest, use this page for product usage and jump to the dedicated API page for the technical contract.",
  },
];

const ScreenshotFigure: React.FC<GuideScreenshot> = ({ src, alt, caption }) => (
  <figure className="mt-6 overflow-hidden rounded-lg border border-stone200 bg-white shadow-none dark:border-neutral700 dark:bg-neutral900">
    <img src={src} alt={alt} className="w-full object-cover" loading="lazy" />
    <figcaption className="border-t border-stone200 px-5 py-4 text-sm leading-6 text-gray500 dark:border-neutral700 dark:text-gray300">
      {caption}
    </figcaption>
  </figure>
);

const UserGuidePage: React.FC = () => {
  return (
    <div className="manifest-page">
      <div className="manifest-page-shell">
        <PageHeader eyebrow="Documentation" title="User guide" description="Learn the workspace, collaboration, publishing, and account tools.">
          <Link to="/ideas" className="manifest-control manifest-control-primary">Open the app</Link>
          <Link to="/docs/api" className="manifest-control manifest-control-secondary">View API docs</Link>
        </PageHeader>

        <div className="grid gap-6 lg:grid-cols-[14rem_minmax(0,1fr)]">
          <aside className="h-fit min-w-0 border-b border-theme-primary pb-4 lg:border-b-0 lg:border-r lg:pr-4 lg:sticky lg:top-24">
            <p className="px-3 text-[0.72rem] font-medium text-gray500 dark:text-gray400">Navigate guide</p>
            <nav className="mt-3 flex flex-wrap gap-1 lg:flex-col">
              {sections.map((section) => (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  className="rounded-2xl px-3 py-2.5 text-sm font-semibold text-neutral700 hover:bg-white/70 hover:text-neutral900 dark:text-gray300 dark:hover:bg-neutral800 dark:hover:text-white"
                >
                  {section.label}
                </a>
              ))}
            </nav>
          </aside>

          <main className="min-w-0 space-y-6">
            {sections.map((section) => (
              <section key={section.id} id={section.id} className="manifest-reading-surface border-b border-theme-primary">
                <p className="manifest-kicker">{section.kicker}</p>
                <h2 className="mt-3 text-xl font-semibold sm:text-2xl tracking-[-0.03em] text-neutral900 dark:text-white">{section.title}</h2>
                <p className="manifest-subtitle mt-4 text-sm sm:text-base">{section.intro}</p>

                <ol className="mt-6 list-decimal space-y-3 pl-5 text-sm leading-7 text-gray500 dark:text-gray300">
                  {section.steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>

                {section.details ? (
                  <div className="mt-6 grid gap-4 md:grid-cols-2">
                    {section.details.map((detail) => (
                      <div key={detail} className="manifest-card px-5 py-5">
                        <p className="text-sm leading-7 text-gray500 dark:text-gray300">{detail}</p>
                      </div>
                    ))}
                  </div>
                ) : null}

                {section.tip ? (
                  <div className="mt-6 rounded-lg border border-accent-200 bg-accent-50/80 px-5 py-5 dark:border-accent-900/60 dark:bg-accent-900/30">
                    <p className="text-xs font-medium text-accent-700 dark:text-accent-300">Best practice</p>
                    <p className="mt-2 text-sm leading-7 text-neutral900 dark:text-gray100">{section.tip}</p>
                  </div>
                ) : null}

                {section.screenshot ? <ScreenshotFigure {...section.screenshot} /> : null}
                {section.secondaryScreenshot ? <ScreenshotFigure {...section.secondaryScreenshot} /> : null}
              </section>
            ))}

            <section className="manifest-reading-surface border-b border-theme-primary">
              <p className="manifest-kicker">Next step</p>
              <h2 className="mt-3 text-xl font-semibold sm:text-2xl tracking-[-0.03em] text-neutral900 dark:text-white">Move from usage to integration when you are ready.</h2>
              <p className="manifest-subtitle mt-4 text-sm sm:text-base">
                Once the product workflow is familiar, open the API reference for the exact auth model, route families, and detailed
                contracts behind the surfaces you have just seen in the UI.
              </p>
              <div className="mt-6">
                <Link
                  to="/docs/api"
                  className="manifest-control manifest-control-secondary"
                >
                  Open the API reference
                </Link>
              </div>
            </section>
          </main>
        </div>
      </div>
    </div>
  );
};

export default UserGuidePage;
