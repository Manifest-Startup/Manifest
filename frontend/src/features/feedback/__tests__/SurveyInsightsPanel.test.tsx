import React from "react";
import { MockedProvider } from "@apollo/client/testing/react";
import { render, screen, waitFor } from "@testing-library/react";

import SurveyInsightsPanel from "../SurveyInsightsPanel";
import { GET_SURVEY_INSIGHTS } from "features/core/apollo/queries";

jest.mock("features/notifications/context/MessageContext", () => ({
  useMessage: () => ({
    setMessage: jest.fn(),
    clearMessage: jest.fn(),
    message: { text: null, type: "info" },
  }),
}));

const surveyInsightsMock = {
  request: {
    query: GET_SURVEY_INSIGHTS,
    variables: { windowDays: 90 },
  },
  result: {
    data: {
      surveyInsights: {
        generatedAt: "2026-04-05T12:00:00Z",
        windowDays: 90,
        totalResponses: 22,
        researchResponses: 14,
        productFeedbackResponses: 8,
        researchSignupIntentAvg: 4.1,
        researchFollowUpRate: 42.9,
        productPmfVeryDisappointedPct: 37.5,
        productNpsScore: 18,
        productProgressAvg: 3.7,
        productDeliverableAvg: 3.9,
        productSatisfactionAvg: 3.9,
        productEaseAvg: 3.5,
        productSatisfactionTopboxPct: 62.5,
        productAiQualityAvg: 4.2,
        topResearchRoles: [{ label: "Founder (building a company)", count: 8, percentage: 57.1 }],
        topResearchValueProps: [{ label: "Investor- or share-ready outputs without starting from scratch", count: 6, percentage: 42.9 }],
        topResearchBarriers: [{ label: "Doing market research or finding comparable companies", count: 5, percentage: 35.7 }],
        topResearchFirstOutputs: [{ label: "A market / comparable research brief", count: 7, percentage: 50 }],
        topResearchTrustSignals: [{ label: "Citations or links behind claims and research", count: 6, percentage: 42.9 }],
        topProductBenefits: [{ label: "It gives shape to rough ideas faster", count: 4, percentage: 50 }],
        topProductTasks: [{ label: "Generate or refine documents (deck, PRD, canvas, patent, etc.)", count: 5, percentage: 62.5 }],
        topActionThemes: [
          { theme: "Research credibility", count: 4 },
          { theme: "Onboarding clarity", count: 3 },
        ],
      },
    },
  },
};

const emptyInsightsMock = {
  request: {
    query: GET_SURVEY_INSIGHTS,
    variables: { windowDays: 90 },
  },
  result: {
    data: {
      surveyInsights: {
        generatedAt: "2026-04-05T12:00:00Z",
        windowDays: 90,
        totalResponses: 0,
        researchResponses: 0,
        productFeedbackResponses: 0,
        researchSignupIntentAvg: null,
        researchFollowUpRate: null,
        productPmfVeryDisappointedPct: null,
        productNpsScore: null,
        productProgressAvg: null,
        productDeliverableAvg: null,
        productSatisfactionAvg: null,
        productEaseAvg: null,
        productSatisfactionTopboxPct: null,
        productAiQualityAvg: null,
        topResearchRoles: [],
        topResearchValueProps: [],
        topResearchBarriers: [],
        topResearchFirstOutputs: [],
        topResearchTrustSignals: [],
        topProductBenefits: [],
        topProductTasks: [],
        topActionThemes: [],
      },
    },
  },
};

describe("SurveyInsightsPanel", () => {
  it("renders the desktop survey snapshot with market and product pull cues", async () => {
    render(
      <MockedProvider mocks={[surveyInsightsMock]} addTypename={false}>
        <SurveyInsightsPanel />
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Survey insights")).toBeInTheDocument();
    });

    expect(screen.getByText("22")).toBeInTheDocument();
    expect(screen.getByText("38%")).toBeInTheDocument();
    expect(screen.getByText("+18")).toBeInTheDocument();
    expect(screen.getByText(/Investor- or share-ready outputs/i)).toBeInTheDocument();
    expect(screen.getByText(/Research credibility \(4\)/i)).toBeInTheDocument();
  });

  it("renders a compact iOS layout", async () => {
    render(
      <MockedProvider mocks={[surveyInsightsMock]} addTypename={false}>
        <SurveyInsightsPanel variant="ios" />
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Survey signals")).toBeInTheDocument();
    });

    expect(screen.getByText("22 responses")).toBeInTheDocument();
    expect(screen.getByText(/Top improvement theme:/i)).toBeInTheDocument();
    expect(screen.getByText(/It gives shape to rough ideas faster/i)).toBeInTheDocument();
  });

  it("shows a calm empty state when no survey data exists yet", async () => {
    render(
      <MockedProvider mocks={[emptyInsightsMock]} addTypename={false}>
        <SurveyInsightsPanel />
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/No survey data has landed yet/i)).toBeInTheDocument();
    });
  });
});
