import React, { useCallback, useEffect, useRef, useState } from "react";
import { useApolloClient, useMutation, useQuery, useReactiveVar } from "@apollo/client/react";
import { Link, useSearchParams } from "react-router-dom";

import { useTheme } from "context/ThemeContext";
import Button from "features/common-ui/Button";
import { useFormState, useInputHandlers } from "features/common-ui/hooks/formHooks";
import Input from "features/common-ui/Input";
import { accountVar, userVar } from "features/core/apollo/localState";
import { GET_ACCOUNT, GET_AI_KEY_STATUS, GET_GITHUB_ACCOUNT, GET_INTEGRATIONS, GET_MY_PORTFOLIO, UPDATE_ACCOUNT } from "features/core/apollo/queries";
import { createLogger } from "features/core/logError";
import { useSafeQuery } from "features/common-ui/api/useSafeQuery";
import ImportExportModal from "features/ideas/components/ImportExportModal";
import ProductFeedbackSurveyCard from "features/feedback/ProductFeedbackSurveyCard";
import SurveyInsightsPanel from "features/feedback/SurveyInsightsPanel";

import ApiAccessSection from "./ApiAccessSection";
import AiKeySection from "./AiKeySection";
import { StorageSection } from "features/vault/StorageSection";
import GitHubSection, { type GithubAccount } from "./GitHubSection";
import IntegrationsSection from "./IntegrationsSection";
import OpenMediaSection from "./OpenMediaSection";
import PrivacyControlsPanel from "./PrivacyControlsPanel";
import SecuritySettingsPanel from "./SecuritySettingsPanel";
import SettingsView, { SettingsCard, type SettingsSection } from "./SettingsView";
import { useOpenMediaLink } from "features/open-media/useOpenMediaLink";
import { uploadProfilePicture } from "../api/uploadProfilePicture";
import { getAvatarUrl, isPersistedProfilePictureUrl, normalizeGravatarInput } from "../utils/gravatar";
import { SkillsPicker } from "features/common-ui/SkillsPicker";
import { GET_AVAILABLE_SKILLS } from "features/core/apollo/queries";
import type { PortfolioItem } from "features/core/apollo/operationTypes";

export interface Account {
  userId: string;
  email: string;
  username?: string;
  firstName?: string;
  lastName?: string;
  country?: string;
  bio?: string;
  address?: string;
  state?: string;
  gravatarHash?: string;
  profilePictureUrl?: string;
  skills?: string[];
}

const logger = createLogger("AccountPage");

const SETTINGS_SECTION_IDS = ["profile", "appearance", "connections", "integrations", "developer", "data", "privacy", "feedback"];
const HASH_TO_SECTION: Record<string, string> = {
  "ai-key": "connections",
  "open-media": "connections",
  integrations: "integrations",
  "api-access": "developer",
  storage: "data",
  "import-export": "data",
  sessions: "privacy",
  "privacy-controls": "privacy",
  "delete-account": "privacy",
};

const THEME_OPTIONS = [
  { key: "light", label: "Light" },
  { key: "dark", label: "Dark" },
  { key: "system", label: "Match system" },
] as const;

const MockUi: React.FC<{ mode: "light" | "dark"; half?: boolean }> = ({ mode, half }) => (
  <div className={`mock-ui ${mode} ${half ? "half" : ""}`} aria-hidden="true">
    <div className="mock-side">
      <div className="mock-line strong" style={{ width: "70%" }} />
      <div className="mock-line" />
      <div className="mock-line" style={{ width: "80%" }} />
      <div className="mock-line" style={{ width: "60%" }} />
    </div>
    <div className="mock-main">
      <div className="mock-line strong" style={{ width: "45%" }} />
      <div className="mock-line" />
      <div className="mock-line" style={{ width: "90%" }} />
      <div className="mock-line" style={{ width: "75%" }} />
    </div>
  </div>
);

const SectionCard: React.FC<{
  eyebrow: string;
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}> = ({ eyebrow, title, description, children, className = "" }) => (
  <section className={`manifest-panel p-4 sm:p-5 ${className}`}>
    <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">{eyebrow}</p>
    <h2 className="mt-3 text-[1.35rem] font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">{title}</h2>
    {description ? <p className="mt-2 break-words text-sm leading-6 text-gray500 dark:text-gray400">{description}</p> : null}
    <div className="mt-5">{children}</div>
  </section>
);

