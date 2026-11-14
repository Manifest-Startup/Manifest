/**
 * Route-specific pre-hydration shell for crawlers and accessibility audits.
 * Mirrors backend/app/services/spa_prerender_shell.py ROUTE_SHELLS.
 */
(function applyManifestSpaShell() {
  var ROUTES = {
    "/": {
      title: "Manifest — Turn your idea into a plan",
      description:
        "Manifest is an AI workspace that turns raw startup ideas into a business model canvas, pitch deck, product requirements and provisional patent drafts.",
      h1: "Turn your idea into a plan.",
      body:
        '<p>Manifest is an AI-powered workspace that helps founders turn notes into structured, investor-ready startup artifacts.</p><p><a href="/auth">Sign in</a>, read the <a href="/docs/api">API docs</a> or the <a href="/agents.md">agent guide</a>.</p>',
      canonical: "/",
    },
    "/home": {
      title: "Manifest — AI startup workspace",
      description:
        "Explore how Manifest helps founders validate ideas, generate documents, and collaborate with investors.",
      h1: "Build your startup with AI",
      body:
        "<p>Generate pitch decks, business model canvas, and legal-oriented drafts from one workspace.</p>",
      canonical: "/home",
    },
    "/login": {
      title: "Sign in to Manifest",
      description:
        "Sign in to your Manifest workspace to continue building startup ideas and generated artifacts.",
      h1: "Sign in to Manifest",
      body:
        '<p>Use your email and password to access your ideas and documents.</p><p>New here? <a href="/signup">Create an account</a>.</p>',
      canonical: "/auth",
    },
    "/signup": {
      title: "Create your Manifest account",
      description:
        "Create a Manifest account to save your startup ideas, generated documents, and collaboration workspace.",
      h1: "Create your Manifest account",
      body:
        '<p>Start a workspace to turn raw ideas into structured startup artifacts.</p><p>Already have an account? <a href="/login">Sign in</a>.</p>',
      canonical: "/auth",
    },
    "/auth": {
      title: "Sign in to Manifest",
      description: "Sign in or create a Manifest account to access your startup workspace.",
      h1: "Sign in to Manifest",
      body: "<p>Access your ideas, pitch decks, and investor-ready documents.</p>",
      canonical: "/auth",
    },
    "/shorts": {
      title: "Pitch Reels — Discover startup ideas",
      description: "Browse short pitch reels from published startup ideas on Manifest.",
      h1: "Pitch Reels",
      body: '<p>Discover founder pitch clips. Canonical route: <a href="/pitch-reels">/pitch-reels</a>.</p>',
      canonical: "/pitch-reels",
    },
    "/pitch-reels": {
      title: "Pitch Reels — Discover startup ideas",
      description: "Browse short pitch reels from published startup ideas on Manifest.",
      h1: "Pitch Reels",
      body: "<p>Watch founder pitch clips and explore published ideas.</p>",
      canonical: "/pitch-reels",
    },
  };

  function normalizePath(pathname) {
    if (!pathname || pathname === "/") return "/";
    return pathname.replace(/\/$/, "") || "/";
  }

  // The backend already rendered the full route shell (data-server-shell);
  // only fill in the shell when the HTML came from a static host.
  if (document.querySelector("[data-server-shell]")) return;

  var path = normalizePath(window.location.pathname);
  var shell = ROUTES[path];
  if (!shell) return;

  document.title = shell.title;

  var meta = document.querySelector('meta[name="description"]');
  if (meta) meta.setAttribute("content", shell.description);
  else {
    meta = document.createElement("meta");
    meta.name = "description";
    meta.content = shell.description;
    document.head.appendChild(meta);
  }

  var canonical = document.querySelector('link[rel="canonical"]');
  var href = shell.canonical || path;
  if (canonical) canonical.setAttribute("href", href);
  else {
    canonical = document.createElement("link");
    canonical.rel = "canonical";
    canonical.href = href;
    document.head.appendChild(canonical);
  }

  var root = document.getElementById("root");
  if (!root) return;

  var existing = document.getElementById("manifest-static-shell");
  var main = existing || document.createElement("main");
  main.id = "manifest-static-shell";
  main.className = "manifest-static-shell";
  main.innerHTML = "<h1>" + shell.h1 + "</h1>" + shell.body;
  if (!existing) root.insertBefore(main, root.firstChild);
})();
