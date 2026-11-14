import React from "react";
import { useQuery } from "@apollo/client/react";
import { Link } from "react-router-dom";

import { GET_MY_PORTFOLIO } from "features/core/apollo/queries";
import type { PortfolioItem } from "features/core/apollo/operationTypes";

const PortfolioPage: React.FC = () => {
  const { data, loading, error } = useQuery(GET_MY_PORTFOLIO);

  const investments: PortfolioItem[] = data?.myPortfolio || [];
  const totalInvested = investments.reduce((sum, investment) => sum + investment.cashAmount + investment.sweatEquityValue, 0);
  const totalEquity = investments.reduce((sum, investment) => sum + investment.equityPercentage, 0);

  if (loading) {
    return (
      <div className="manifest-page">
        <div className="manifest-page-shell">
          <section className="manifest-panel px-6 py-6 sm:px-7">
            <div className="animate-pulse space-y-4">
              <div className="h-6 w-40 rounded-full bg-gray200 dark:bg-neutral700" />
              <div className="grid gap-4 md:grid-cols-3">
                {[1, 2, 3].map((item) => (
                  <div className="h-28 rounded-[1.5rem] bg-gray100 dark:bg-neutral800" key={item} />
                ))}
              </div>
              <div className="h-40 rounded-[1.75rem] bg-gray100 dark:bg-neutral800" />
            </div>
          </section>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="manifest-page">
        <div className="manifest-page-shell">
          <section className="manifest-panel px-6 py-10 text-center sm:px-8">
            <p className="text-sm font-semibold text-red-600 dark:text-red-400">Failed to load portfolio</p>
            <button
              onClick={() => window.location.reload()}
              className="mt-4 inline-flex items-center justify-center rounded-2xl bg-gradient-to-br from-neutral900 via-neutral800 to-blue500 px-5 py-3 text-sm font-semibold text-white shadow-professional hover:-translate-y-0.5 dark:from-white dark:via-gray100 dark:to-stone100 dark:text-neutral900"
            >
              Retry
            </button>
          </section>
        </div>
      </div>
    );
  }

  const summaryCards = [
    { label: "Total Investments", value: investments.length.toString(), helper: "Active portfolio positions" },
    { label: "Capital Deployed", value: `$${totalInvested.toLocaleString()}`, helper: "Cash plus sweat equity value" },
    { label: "Equity Exposure", value: `${totalEquity.toFixed(2)}%`, helper: "Combined ownership across ideas" },
  ];

  return (
    <div className="manifest-page">
      <div className="manifest-page-shell gap-8">
        <section className="manifest-page-header overflow-hidden">
          <div className="grid gap-6 px-6 py-8 sm:px-8 sm:py-10 lg:grid-cols-[minmax(0,1fr)_24rem]">
            <div>
              <span className="manifest-kicker">Investor Workspace</span>
              <h1 className="manifest-title mt-5 text-4xl text-neutral900 dark:text-white sm:text-5xl">My Portfolio</h1>
              <p className="manifest-subtitle mt-5 max-w-3xl text-base sm:text-lg">
                Track the ideas you have backed, the capital you have deployed, and the ownership exposure you are building across the Manifest ecosystem.
              </p>
            </div>
            <div className="manifest-panel-muted p-5 sm:p-6">
              <p className="text-[0.72rem] font-bold uppercase tracking-[0.16em] text-gray500 dark:text-gray400">Portfolio Snapshot</p>
              <div className="mt-4 space-y-3">
                {summaryCards.map((card) => (
                  <div className="manifest-card px-4 py-4" key={card.label}>
                    <p className="text-xs font-bold uppercase tracking-[0.14em] text-gray500 dark:text-gray400">{card.label}</p>
                    <p className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">{card.value}</p>
                    <p className="mt-1 text-sm text-gray500 dark:text-gray400">{card.helper}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {investments.length === 0 ? (
          <section className="manifest-panel px-6 py-10 text-center sm:px-8">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-[1.5rem] bg-white/85 shadow-soft dark:bg-neutral800">
              <svg className="h-8 w-8 text-accent-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
            </div>
            <h2 className="mt-5 text-2xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">No investments yet</h2>
            <p className="mt-2 text-sm text-gray500 dark:text-gray400">Start investing in ideas to build your portfolio.</p>
            <Link
              to="/pitch-reels"
              className="mt-5 inline-flex items-center justify-center rounded-2xl bg-gradient-to-br from-neutral900 via-neutral800 to-blue500 px-5 py-3 text-sm font-semibold text-white shadow-professional hover:-translate-y-0.5 dark:from-white dark:via-gray100 dark:to-stone100 dark:text-neutral900"
            >
              Open Pitch Reels
            </Link>
          </section>
        ) : (
          <section className="space-y-4">
            {investments.map((investment) => (
              <Link key={investment.investmentId} to={`/ideas/${investment.ideaId}`} className="block">
                <article className="manifest-panel px-6 py-6 transition-transform hover:-translate-y-0.5 sm:px-7">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-2xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">{investment.ideaTitle}</h3>
                        <span className="manifest-pill">{investment.status}</span>
                      </div>
                      {investment.ideaDescription ? (
                        <p className="mt-3 max-w-3xl text-sm leading-6 text-gray500 dark:text-gray400">{investment.ideaDescription}</p>
                      ) : null}
                    </div>
                    <p className="text-sm font-medium text-gray500 dark:text-gray400">
                      Invested on {new Date(investment.createdAt).toLocaleDateString()}
                    </p>
                  </div>

                  <div className="mt-5 grid gap-3 md:grid-cols-3">
                    <div className="manifest-card px-4 py-4">
                      <p className="text-xs font-bold uppercase tracking-[0.14em] text-gray500 dark:text-gray400">Cash Invested</p>
                      <p className="mt-2 text-lg font-semibold text-neutral900 dark:text-white">${investment.cashAmount.toLocaleString()}</p>
                    </div>
                    <div className="manifest-card px-4 py-4">
                      <p className="text-xs font-bold uppercase tracking-[0.14em] text-gray500 dark:text-gray400">Sweat Equity</p>
                      <p className="mt-2 text-lg font-semibold text-neutral900 dark:text-white">${investment.sweatEquityValue.toLocaleString()}</p>
                    </div>
                    <div className="manifest-card px-4 py-4">
                      <p className="text-xs font-bold uppercase tracking-[0.14em] text-gray500 dark:text-gray400">Equity Stake</p>
                      <p className="mt-2 text-lg font-semibold text-accent-600 dark:text-accent-300">{investment.equityPercentage.toFixed(2)}%</p>
                    </div>
                  </div>
                </article>
              </Link>
            ))}
          </section>
        )}
      </div>
    </div>
  );
};

export default PortfolioPage;