const AccountPage: React.FC = () => {
  logger.log("rendered");

  const { isLoggedIn } = useReactiveVar(userVar);
  const accountState = useReactiveVar(accountVar);
  const { data, loading, error, refetch } = useSafeQuery(GET_ACCOUNT, {
    fetchPolicy: "cache-first",
    nextFetchPolicy: "cache-first",
    notifyOnNetworkStatusChange: true,
  });
  const { data: portfolioData, loading: portfolioLoading, error: portfolioError } = useQuery(GET_MY_PORTFOLIO, {
    skip: !isLoggedIn,
  });
  const [updateAccount] = useMutation(UPDATE_ACCOUNT, {
    refetchQueries: [{ query: GET_ACCOUNT }],
  });
  const client = useApolloClient();
  const { theme, setTheme } = useTheme();
  const { data: skillsData } = useSafeQuery(GET_AVAILABLE_SKILLS);
  const [searchParams, setSearchParams] = useSearchParams();
  const focusIntegrationId = searchParams.get("focusIntegration");
  const sectionParam = searchParams.get("section");
  const { data: aiKeyData } = useQuery(GET_AI_KEY_STATUS, { skip: !isLoggedIn });
  const openMedia = useOpenMediaLink();
  const { data: integrationsData } = useQuery(GET_INTEGRATIONS, { skip: !isLoggedIn });
  const connectedIntegrations = integrationsData?.integrations?.length ?? 0;
  const { data: githubData } = useQuery<{ githubAccount: GithubAccount }>(GET_GITHUB_ACCOUNT, { skip: !isLoggedIn });
  const github = githubData?.githubAccount;

  const [activeTab, setActiveTab] = useState<"portfolio" | "settings">(
    focusIntegrationId || sectionParam ? "settings" : "portfolio",
  );
  const activeSection = sectionParam && SETTINGS_SECTION_IDS.includes(sectionParam) ? sectionParam : focusIntegrationId ? "integrations" : "profile";
  const [focusAnchor, setFocusAnchor] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const selectSection = useCallback(
    (id: string) => {
      const next = new URLSearchParams(searchParams);
      next.set("section", id);
      next.delete("focusIntegration");
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );
  const clearFocusAnchor = useCallback(() => setFocusAnchor(null), []);
  const [gravatarInput, setGravatarInput] = useState("");
  const [localProfilePreviewUrl, setLocalProfilePreviewUrl] = useState<string | null>(null);
  const [uploadMessage, setUploadMessage] = useState("");
  const [profilePictureUploading, setProfilePictureUploading] = useState(false);
  const [isImportExportOpen, setIsImportExportOpen] = useState(false);
  const [accountLoadStalled, setAccountLoadStalled] = useState(false);
  const [skills, setSkills] = useState<string[]>([]);
  const { formData, updateField } = useFormState<{ email: string; firstName: string; lastName: string }>({
    email: "",
    firstName: "",
    lastName: "",
  });
  const { handleInputChange } = useInputHandlers(updateField);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const investments: PortfolioItem[] = portfolioData?.myPortfolio || [];

  useEffect(() => {
    if (focusIntegrationId) {
      setActiveTab("settings");
    }
  }, [focusIntegrationId]);

  // Old deep links ("/account#ai-key" from the "Add your key" banner, "#storage",
  // "#open-media") still land on the right card.
  useEffect(() => {
    const anchor = window.location.hash.slice(1);
    const section = HASH_TO_SECTION[anchor];
    if (!section) return;
    setActiveTab("settings");
    selectSection(section);
    setFocusAnchor(anchor);
    // Only on first load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!data) {
      return;
    }

    const account = data.account;
    accountVar({ accountData: account, loading: false, error: null });
    const gravatar = account?.gravatarHash || "";
    setGravatarInput(gravatar);
    updateField("email", account?.email || "");
    updateField("firstName", account?.firstName || "");
    updateField("lastName", account?.lastName || "");
    setSkills(account?.skills ?? []);
  }, [data, updateField]);

  useEffect(() => {
    if (!loading) {
      setAccountLoadStalled(false);
      return;
    }

    const timeout = window.setTimeout(() => {
      setAccountLoadStalled(true);
    }, 10000);

    return () => window.clearTimeout(timeout);
  }, [loading]);

  useEffect(() => {
    return () => {
      if (localProfilePreviewUrl) {
        URL.revokeObjectURL(localProfilePreviewUrl);
      }
    };
  }, [localProfilePreviewUrl]);

  const handleGravatarChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setGravatarInput(event.target.value);
  };

  const handleProfilePictureUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setProfilePictureUploading(true);
    setUploadMessage("");
    try {
      await uploadProfilePicture(file);
      await client.refetchQueries({ include: [GET_ACCOUNT] });
      if (localProfilePreviewUrl) {
        URL.revokeObjectURL(localProfilePreviewUrl);
      }
      setLocalProfilePreviewUrl(null);
      setUploadMessage("Profile picture saved.");
    } catch (uploadError) {
      logger.error("Profile picture upload failed", uploadError);
      setUploadMessage(uploadError instanceof Error ? uploadError.message : "Could not upload profile picture.");
    } finally {
      setProfilePictureUploading(false);
      event.target.value = "";
    }
  };

  const handleSaveDetails = async () => {
    setSaveState("saving");
    try {
      const normalizedGravatar = normalizeGravatarInput(gravatarInput);
      const { data: updatedData } = await updateAccount({
        variables: {
          input: {
            firstName: formData.firstName,
            lastName: formData.lastName,
            email: formData.email,
            gravatarHash: normalizedGravatar,
            skills,
          },
        },
      });

      if (updatedData?.updateAccount) {
        accountVar({ accountData: updatedData.updateAccount, loading: false, error: null });
        setGravatarInput(updatedData.updateAccount.gravatarHash || normalizedGravatar);
        setUploadMessage("");
      }
      setSaveState("saved");
    } catch (saveError) {
      logger.error("Failed to update account details", saveError);
      setSaveState("error");
    }
  };

  const handleUploadButtonClick = () => fileInputRef.current?.click();

  const cachedAccount = accountState.accountData || undefined;
  const queryAccount = data?.account;
  const userDetails: Partial<Account> = queryAccount || cachedAccount || {};
  const hasAccountShellData = Boolean(userDetails.email || userDetails.userId);

  if (loading && !hasAccountShellData) {
    return (
      <div className="manifest-page">
        <div className="manifest-shell">
          <div className="manifest-panel flex min-h-[50vh] items-center justify-center">
            <div className="flex max-w-md flex-col items-center gap-3 text-center text-sm text-gray500 dark:text-gray400">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent-500 border-t-transparent" />
              <p className="font-semibold">Loading account workspace...</p>
              {accountLoadStalled ? (
                <>
                  <p>This is taking longer than expected.</p>
                  <Button type="button" variant="secondary" onClick={() => refetch()}>
                    Retry
                  </Button>
                </>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error && !hasAccountShellData) {
    return (
      <div className="manifest-page">
        <div className="manifest-shell">
          <div className="manifest-panel px-6 py-10 text-center">
            <p className="text-lg font-semibold text-red-600 dark:text-red-300">Error loading account information</p>
            <p className="mt-3 text-sm text-gray500 dark:text-gray400">We couldn&apos;t retrieve your account workspace.</p>
            <Button type="button" variant="secondary" className="mt-5" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const isRefreshingAccount = loading && hasAccountShellData;
  const displayName =
    userDetails.firstName && userDetails.lastName
      ? `${userDetails.firstName} ${userDetails.lastName}`
      : userDetails.email || "My Account";
  const totalInvested = investments.reduce((sum, investment) => sum + investment.cashAmount + investment.sweatEquityValue, 0);
  const totalEquity = investments.reduce((sum, investment) => sum + investment.equityPercentage, 0);
  const avatarSrc =
    localProfilePreviewUrl ||
    getAvatarUrl({
      profilePictureUrl: userDetails.profilePictureUrl,
      gravatarHash: gravatarInput || userDetails.gravatarHash,
      size: 120,
    });

  const savedSkills = userDetails.skills ?? [];
  const profileDirty =
    formData.email !== (userDetails.email ?? "") ||
    formData.firstName !== (userDetails.firstName ?? "") ||
    formData.lastName !== (userDetails.lastName ?? "") ||
    (gravatarInput || "") !== (userDetails.gravatarHash ?? "") ||
    skills.length !== savedSkills.length ||
    skills.some((skill, index) => skill !== savedSkills[index]);

  const aiKey = aiKeyData?.aiKeyStatus;
  const openMediaStatus = openMedia.status;
  const themeLabel = THEME_OPTIONS.find((option) => option.key === theme)?.label ?? "Match system";

  const settingsSections: SettingsSection[] = [
    {
      id: "profile",
      label: "Profile",
      summary: "How you appear to collaborators, founders and investors across Manifest.",
      icon: "user",
      items: [
        { anchor: "profile-photo", label: "Profile photo", keywords: "picture avatar image upload gravatar" },
        { anchor: "profile-details", label: "Name", keywords: "first last full name" },
        { anchor: "profile-details", label: "Email address", keywords: "email contact" },
        { anchor: "profile-details", label: "Skills", keywords: "expertise tags roles" },
      ],
      content: (
        <>
          <SettingsCard id="profile-photo" title="Photo" description="Shown on your ideas, comments and messages.">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
              <button
                type="button"
                className="settings-avatar-button"
                onClick={handleUploadButtonClick}
                disabled={profilePictureUploading}
                aria-label="Change profile photo"
              >
                <img src={avatarSrc} alt="" />
                <span>{profilePictureUploading ? "Uploading…" : "Change"}</span>
              </button>
              <div className="min-w-0 flex-1 space-y-3">
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="secondary" onClick={handleUploadButtonClick} disabled={profilePictureUploading}>
                    {profilePictureUploading ? "Uploading…" : "Upload photo"}
                  </Button>
                </div>
                <p className="text-xs text-theme-secondary">JPG, PNG or GIF. A square image works best.</p>
                {uploadMessage ? <p className="text-sm text-theme-secondary" role="status">{uploadMessage}</p> : null}
                <details className="group text-sm">
                  <summary className="cursor-pointer select-none text-theme-secondary hover:text-theme-primary">Use a Gravatar instead</summary>
                  <div className="mt-3 max-w-md">
                    <Input
                      type="text"
                      label="Gravatar URL or hash"
                      value={gravatarInput}
                      onChange={handleGravatarChange}
                      placeholder="Paste a Gravatar URL or raw hash"
                    />
                  </div>
                </details>
              </div>
              <input type="file" accept="image/*" ref={fileInputRef} onChange={handleProfilePictureUpload} className="hidden" />
            </div>
          </SettingsCard>

          <SettingsCard id="profile-details" title="Details" description="Your name and skills help the right people find and team up with you.">
            <div className="grid gap-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Input id="firstName" label="First name" type="text" value={formData.firstName} name="firstName" onChange={handleInputChange} autoComplete="given-name" />
                <Input id="lastName" label="Last name" type="text" value={formData.lastName} name="lastName" onChange={handleInputChange} autoComplete="family-name" />
              </div>
              <Input id="email" label="Email" type="email" value={formData.email} name="email" onChange={handleInputChange} autoComplete="email" />
              <SkillsPicker
                availableSkills={skillsData?.availableSkills ?? []}
                label="Skills"
                onChange={setSkills}
                placeholder="Search your skills…"
                value={skills}
              />
            </div>
            <div className="settings-savebar">
              <p className="mr-auto text-sm text-theme-secondary" role="status" aria-live="polite">
                {saveState === "saving"
                  ? "Saving…"
                  : saveState === "error"
                    ? "Couldn't save. Try again."
                    : profileDirty
                      ? "You have unsaved changes"
                      : saveState === "saved"
                        ? "Saved"
                        : ""}
              </p>
              <Button type="button" variant="primary" onClick={handleSaveDetails} disabled={!profileDirty || saveState === "saving"}>
                Save changes
              </Button>
            </div>
          </SettingsCard>
        </>
      ),
    },
    {
      id: "appearance",
      label: "Appearance",
      summary: "Choose how Manifest looks on this device.",
      icon: "palette",
      status: { text: themeLabel, tone: "neutral" },
      items: [{ anchor: "appearance-theme", label: "Theme", keywords: "dark mode light mode system colors appearance" }],
      content: (
        <SettingsCard id="appearance-theme" title="Theme" description="Match system follows your device's light or dark setting.">
          <div className="settings-theme-grid" role="radiogroup" aria-label="Theme">
            {THEME_OPTIONS.map((option) => (
              <button
                key={option.key}
                type="button"
                role="radio"
                aria-checked={theme === option.key}
                className="settings-theme-option"
                onClick={() => setTheme(option.key)}
              >
                <span className="settings-theme-preview">
                  {option.key === "system" ? (
                    <>
                      <MockUi mode="light" />
                      <MockUi mode="dark" half />
                    </>
                  ) : (
                    <MockUi mode={option.key} />
                  )}
                </span>
                <span className="settings-theme-label">
                  <span className="settings-radio" aria-hidden="true" />
                  {option.label}
                </span>
              </button>
            ))}
          </div>
        </SettingsCard>
      ),
    },
    {
      id: "connections",
      label: "AI & sign-in",
      summary: "The OpenAI key Manifest uses for generation, and the account you sign in with.",
      icon: "sparkles",
      status: aiKey
        ? aiKey.source === "user"
          ? { text: `OpenAI key ••${aiKey.last4 ?? ""}`, tone: "ok" }
          : { text: "Add your OpenAI key", tone: "warn" }
        : null,
      items: [
        { anchor: "ai-key", label: "OpenAI API key", keywords: "ai key openai byok generation gpt model" },
        { anchor: "open-media", label: "Open Media sign-in", keywords: "login account passkey password two-step 2fa messages pitch shorts" },
      ],
      content: (
        <>
          <SettingsCard
            id="ai-key"
            title="OpenAI key"
            description="Manifest runs on your own OpenAI account, so you only pay OpenAI for what you generate. The key is verified, encrypted and never shown again."
          >
            <AiKeySection />
          </SettingsCard>
          <SettingsCard
            id="open-media"
            title="Sign-in"
            description="One Open Media account signs you in to Manifest and also runs Messages and Pitch Shorts."
          >
            <OpenMediaSection />
          </SettingsCard>
        </>
      ),
    },
    {
      id: "integrations",
      label: "Integrations",
      summary: "Connect the tools and companies you work with. Connected partners show under Key Partners on every canvas.",
      icon: "puzzle",
      status: github?.connected
        ? { text: `GitHub @${github.login ?? ""}`, tone: "ok" }
        : connectedIntegrations > 0
          ? { text: `${connectedIntegrations} connected`, tone: "ok" }
          : null,
      items: [
        { anchor: "github", label: "GitHub", keywords: "github git code connect gh cli plugin" },
        { anchor: "github", label: "Repositories", keywords: "repository repositories repo repos pull requests issues actions ci releases" },
        { anchor: "github", label: "GitHub token", keywords: "token access token personal access token pat oauth sign in with github" },
        { anchor: "integrations", label: "Connected apps", keywords: "integrations connect apps tools google notion slack figma stripe" },
        { anchor: "integrations", label: "Key partners", keywords: "partners suppliers agencies distributors canvas" },
      ],
      content: (
        <>
          <SettingsCard
            id="github"
            title="GitHub"
            description="One connection for everything: the app, ideas turned into repositories, the manifest CLI, your agent's Manifest plugin and voice. Manifest always asks before merging or deleting."
          >
            <GitHubSection />
          </SettingsCard>
          <div id="integrations">
            <IntegrationsSection showHeader={false} />
          </div>
        </>
      ),
    },
    {
      id: "developer",
      label: "Developer",
      summary: "API keys for the Manifest GraphQL API, scripts and agents.",
      icon: "code",
      items: [{ anchor: "api-access", label: "API keys", keywords: "developer graphql token automation api access docs" }],
      content: (
        <div id="api-access">
          <ApiAccessSection />
        </div>
      ),
    },
    {
      id: "data",
      label: "Data & storage",
      summary: "Where your ideas live, and moving them in or out of Manifest.",
      icon: "database",
      items: [
        { anchor: "storage", label: "Vault folder", keywords: "storage icloud dropbox markdown files offline sync obsidian" },
        { anchor: "import-export", label: "Import and export ideas", keywords: "backup download apple notes google keep" },
      ],
      content: (
        <>
          <StorageSection />
          <SettingsCard
            id="import-export"
            title="Import and export"
            description="Bring ideas in from Apple Notes or Google Keep, or download your workspace as a backup."
          >
            <Button type="button" variant="secondary" onClick={() => setIsImportExportOpen(true)} data-testid="import-export-button">
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-1m-4-8-4-4m0 0L8 8m4-4v12" />
              </svg>
              Import / Export Ideas
            </Button>
          </SettingsCard>
        </>
      ),
    },
    {
      id: "privacy",
      label: "Privacy & security",
      summary: "Where you're signed in, how long data is kept, and deleting your account.",
      icon: "shield",
      status: openMediaStatus?.linked && openMediaStatus.needsReconnect ? { text: "Reconnect Open Media", tone: "warn" } : null,
      items: [
        { anchor: "sessions", label: "Signed-in devices", keywords: "sessions log out sign out revoke security" },
        { anchor: "privacy-controls", label: "Privacy choices", keywords: "consent analytics cookies tracking outreach" },
        { anchor: "privacy-controls", label: "Data retention", keywords: "keep retention gdpr export data" },
        { anchor: "delete-account", label: "Delete account", keywords: "remove close erase account deletion" },
      ],
      content: (
        <>
          <SettingsCard
            id="sessions"
            title="Signed-in devices"
            description="Sign out of devices you don't recognise. Passkeys, passwords and two-step verification are managed in Open Media."
          >
            <SecuritySettingsPanel />
          </SettingsCard>
          <SettingsCard id="privacy-controls" title="Privacy choices" description="What Manifest may collect beyond the essentials, and how long data is kept.">
            <PrivacyControlsPanel accountEmail={userDetails.email} parts={["consent", "retention"]} embedded />
          </SettingsCard>
          <SettingsCard id="delete-account" title="Delete account" tone="danger">
            <PrivacyControlsPanel accountEmail={userDetails.email} parts={["deletion"]} embedded />
          </SettingsCard>
        </>
      ),
    },
    {
      id: "feedback",
      label: "Feedback",
      summary: "Tell us how Manifest is working for you.",
      icon: "chat",
      items: [{ anchor: "feedback-survey", label: "Product feedback survey", keywords: "survey feedback nps help" }],
      content: (
        <>
          <div id="feedback-survey">
            <ProductFeedbackSurveyCard variant="desktop" />
          </div>
          <SurveyInsightsPanel variant="desktop" />
        </>
      ),
    },
  ];

  return (
    <div className="manifest-page">
      <div className="manifest-page-shell">
        <section className="manifest-page-header">
          <div className="grid gap-6 xl:grid-cols-[1fr_1fr] xl:items-center">
            <div className="flex min-w-0 items-start gap-4">
              <img
                src={avatarSrc}
                alt="Profile"
                className="h-14 w-14 shrink-0 rounded-lg border border-stone200 object-cover shadow-none dark:border-neutral700"
              />
              <div className="min-w-0">
                <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Account</p>
                <h1 className="mt-2 manifest-page-title text-neutral900 dark:text-white">{displayName}</h1>
                <p className="mt-2 break-words text-sm leading-6 text-gray500 dark:text-gray400">{userDetails.email}</p>
                {isRefreshingAccount ? (
                  <p className="mt-2 text-xs font-semibold uppercase tracking-[0.14em] text-gray400 dark:text-gray500">
                    Refreshing account data...
                  </p>
                ) : null}

              </div>
            </div>

            {activeTab === "portfolio" ? (
            <div className="grid gap-3 grid-cols-3">
              <div className="manifest-card px-4 py-4">
                <p className="text-[0.68rem] font-medium text-gray500 dark:text-gray400">Investments</p>
                <p className="mt-2 text-2xl font-semibold text-neutral900 dark:text-white">{investments.length}</p>
              </div>
              <div className="manifest-card px-4 py-4">
                <p className="text-[0.68rem] font-medium text-gray500 dark:text-gray400">Committed capital</p>
                <p className="mt-2 text-2xl font-semibold text-neutral900 dark:text-white">${totalInvested.toLocaleString()}</p>
              </div>
              <div className="manifest-card px-4 py-4">
                <p className="text-[0.68rem] font-medium text-gray500 dark:text-gray400">Equity stake</p>
                <p className="mt-2 text-2xl font-semibold text-neutral900 dark:text-white">{totalEquity.toFixed(2)}%</p>
              </div>
            </div>
            ) : null}
          </div>
        </section>

        <div className="flex gap-2 border-b border-theme-primary pb-2">
          <button
            aria-pressed={activeTab === "portfolio"}
            onClick={() => setActiveTab("portfolio")}
            className={`rounded-lg px-3 py-2.5 text-sm font-semibold transition-all ${
              activeTab === "portfolio"
                ? "bg-theme-tertiary text-theme-primary"
                : "text-neutral700 hover:bg-stone50 dark:text-gray300 dark:hover:bg-neutral800 dark:hover:text-white"
            }`}
          >
            My Investments
          </button>
          <button
            aria-pressed={activeTab === "settings"}
            onClick={() => setActiveTab("settings")}
            className={`rounded-lg px-3 py-2.5 text-sm font-semibold transition-all ${
              activeTab === "settings"
                ? "bg-theme-tertiary text-theme-primary"
                : "text-neutral700 hover:bg-stone50 dark:text-gray300 dark:hover:bg-neutral800 dark:hover:text-white"
            }`}
          >
            Settings
          </button>
        </div>

        {activeTab === "portfolio" ? (
          <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
            <SectionCard
              eyebrow="Portfolio"
              title="Investment activity"
              description="Review startup positions, equity exposure, and recent investment records."
            >
              {portfolioError ? (
                <div className="manifest-card px-5 py-8 text-center">
                  <p className="text-base font-semibold text-red-600 dark:text-red-300">Failed to load portfolio</p>
                  <p className="mt-2 text-sm text-gray500 dark:text-gray400">We couldn&apos;t retrieve your investment data.</p>
                  <Button type="button" variant="secondary" className="mt-4" onClick={() => window.location.reload()}>
                    Retry
                  </Button>
                </div>
              ) : portfolioLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((item) => (
                    <div key={item} className="manifest-card animate-pulse px-5 py-5">
                      <div className="h-4 w-32 rounded bg-gray200 dark:bg-neutral700" />
                      <div className="mt-3 h-4 w-full rounded bg-gray200 dark:bg-neutral700" />
                      <div className="mt-2 h-4 w-2/3 rounded bg-gray200 dark:bg-neutral700" />
                    </div>
                  ))}
                </div>
              ) : investments.length === 0 ? (
                <div className="manifest-card px-6 py-10 text-center">
                  <svg className="mx-auto h-14 w-14 text-gray400 dark:text-gray500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M19 21V5a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v5m-4 0h4" />
                  </svg>
                  <h2 className="mt-4 text-xl font-semibold text-neutral900 dark:text-white">No investments yet</h2>
                  <p className="mt-2 break-words text-sm leading-6 text-gray500 dark:text-gray400">Start investing in ideas to build your founder portfolio.</p>
                  <Link
                    to="/pitch-reels"
                    className="mt-5 inline-flex items-center rounded-2xl bg-neutral900 px-5 py-3 text-sm font-semibold text-white shadow-none hover:bg-stone50 dark:hover:bg-neutral800 dark:bg-white dark:text-neutral900"
                  >
                    Open Pitch Reels
                  </Link>
                </div>
              ) : (
                <div className="space-y-4">
                  {investments.map((investment) => (
                    <Link
                      key={investment.investmentId}
                      to={`/ideas/${investment.ideaId}`}
                      className="manifest-card block px-5 py-5 transition-all hover:bg-stone50 dark:hover:bg-neutral800"
                    >
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-3">
                            <h3 className="text-lg font-semibold text-neutral900 dark:text-white">{investment.ideaTitle}</h3>
                            <span
                              className={`rounded-full px-3 py-1 text-[0.72rem] font-medium ${
                                investment.status === "confirmed"
                                  ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-200"
                                  : investment.status === "pending"
                                    ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-200"
                                    : "bg-stone100 text-gray500 dark:bg-neutral800 dark:text-gray400"
                              }`}
                            >
                              {investment.status}
                            </span>
                          </div>
                          {investment.ideaDescription ? (
                            <p className="mt-3 line-clamp-2 text-sm leading-7 text-gray500 dark:text-gray400">
                              {investment.ideaDescription}
                            </p>
                          ) : null}
                        </div>
                        <div className="grid gap-3 text-sm sm:grid-cols-3 lg:min-w-[20rem]">
                          <div>
                            <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Cash</p>
                            <p className="mt-2 font-semibold text-neutral900 dark:text-white">${investment.cashAmount.toLocaleString()}</p>
                          </div>
                          <div>
                            <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Sweat Equity</p>
                            <p className="mt-2 font-semibold text-neutral900 dark:text-white">${investment.sweatEquityValue.toLocaleString()}</p>
                          </div>
                          <div>
                            <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Stake</p>
                            <p className="mt-2 font-semibold text-neutral900 dark:text-white">{investment.equityPercentage.toFixed(2)}%</p>
                          </div>
                        </div>
                      </div>
                      <p className="mt-4 text-xs font-medium uppercase tracking-[0.14em] text-gray400 dark:text-gray500">
                        Invested on {new Date(investment.createdAt).toLocaleDateString()}
                      </p>
                    </Link>
                  ))}
                </div>
              )}
            </SectionCard>

            <div className="space-y-6">
              <SectionCard
                eyebrow="Summary"
                title="Portfolio overview"
                description="A quick view of your exposure across the ideas you have backed."
              >
                {portfolioLoading ? (
                  <div className="grid gap-3">
                    {[1, 2, 3].map((item) => (
                      <div key={item} className="manifest-card h-24 animate-pulse" />
                    ))}
                  </div>
                ) : (
                  <div className="grid gap-3">
                    <div className="manifest-card px-5 py-4">
                      <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Total investments</p>
                      <p className="mt-2 text-3xl font-semibold text-neutral900 dark:text-white">{investments.length}</p>
                    </div>
                    <div className="manifest-card px-5 py-4">
                      <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Total value invested</p>
                      <p className="mt-2 text-3xl font-semibold text-neutral900 dark:text-white">${totalInvested.toLocaleString()}</p>
                    </div>
                    <div className="manifest-card px-5 py-4">
                      <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Total equity owned</p>
                      <p className="mt-2 text-3xl font-semibold text-neutral900 dark:text-white">{totalEquity.toFixed(2)}%</p>
                    </div>
                  </div>
                )}
              </SectionCard>

              <SectionCard
                eyebrow="Planning"
                title="What to do next"
                description="Use Pitch Reels to scan public startup narratives quickly, or open an existing workspace to review the supporting documents."
              >
                <div className="space-y-3">
                  <Link
                    to="/pitch-reels"
                    className="manifest-card flex items-center justify-between px-5 py-4 text-neutral900 transition-all hover:bg-stone50 dark:hover:bg-neutral800 dark:text-white"
                  >
                    <div>
                      <p className="text-sm font-semibold">Open Pitch Reels</p>
                      <p className="mt-1 text-sm text-gray500 dark:text-gray400">Browse startup pitches in a faster, more immersive view.</p>
                    </div>
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="m9 5 7 7-7 7" />
                    </svg>
                  </Link>
                  <Link
                    to="/ideas"
                    className="manifest-card flex items-center justify-between px-5 py-4 text-neutral900 transition-all hover:bg-stone50 dark:hover:bg-neutral800 dark:text-white"
                  >
                    <div>
                      <p className="text-sm font-semibold">Open founder workspace</p>
                      <p className="mt-1 text-sm text-gray500 dark:text-gray400">Return to your notes, documents, and collaboration tools.</p>
                    </div>
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="m9 5 7 7-7 7" />
                    </svg>
                  </Link>
                </div>
              </SectionCard>
            </div>
          </div>
        ) : (
          <SettingsView
            sections={settingsSections}
            activeId={activeSection}
            onSelect={selectSection}
            focusAnchor={focusAnchor}
            onFocusHandled={clearFocusAnchor}
          />
        )}
      </div>

      <ImportExportModal isOpen={isImportExportOpen} onClose={() => setIsImportExportOpen(false)} />
    </div>
  );
};

export default AccountPage;
