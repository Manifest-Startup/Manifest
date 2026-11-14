import React, { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import Button from "features/common-ui/Button";

import {
  bumpSessionCountIfNeeded,
  dismissFeedbackSurvey,
  hasModalBeenShownThisSession,
  isFeedbackSurveyDismissed,
  markModalShownThisSession,
  PRODUCT_FEEDBACK_VISIT_THRESHOLD,
  readSessionCount,
} from "./productFeedbackSurveyStorage";
import { useSurveyAnalytics } from "./useSurveyAnalytics";

export interface ProductFeedbackSurveyPromptProps {
  /** When true (e.g. `/shorts` fullscreen), do not show the modal; session bump still runs once per browser session. */
  immersiveShorts?: boolean;
}

/**
 * After N logged-in browser sessions, nudges the in-app product feedback survey at `/feedback/survey`.
 */
const ProductFeedbackSurveyPrompt: React.FC<ProductFeedbackSurveyPromptProps> = ({ immersiveShorts = false }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { captureSurvey } = useSurveyAnalytics();
  const [visible, setVisible] = useState(false);
  const immersiveRef = useRef(immersiveShorts);
  immersiveRef.current = immersiveShorts;

  const onSurveyRoute = location.pathname === "/feedback/survey";

  useEffect(() => {
    if (isFeedbackSurveyDismissed() || onSurveyRoute) {
      return;
    }

    bumpSessionCountIfNeeded();
    const count = readSessionCount();

    if (count < PRODUCT_FEEDBACK_VISIT_THRESHOLD || hasModalBeenShownThisSession()) {
      return;
    }

    const t = window.setTimeout(() => {
      if (immersiveRef.current) {
        return;
      }
      markModalShownThisSession();
      setVisible(true);
      captureSurvey("survey_prompt_shown", { track: "b", surface: "modal" });
    }, 2000);

    return () => window.clearTimeout(t);
  }, [immersiveShorts, captureSurvey, onSurveyRoute]);

  useEffect(() => {
    if (immersiveShorts || onSurveyRoute) {
      setVisible(false);
    }
  }, [immersiveShorts, onSurveyRoute]);

  if (!visible) {
    return null;
  }

  const handleOpen = () => {
    dismissFeedbackSurvey();
    captureSurvey("survey_cta_clicked", { track: "b", surface: "modal" });
    setVisible(false);
    navigate("/feedback/survey");
  };

  const handleDismiss = () => {
    dismissFeedbackSurvey();
    captureSurvey("survey_prompt_dismissed", { track: "b", surface: "modal" });
    setVisible(false);
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-end justify-center bg-black/40 px-4 pb-6 pt-16 backdrop-blur-[2px] sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="manifest-feedback-survey-title"
    >
      <div className="w-full max-w-md rounded-lg border border-stone200 bg-white p-6 shadow-[0_24px_80px_-32px_rgba(0,0,0,0.35)] dark:border-neutral700 dark:bg-neutral900">
        <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Product experience</p>
        <h2 id="manifest-feedback-survey-title" className="mt-2 text-xl font-semibold tracking-tight text-neutral900 dark:text-white">
          How is the workspace working for you?
        </h2>
        <p className="mt-3 text-sm leading-7 text-gray500 dark:text-gray400">
          This is the in-product survey (not the visitor discovery flow on the site). A few minutes helps us prioritize fixes and features.
        </p>
        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          <Button type="button" variant="primary" className="flex-1 px-6" onClick={handleOpen}>
            Open survey
          </Button>
          <Button type="button" variant="secondary" className="flex-1 px-6" onClick={handleDismiss}>
            Not now
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ProductFeedbackSurveyPrompt;
