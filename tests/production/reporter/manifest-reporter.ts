/**
 * Custom Playwright reporter that ships each test result to the
 * Manifest backend's internal production-test results endpoint.
 *
 * The backend (production_test_service) persists the row and, on
 * failure, dedupes + files a GitHub issue.
 *
 * Required env:
 *   MANIFEST_INTERNAL_API_URL  Base URL of the deployed backend (defaults to MANIFEST_TEST_TARGET_URL).
 *   MANIFEST_AGENT_LOOP_SECRET Secret for the X-Manifest-Agent-Key header.
 *
 * If MANIFEST_AGENT_LOOP_SECRET is missing, the reporter logs each
 * result locally and skips posting — useful for local dev runs.
 *
 * See docs/PRODUCTION_TESTING.md.
 */

import type {
  Reporter,
  TestCase,
  TestResult,
  FullConfig,
} from "@playwright/test/reporter";

type Severity = "low" | "medium" | "high";
type Status = "pass" | "fail" | "flaky" | "error" | "skipped";

interface ManifestTestResultBody {
  test_name: string;
  status: Status;
  suite?: string;
  environment: string;
  severity: Severity;
  error_message?: string;
  stack_trace?: string;
  console_errors?: unknown[];
  network_errors?: unknown[];
  suspected_files?: string[];
  git_sha?: string;
  git_ref?: string;
  ci_run_url?: string;
  runner: string;
  duration_ms?: number;
  started_at?: string;
  completed_at?: string;
  create_github_issue: boolean;
  metadata?: Record<string, unknown>;
}

class ManifestReporter implements Reporter {
  private apiUrl: string;
  private secret: string;
  private environment: string;
  private gitSha?: string;
  private gitRef?: string;
  private ciRunUrl?: string;
  private projectName: string = "production-tests";

  constructor() {
    this.apiUrl = (
      process.env.MANIFEST_INTERNAL_API_URL ||
      process.env.MANIFEST_TEST_TARGET_URL ||
      ""
    ).replace(/\/+$/, "");
    this.secret = process.env.MANIFEST_AGENT_LOOP_SECRET || "";
    this.environment =
      process.env.MANIFEST_TEST_ENVIRONMENT || "production";
    this.gitSha = process.env.GITHUB_SHA || process.env.GIT_SHA;
    this.gitRef = process.env.GITHUB_REF || process.env.GIT_REF;
    if (process.env.GITHUB_SERVER_URL && process.env.GITHUB_REPOSITORY && process.env.GITHUB_RUN_ID) {
      this.ciRunUrl = `${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`;
    }
  }

  onBegin(config: FullConfig) {
    if (!this.apiUrl) {
      console.warn(
        "[manifest-reporter] no MANIFEST_INTERNAL_API_URL / MANIFEST_TEST_TARGET_URL — results will only be logged locally",
      );
    } else if (!this.secret) {
      console.warn(
        "[manifest-reporter] MANIFEST_AGENT_LOOP_SECRET missing — results will only be logged locally (POST would be unauthenticated)",
      );
    } else {
      console.log(`[manifest-reporter] posting results to ${this.apiUrl}/api/internal/production-tests/results`);
    }
    this.projectName = config.projects[0]?.name || "production-tests";
  }

  async onTestEnd(test: TestCase, result: TestResult) {
    const body = this._buildBody(test, result);
    if (!this.apiUrl || !this.secret) {
      console.log(`[manifest-reporter] (local) ${body.test_name} → ${body.status}`);
      return;
    }
    try {
      const response = await fetch(
        `${this.apiUrl}/api/internal/production-tests/results`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Manifest-Agent-Key": this.secret,
          },
          body: JSON.stringify(body),
        },
      );
      if (!response.ok) {
        const text = await response.text();
        console.error(
          `[manifest-reporter] post failed (${response.status}): ${text.slice(0, 200)}`,
        );
      }
    } catch (err) {
      console.error(`[manifest-reporter] post error: ${err}`);
    }
  }

  private _buildBody(test: TestCase, result: TestResult): ManifestTestResultBody {
    const status = this._mapStatus(result);
    const severity = this._severityFor(test);
    const errorMessage = result.errors
      .map((e) => e.message || "")
      .filter(Boolean)
      .join("\n\n") || undefined;
    const stack =
      result.errors
        .map((e) => e.stack || "")
        .filter(Boolean)
        .join("\n---\n") || undefined;

    const suspected = inferSuspectedFiles(stack);

    return {
      test_name: `${test.titlePath().slice(1).join(" > ")}@${this.projectName}`,
      status,
      suite: test.parent.title || undefined,
      environment: this.environment,
      severity,
      error_message: errorMessage,
      stack_trace: stack,
      suspected_files: suspected,
      git_sha: this.gitSha,
      git_ref: this.gitRef,
      ci_run_url: this.ciRunUrl,
      runner: `playwright@${this.projectName}`,
      duration_ms: Math.round(result.duration),
      started_at: result.startTime.toISOString(),
      completed_at: new Date(result.startTime.getTime() + result.duration).toISOString(),
      create_github_issue: status === "fail" || status === "error",
      metadata: {
        retry: result.retry,
        worker_index: result.workerIndex,
      },
    };
  }

  private _mapStatus(result: TestResult): Status {
    switch (result.status) {
      case "passed":
        return "pass";
      case "failed":
        return "fail";
      case "timedOut":
        return "fail";
      case "interrupted":
        return "error";
      case "skipped":
        return "skipped";
      default:
        return "error";
    }
  }

  private _severityFor(test: TestCase): Severity {
    const tags = test.title + " " + (test.parent.title || "");
    if (/@sev:high\b/i.test(tags)) return "high";
    if (/@sev:low\b/i.test(tags)) return "low";
    return "medium";
  }
}

/**
 * Pull repo-relative file hints out of a stack trace so reviewers (and
 * the bug-fix agent) have a starting point. We only keep paths that
 * look like they live in the repo — node_modules and absolute system
 * paths are stripped.
 */
function inferSuspectedFiles(stack?: string): string[] | undefined {
  if (!stack) return undefined;
  const lines = stack.split("\n");
  const matches = new Set<string>();
  for (const line of lines) {
    const m = line.match(/\(?([^()\s]+\.(?:ts|tsx|js|jsx|py|sql)):\d+/);
    if (!m) continue;
    let path = m[1];
    if (path.includes("node_modules")) continue;
    if (path.startsWith("/")) continue;
    if (path.startsWith("..")) continue;
    matches.add(path);
    if (matches.size >= 5) break;
  }
  return matches.size ? Array.from(matches) : undefined;
}

export default ManifestReporter;
