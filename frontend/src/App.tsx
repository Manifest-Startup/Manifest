import { isVaultMode } from "features/vault/mode";
import React, { Suspense, lazy, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import { useReactiveVar } from "@apollo/client/react";

import { ThemeProvider } from "context/ThemeContext";
import { useAccountSync } from "features/account/hooks/useAccountSync";
import { useAuthSync } from "features/auth/hooks/useAuthSync";
import ErrorBoundary from "features/core/ErrorBoundary";
import { userVar } from "features/core/apollo/localState";
import { createLogger } from "features/core/logError";
import AppFooter from "features/navigation/components/AppFooter";
import AppShortcuts from "features/navigation/components/AppShortcuts";
import NavigationBar from "features/navigation/components/NavigationBar";
import MessageBanner from "features/notifications/components/MessageBanner";
import AiKeyRequiredNotice from "features/ai/AiKeyRequiredNotice";
import { MessageProvider } from "features/notifications/context/MessageContext";
import { detectDevice } from "features/ios/utils/deviceDetection";
import { getViewMode, shouldShowIOSView } from "features/ios/utils/viewMode";
import { loadPitchReelsPage } from "features/pitch-reels/loadPitchReelsPage";
import PrivacyConsentBanner from "features/privacy/PrivacyConsentBanner";
// The landing page and the auth gate are tiny and on almost every first paint:
// ship them in the boot chunk so "/" and signed-in routes skip a round trip.
import PitchPage from "features/marketing/components/PitchPage";
import PrivateRoute from "features/auth/components/PrivateRoute";
import { usePrivacyConsent } from "features/privacy/PrivacyConsentContext";
import ManifestLogo from "features/common-ui/ManifestLogo";

const LoginPage = lazy(() => import("features/auth/components/LoginPage"));
const VaultSettingsPage = lazy(() => import("features/vault/StorageSection"));
const GuestSessionBanner = lazy(() => import("features/auth/components/GuestSessionBanner"));
const loadIdeasPage = () => import("features/ideas/components/IdeasPage");
const IdeasPage = lazy(loadIdeasPage);
if (typeof window !== "undefined" && window.location.pathname.startsWith("/ideas")) {
  // Deep links into the workspace: fetch the page and the idea view now,
  // instead of after auth sync and the route render.
  void loadIdeasPage();
  void import("features/ideas/components/Idea");
}
const IdeaQualificationPage = lazy(() => import("features/ideas/components/IdeaQualificationPage"));
const PitchReelsPage = lazy(loadPitchReelsPage);
const MessagesPage = lazy(() => import("features/messaging/components/MessagesPage"));
const LearnMorePage = lazy(() => import("features/marketing/components/LearnMorePage"));
const AccountPage = lazy(() => import("features/account/components/AccountPage"));
const BillingDashboardPage = lazy(() => import("features/account/components/BillingDashboardPage"));
const AdminCostDashboardPage = lazy(() => import("features/admin/components/AdminCostDashboardPage"));
const AppIOS = lazy(() => import("features/ios/AppIOS"));
const PullToRefresh = lazy(() => import("features/core/refresh/PullToRefresh"));
const FloatingVoiceButton = lazy(() => import("features/voice/FloatingVoiceButton"));
const ProductFeedbackSurveyPrompt = lazy(() => import("features/feedback/ProductFeedbackSurveyPrompt"));
const ResearchSurveyPage = lazy(() => import("features/survey/ResearchSurveyPage"));
const ProductFeedbackSurveyPage = lazy(() => import("features/survey/ProductFeedbackSurveyPage"));
const DocsHubPage = lazy(() => import("features/docs/DocsHubPage"));
const UserGuidePage = lazy(() => import("features/docs/UserGuidePage"));
const ApiDocsPage = lazy(() => import("features/docs/ApiDocsPage"));
const LegalDocumentPage = lazy(() => import("features/docs/LegalDocumentPage"));
const CompanyInfoPage = lazy(() => import("features/docs/CompanyInfoPage"));

const logger = createLogger("App");

const RouteFallback: React.FC = () => (
  <div className="manifest-page">
    <div className="manifest-shell">
      <div className="manifest-panel flex min-h-[42vh] flex-col items-center justify-center gap-4 px-6 text-center">
        <ManifestLogo size={56} />
        <div>
          <p className="text-[0.72rem] font-bold uppercase tracking-[0.18em] text-gray500 dark:text-gray400">
            Manifest
          </p>
          <p className="mt-1 text-lg font-semibold text-neutral900 dark:text-white">
            Loading workspace...
          </p>
        </div>
      </div>
    </div>
  </div>
);

const IdeaDetailRedirect: React.FC = () => {
  const { idea_id } = useParams();

  if (!idea_id) {
    return <Navigate to="/ideas" replace />;
  }

  return <Navigate to={`/ideas/${idea_id}/description`} replace />;
};

const App = () => {
  useAuthSync();
  useAccountSync();
  const location = useLocation();
  const { consent: privacyConsent, loading: privacyLoading } = usePrivacyConsent();

  const { isLoggedIn, isGuest } = useReactiveVar(userVar);
  // Reels share the standard navigation, with their own scrolling content.
  const isImmersiveShorts =
    location.pathname.startsWith("/pitch-reels") ||
    location.pathname.startsWith("/shorts");
  const isSurveyFlow = location.pathname === "/research" || location.pathname === "/feedback/survey";
  const isLandingPage = location.pathname === "/" || location.pathname === "/home";
  const hideTopChrome = isSurveyFlow || isLandingPage;
  const showPrivacyBanner = !hideTopChrome && !privacyLoading && !privacyConsent.hasStoredPreference;
  const [viewMode, setViewMode] = useState<"desktop" | "ios">(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const urlView = urlParams.get("view");

    if (urlView === "ios") {
      if (typeof window !== "undefined") {
        localStorage.setItem("manifest_view_mode", "ios");
      }
      return "ios";
    }

    if (urlView === "desktop") {
      if (typeof window !== "undefined") {
        localStorage.setItem("manifest_view_mode", "desktop");
      }
      return "desktop";
    }

    const mode = getViewMode();
    const device = detectDevice();
    return shouldShowIOSView(mode, device.isIOS) ? "ios" : "desktop";
  });

  useEffect(() => {
    const handleStorageChange = () => {
      const mode = getViewMode();
      const device = detectDevice();
      setViewMode(shouldShowIOSView(mode, device.isIOS) ? "ios" : "desktop");
    };

    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, []);

  logger.log("Rendering App component", { viewMode });

  if (viewMode === "ios") {
    return (
      <ThemeProvider>
        <Suspense fallback={<RouteFallback />}>
          <AppIOS />
        </Suspense>
        {isLoggedIn ? (
          <Suspense fallback={null}>
            <PullToRefresh />
          </Suspense>
        ) : null}
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider>
      <MessageProvider>
        <div className="manifest-app-frame flex flex-col">
          {hideTopChrome ? null : <NavigationBar />}
          <MessageBanner />
          <AiKeyRequiredNotice />
          {hideTopChrome ? null : (
            <Suspense fallback={null}>
              <GuestSessionBanner />
            </Suspense>
          )}
          {hideTopChrome ? null : <PrivacyConsentBanner />}
          <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <div
              className={`min-h-0 flex-1 ${isImmersiveShorts ? "overflow-hidden" : "overflow-y-auto overflow-x-hidden"} ${
                showPrivacyBanner ? "pb-40 sm:pb-36" : ""
              } [-webkit-overflow-scrolling:touch]`}
            >
              <ErrorBoundary>
                <Suspense fallback={<RouteFallback />}>
                  <Routes>
                    <Route path="/" element={<PitchPage />} />
                    <Route path="/home" element={<PitchPage />} />
                    <Route path="/research" element={<ResearchSurveyPage />} />
                    <Route path="/feedback/survey" element={<PrivateRoute><ProductFeedbackSurveyPage /></PrivateRoute>} />
                    <Route path="/ideas" element={<PrivateRoute><IdeasPage /></PrivateRoute>} />
                    <Route path="/ideas/qualify" element={<PrivateRoute><IdeaQualificationPage /></PrivateRoute>} />
                    <Route path="/ideas/:idea_id" element={<PrivateRoute><IdeaDetailRedirect /></PrivateRoute>} />
                    <Route path="/ideas/:idea_id/:ideaAspect" element={<PrivateRoute><IdeasPage /></PrivateRoute>} />
                    <Route
                      path="/account"
                      element={isVaultMode() ? <VaultSettingsPage /> : <PrivateRoute><AccountPage /></PrivateRoute>}
                    />
                    <Route path="/account/billing" element={<PrivateRoute><BillingDashboardPage /></PrivateRoute>} />
                    <Route path="/admin/cost" element={<PrivateRoute><AdminCostDashboardPage /></PrivateRoute>} />
                    <Route path="/login" element={isLoggedIn && !isGuest ? <Navigate to="/ideas" replace /> : <LoginPage />} />
                    {/* Sign-up, password reset and MFA screens were removed (sign-in is Open Media only); old links land on /login. */}
                    <Route path="/signup" element={<Navigate to="/login" replace />} />
                    <Route path="/auth" element={<Navigate to="/login" replace />} />
                    <Route path="/auth/forgot-password" element={<Navigate to="/login" replace />} />
                    <Route path="/auth/reset-password" element={<Navigate to="/login" replace />} />
                    <Route path="/learn-more" element={<LearnMorePage />} />
                    <Route path="/messages/:conversationId" element={<PrivateRoute><MessagesPage /></PrivateRoute>} />
                    <Route path="/messages" element={<PrivateRoute><MessagesPage /></PrivateRoute>} />
                    {/* Pitch Reels: canonical URL is /pitch-reels (regression #25 — the user-facing label has always been "Pitch Reels"; /shorts was an internal name). The legacy paths redirect so external bookmarks keep working. */}
                    <Route path="/pitch-reels" element={<PrivateRoute><PitchReelsPage /></PrivateRoute>} />
                    <Route path="/shorts" element={<Navigate to="/pitch-reels" replace />} />
                    <Route path="/discover" element={<Navigate to="/pitch-reels" replace />} />
                    <Route path="/pitch-shorts" element={<Navigate to="/pitch-reels" replace />} />
                    <Route path="/portfolio" element={<Navigate to="/account" replace />} />
                    <Route path="/docs" element={<DocsHubPage />} />
                    <Route path="/docs/guide" element={<UserGuidePage />} />
                    <Route path="/docs/api" element={<ApiDocsPage />} />
                    <Route path="/legal/terms" element={<LegalDocumentPage />} />
                    <Route path="/legal/privacy" element={<LegalDocumentPage />} />
                    <Route path="/privacy" element={<Navigate to="/legal/privacy" replace />} />
                    <Route path="/about" element={<CompanyInfoPage />} />
                    <Route path="/contact" element={<CompanyInfoPage />} />
                    <Route path="/developers" element={<Navigate to="/docs/api" replace />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </Suspense>
              </ErrorBoundary>
            </div>
          </main>
          {hideTopChrome ? null : <AppFooter />}
          <AppShortcuts signedIn={Boolean(isLoggedIn)} />
          {isLoggedIn ? (
            <Suspense fallback={null}>
              <PullToRefresh />
            </Suspense>
          ) : null}
          {!hideTopChrome && isLoggedIn ? (
            <Suspense fallback={null}>
              <FloatingVoiceButton />
            </Suspense>
          ) : null}
          {isLoggedIn ? (
            <Suspense fallback={null}>
              <ProductFeedbackSurveyPrompt immersiveShorts={isImmersiveShorts} />
            </Suspense>
          ) : null}
        </div>
      </MessageProvider>
    </ThemeProvider>
  );
};

export default App;
