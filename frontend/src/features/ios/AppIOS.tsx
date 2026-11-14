import React from "react";
import { Routes, Route, Navigate, useLocation, useParams } from "react-router-dom";
import { useAuthSync } from "features/auth/hooks/useAuthSync";
import { useAccountSync } from "features/account/hooks/useAccountSync";
import IOSNavigationBar from "./components/IOSNavigationBar";
import IOSTabBar from "./components/IOSTabBar";
import IOSViewToggle from "./components/IOSViewToggle";
import IOSIdeasPage from "./pages/IOSIdeasPage";
import IOSAuthForm from "./pages/IOSAuthForm";
import IOSAccountPage from "./pages/IOSAccountPage";
import PitchPage from "features/marketing/components/PitchPage";
import LearnMorePage from "features/marketing/components/LearnMorePage";
import GuestSessionBanner from "features/auth/components/GuestSessionBanner";
import PrivateRoute from "features/auth/components/PrivateRoute";
import { MessageProvider } from "features/notifications/context/MessageContext";
import MessageBanner from "features/notifications/components/MessageBanner";
import { createLogger } from "features/core/logError";
import { useReactiveVar } from "@apollo/client/react";
import { userVar } from "features/core/apollo/localState";
import ErrorBoundary from "features/core/ErrorBoundary";
import CompanyInfoPage from "features/docs/CompanyInfoPage";
import LegalDocumentPage from "features/docs/LegalDocumentPage";
import PortfolioPage from "features/investments/components/PortfolioPage";
import { FloatingVoiceButton } from "features/voice";
import ProductFeedbackSurveyPrompt from "features/feedback/ProductFeedbackSurveyPrompt";
import ResearchSurveyPage from "features/survey/ResearchSurveyPage";
import ProductFeedbackSurveyPage from "features/survey/ProductFeedbackSurveyPage";
import PitchShortsPage from "features/pitchshorts/PitchShortsPage";
import MessagesPage from "features/messaging/components/MessagesPage";
import PrivacyConsentBanner from "features/privacy/PrivacyConsentBanner";

const logger = createLogger('AppIOS');

const IdeaDetailRedirect: React.FC = () => {
  const { idea_id } = useParams();

  if (!idea_id) {
    return <Navigate to="/ideas" replace />;
  }

  return <Navigate to={`/ideas/${idea_id}/description`} replace />;
};

/**
 * iOS-styled App component with native iOS design patterns
 */
const AppIOS: React.FC = () => {
  useAuthSync();
  useAccountSync();
  const location = useLocation();

  const { isLoggedIn } = useReactiveVar(userVar);
  // Match #25: accept both the canonical `/pitch-reels` and legacy `/shorts`.
  const isImmersiveShorts =
    location.pathname.startsWith("/pitch-reels") || location.pathname.startsWith("/shorts");
  const isSurveyFlow = location.pathname === "/research" || location.pathname === "/feedback/survey";
  const isLandingPage = location.pathname === "/" || location.pathname === "/home";
  const hideIosChrome = isImmersiveShorts || isSurveyFlow || isLandingPage;

  logger.log("Rendering iOS App component");
  return (
    <MessageProvider>
      <div className="ios-app min-h-screen min-h-[100dvh] bg-gray-50 dark:bg-neutral900 transition-colors">
        {hideIosChrome ? null : <IOSNavigationBar />}
        <MessageBanner />
        {hideIosChrome ? null : <GuestSessionBanner />}
        {hideIosChrome ? null : <PrivacyConsentBanner />}
        <div className="ios-content-area">
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<PitchPage />} />
              <Route path="/home" element={<PitchPage />} />
              <Route path="/research" element={<ResearchSurveyPage />} />
              <Route path="/feedback/survey" element={<PrivateRoute><ProductFeedbackSurveyPage /></PrivateRoute>} />
              <Route path="/ideas" element={<PrivateRoute><IOSIdeasPage /></PrivateRoute>} />
              <Route path="/ideas/:idea_id" element={<PrivateRoute><IdeaDetailRedirect /></PrivateRoute>} />
              <Route path="/ideas/:idea_id/:ideaAspect" element={<PrivateRoute><IOSIdeasPage /></PrivateRoute>} />
              <Route path="/account" element={<PrivateRoute><IOSAccountPage /></PrivateRoute>} />
              <Route path="/login" element={<Navigate to="/auth" replace />} />
              <Route path="/signup" element={<Navigate to="/auth" replace />} />
              <Route path="/auth" element={isLoggedIn ? <Navigate to="/ideas" replace /> : <IOSAuthForm />} />
              <Route path="/learn-more" element={<LearnMorePage />} />
              <Route path="/legal/terms" element={<LegalDocumentPage />} />
              <Route path="/legal/privacy" element={<LegalDocumentPage />} />
              <Route path="/privacy" element={<Navigate to="/legal/privacy" replace />} />
              <Route path="/about" element={<CompanyInfoPage />} />
              <Route path="/contact" element={<CompanyInfoPage />} />
              <Route path="/messages/:conversationId" element={<PrivateRoute><MessagesPage /></PrivateRoute>} />
              <Route path="/messages" element={<PrivateRoute><MessagesPage /></PrivateRoute>} />
              <Route path="/pitch-reels" element={<PrivateRoute><PitchShortsPage /></PrivateRoute>} />
              <Route path="/shorts" element={<Navigate to="/pitch-reels" replace />} />
              <Route path="/discover" element={<Navigate to="/pitch-reels" replace />} />
              <Route path="/pitch-shorts" element={<Navigate to="/pitch-reels" replace />} />
              <Route path="/portfolio" element={<PrivateRoute><PortfolioPage /></PrivateRoute>} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </ErrorBoundary>
        </div>
        {hideIosChrome ? null : <IOSTabBar />}
        <IOSViewToggle />
        {hideIosChrome ? null : <FloatingVoiceButton />}
        {isLoggedIn ? <ProductFeedbackSurveyPrompt immersiveShorts={isImmersiveShorts} /> : null}
      </div>
    </MessageProvider>
  );
};

export default AppIOS;
