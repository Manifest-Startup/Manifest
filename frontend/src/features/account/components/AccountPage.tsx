import React, { useEffect, useRef, useState } from "react";
import { useApolloClient, useMutation, useQuery, useReactiveVar } from "@apollo/client/react";
import { Link, useSearchParams } from "react-router-dom";

import { useTheme } from "context/ThemeContext";
import Button from "features/common-ui/Button";
import { useFormState, useInputHandlers } from "features/common-ui/hooks/formHooks";
import Input from "features/common-ui/Input";
import { accountVar, userVar } from "features/core/apollo/localState";
import { GET_ACCOUNT, GET_MY_PORTFOLIO, UPDATE_ACCOUNT } from "features/core/apollo/queries";
import { createLogger } from "features/core/logError";
import { useSafeQuery } from "features/common-ui/api/useSafeQuery";
import ImportExportModal from "features/ideas/components/ImportExportModal";
import ProductFeedbackSurveyCard from "features/feedback/ProductFeedbackSurveyCard";
import SurveyInsightsPanel from "features/feedback/SurveyInsightsPanel";

import ApiAccessSection from "./ApiAccessSection";
import AiKeySection from "./AiKeySection";
import { StorageSection } from "features/vault/StorageSection";
import IntegrationsSection from "./IntegrationsSection";
import OpenMediaSection from "./OpenMediaSection";
import PrivacyControlsPanel from "./PrivacyControlsPanel";
import SecuritySettingsPanel from "./SecuritySettingsPanel";
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
    {description ? <p className="mt-2 break-all text-sm leading-6 text-gray500 dark:text-gray400">{description}</p> : null}
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
  const [searchParams] = useSearchParams();
  const focusIntegrationId = searchParams.get("focusIntegration");

  const [activeTab, setActiveTab] = useState<"portfolio" | "settings">(
    focusIntegrationId ? "settings" : "portfolio",
  );
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

  // "/account#ai-key" (from the "Add your key" banner) opens the AI key card.
  useEffect(() => {
    if (window.location.hash !== "#ai-key") return;
    setActiveTab("settings");
    const timer = window.setTimeout(() => {
      document.getElementById("ai-key")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
    return () => window.clearTimeout(timer);
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
    } catch (saveError) {
      logger.error("Failed to update account details", saveError);
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
                <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Account Workspace</p>
                <h1 className="mt-2 manifest-page-title text-neutral900 dark:text-white">{displayName}</h1>
                <p className="mt-2 break-all text-sm leading-6 text-gray500 dark:text-gray400">{userDetails.email}</p>
                {isRefreshingAccount ? (
                  <p className="mt-2 text-xs font-semibold uppercase tracking-[0.14em] text-gray400 dark:text-gray500">
                    Refreshing account data...
                  </p>
                ) : null}

              </div>
            </div>

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
                  <p className="mt-2 break-all text-sm leading-6 text-gray500 dark:text-gray400">Start investing in ideas to build your founder portfolio.</p>
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
          <div className="grid gap-6 xl:grid-cols-2">
            <div className="space-y-6">
              <SectionCard
                eyebrow="Appearance"
                title="Visual preferences"
                description="Choose how Manifest looks to you. Select a theme or sync with your system settings."
              >
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { key: "light", label: "Light", icon: "sun" },
                    { key: "dark", label: "Dark", icon: "moon" },
                    { key: "system", label: "System", icon: "desktop" },
                  ].map((option) => {
                    const selected = theme === option.key;
                    return (
                      <button
                        key={option.key}
                        aria-pressed={selected}
                        type="button"
                        onClick={() => setTheme(option.key as "light" | "dark" | "system")}
                        className={`manifest-card flex flex-col items-center gap-2 px-3 py-3 ${
                          selected ? "border-accent-200 bg-accent-50/80 dark:border-accent-800 dark:bg-accent-900/20" : ""
                        }`}
                      >
                        {option.icon === "sun" ? (
                          <svg className="h-6 w-6 text-amber-500" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M12 2.25a.75.75 0 0 1 .75.75v2.25a.75.75 0 0 1-1.5 0V3a.75.75 0 0 1 .75-.75ZM7.5 12a4.5 4.5 0 1 1 9 0 4.5 4.5 0 0 1-9 0Zm10.334-5.834a.75.75 0 0 0-1.06-1.06l-1.59 1.59a.75.75 0 0 0 1.06 1.061l1.59-1.59ZM21.75 12A.75.75 0 0 1 21 12.75h-2.25a.75.75 0 0 1 0-1.5H21a.75.75 0 0 1 .75.75ZM17.304 16.243a.75.75 0 1 0-1.06 1.06l1.59 1.591a.75.75 0 0 0 1.061-1.06l-1.59-1.59ZM12 18a.75.75 0 0 1 .75.75V21a.75.75 0 0 1-1.5 0v-2.25A.75.75 0 0 1 12 18ZM7.757 17.303a.75.75 0 0 0-1.06-1.06l-1.59 1.59a.75.75 0 1 0 1.06 1.061l1.59-1.59ZM6 12a.75.75 0 0 1-.75.75H3a.75.75 0 0 1 0-1.5h2.25A.75.75 0 0 1 6 12ZM6.697 7.757a.75.75 0 0 0 1.06-1.06L6.167 5.106a.75.75 0 1 0-1.061 1.06l1.591 1.591Z" />
                          </svg>
                        ) : option.icon === "moon" ? (
                          <svg className="h-6 w-6 text-indigo-500" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M9.528 1.718a.75.75 0 0 1 .162.819A8.97 8.97 0 0 0 9 6a9 9 0 0 0 9 9 8.97 8.97 0 0 0 3.463-.69.75.75 0 0 1 .981.98 10.503 10.503 0 0 1-9.694 6.46c-5.799 0-10.5-4.701-10.5-10.5 0-4.368 2.667-8.112 6.46-9.694a.75.75 0 0 1 .818.162Z" />
                          </svg>
                        ) : (
                          <svg className="h-6 w-6 text-gray500 dark:text-gray400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M21 12V6.75A2.25 2.25 0 0 0 18.75 4.5H5.25A2.25 2.25 0 0 0 3 6.75V15a2.25 2.25 0 0 0 2.25 2.25H9l-1.5 2.25h9L15 17.25h3.75A2.25 2.25 0 0 0 21 15V12Z" />
                          </svg>
                        )}
                        <span className={`text-sm font-semibold ${selected ? "text-accent-600 dark:text-accent-200" : "text-neutral900 dark:text-white"}`}>
                          {option.label}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </SectionCard>

              <SectionCard
                eyebrow="Identity"
                title="Profile image and public presence"
                description="Choose the image used across founder workspaces and collaboration surfaces."
              >
                <div className="flex flex-col gap-6 lg:flex-row">
                  <img
                    src={avatarSrc}
                    alt="Profile"
                    className="h-28 w-28 rounded-lg border border-stone200 object-cover shadow-none dark:border-neutral700"
                  />
                  <div className="flex-1 space-y-4">
                    <Input
                      type="text"
                      label="Gravatar URL Or Hash"
                      value={gravatarInput}
                      onChange={handleGravatarChange}
                      placeholder="Paste a Gravatar URL or raw hash"
                    />
                    <input
                      type="file"
                      accept="image/*"
                      ref={fileInputRef}
                      onChange={handleProfilePictureUpload}
                      className="hidden"
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={handleUploadButtonClick}
                      disabled={profilePictureUploading}
                    >
                      {profilePictureUploading ? "Uploading…" : "Upload profile picture"}
                    </Button>
                    {uploadMessage ? <p className="text-sm leading-6 text-gray500 dark:text-gray400">{uploadMessage}</p> : null}
                  </div>
                </div>
              </SectionCard>

              <SectionCard
                eyebrow="User Details"
                title="Account identity"
                description="Keep your founder profile accurate for collaboration, messaging, and investor review."
              >
                <div className="grid gap-4">
                  <Input id="email" label="Email" type="email" value={formData.email} name="email" onChange={handleInputChange} />
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Input id="firstName" label="First Name" type="text" value={formData.firstName} name="firstName" onChange={handleInputChange} />
                    <Input id="lastName" label="Last Name" type="text" value={formData.lastName} name="lastName" onChange={handleInputChange} />
                  </div>
                  <SkillsPicker
                    availableSkills={skillsData?.availableSkills ?? []}
                    label="Your skills"
                    onChange={setSkills}
                    placeholder="Search your skills…"
                    value={skills}
                  />
                  <Button type="button" variant="primary" onClick={handleSaveDetails}>
                    Save Changes
                  </Button>
                </div>
              </SectionCard>
            </div>

            <div className="space-y-6">
              <StorageSection />
              <div id="ai-key">
                <SectionCard
                  eyebrow="AI"
                  title="Your OpenAI key"
                  description="Manifest runs on your own OpenAI account, so you only pay OpenAI for what you generate. The key is verified, encrypted, and never shown again."
                >
                  <AiKeySection />
                </SectionCard>
              </div>
              <div id="open-media">
                <SectionCard
                  eyebrow="Sign-in"
                  title="Signed in with Open Media"
                  description="One account for Manifest and Open Media. Messages and Pitch Shorts run on it too, and your pitch shorts appear in Open Media's clips feed."
                >
                  <OpenMediaSection />
                </SectionCard>
              </div>
              <SurveyInsightsPanel variant="desktop" />
              <ProductFeedbackSurveyCard variant="desktop" />
              <SectionCard
                eyebrow="Security"
                title="Sessions"
                description="Review where you are signed in to Manifest and revoke sessions you no longer trust. Passkeys, passwords and two-step verification are managed in Open Media."
              >
                <SecuritySettingsPanel />
              </SectionCard>

              <IntegrationsSection />
              <ApiAccessSection />

              <SectionCard
                eyebrow="Data Management"
                title="Import and export"
                description="Bring startup ideas in from Apple Notes or Google Keep, or export your workspace for backup."
              >
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setIsImportExportOpen(true)}
                  data-testid="import-export-button"
                >
                  <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-1m-4-8-4-4m0 0L8 8m4-4v12" />
                  </svg>
                  Import / Export Ideas
                </Button>
              </SectionCard>

              <SectionCard
                eyebrow="Privacy"
                title="Retention and account deletion"
                description="Review retention windows, confirm deletion requests, and keep your workspace data lifecycle explicit."
              >
                <PrivacyControlsPanel accountEmail={userDetails.email} />
              </SectionCard>
            </div>
          </div>
        )}
      </div>

      <ImportExportModal isOpen={isImportExportOpen} onClose={() => setIsImportExportOpen(false)} />
    </div>
  );
};

export default AccountPage;
