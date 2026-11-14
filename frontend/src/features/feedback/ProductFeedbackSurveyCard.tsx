import React from "react";
import { Link, useNavigate } from "react-router-dom";

import Button from "features/common-ui/Button";

import { useSurveyAnalytics } from "./useSurveyAnalytics";

interface ProductFeedbackSurveyCardProps {
  /** `ios` uses compact styling for IOSAccountPage */
  variant?: "desktop" | "ios";
}

/**
 * Track B entry point on Account settings (and iOS account).
 */
const ProductFeedbackSurveyCard: React.FC<ProductFeedbackSurveyCardProps> = ({ variant = "desktop" }) => {
  const { captureSurvey } = useSurveyAnalytics();
  const navigate = useNavigate();

  if (variant === "ios") {
    return (
      <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm transition-colors dark:border-neutral700 dark:bg-neutral800">
        <h3 className="mb-2 font-semibold text-gray-900 dark:text-white">Product experience</h3>
        <p className="mb-4 text-sm leading-6 text-gray-500 dark:text-gray-400">
          Different from the marketing-site discovery survey: this flow is only about using Manifest (quality, ease, features).
        </p>
        <Link
          to="/feedback/survey"
          onClick={() => captureSurvey("survey_cta_clicked", { track: "b", surface: "ios_account" })}
          className="block w-full rounded-lg bg-accent-600 py-2.5 text-center text-sm font-medium text-white active:scale-[0.98] transition-transform"
        >
          Open feedback survey
        </Link>
      </div>
    );
  }

  return (
    <section className="manifest-panel p-4 sm:p-5">
      <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Experience</p>
      <h2 className="mt-3 text-[1.35rem] font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">Product experience survey</h2>
      <p className="mt-2 text-sm leading-7 text-gray500 dark:text-gray-400">
        For signed-in users only. This measures how the workspace actually feels — not the same as the visitor discovery survey on the marketing
        site. Responses are saved for the product team.
      </p>
      <div className="mt-5">
        <Button
          type="button"
          variant="primary"
          className="px-6"
          onClick={() => {
            captureSurvey("survey_cta_clicked", { track: "b", surface: "account" });
            navigate("/feedback/survey");
          }}
        >
          Open feedback survey
        </Button>
      </div>
    </section>
  );
};

export default ProductFeedbackSurveyCard;
