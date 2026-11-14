import React from "react";
import { gql } from "@apollo/client";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";

import { GET_IDEAS } from "../../../core/apollo/queries";
import VerifiedBadge from "../VerifiedBadge";

const TOGGLE_PUBLISH_IDEA = gql`
  mutation TogglePublishIdea($ideaId: String!) {
    togglePublishIdea(ideaId: $ideaId) {
      ideaId
      isPublished
    }
  }
`;

const createMocks = (initialPublished: boolean, resultPublished: boolean) => [
  {
    request: {
      query: TOGGLE_PUBLISH_IDEA,
      variables: { ideaId: "test-idea-1" },
    },
    result: {
      data: {
        togglePublishIdea: {
          ideaId: "test-idea-1",
          isPublished: resultPublished,
        },
      },
    },
  },
  {
    request: { query: GET_IDEAS },
    result: { data: { ideas: [] } },
  },
];

const renderBadge = (props: Partial<React.ComponentProps<typeof VerifiedBadge>> = {}) => {
  const defaultProps = {
    ideaId: "test-idea-1",
    isPublished: false,
  };

  const mergedProps = { ...defaultProps, ...props };
  const mocks = createMocks(mergedProps.isPublished, !mergedProps.isPublished);

  return render(
    <MockedProvider mocks={mocks} addTypename={false}>
      <VerifiedBadge {...mergedProps} />
    </MockedProvider>,
  );
};

describe("VerifiedBadge / IdeaPublishBadge", () => {
  describe("Rendering", () => {
    test("renders as a button", () => {
      renderBadge();
      expect(screen.getByTestId("idea-publish-badge")).toBeInTheDocument();
    });

    test("renders icon svg", () => {
      renderBadge();
      expect(document.querySelector("svg")).toBeInTheDocument();
    });

    test("is circular (rounded-full)", () => {
      renderBadge();
      expect(screen.getByRole("button")).toHaveClass("rounded-full");
    });
  });

  describe("Size Variants", () => {
    test("renders small size (platform-scale)", () => {
      renderBadge({ size: "sm" });
      const badge = screen.getByRole("button");
      expect(badge.className).toMatch(/h-\[22px\]/);
      expect(badge.className).toMatch(/w-\[22px\]/);
    });

    test("renders medium size", () => {
      renderBadge({ size: "md" });
      const badge = screen.getByRole("button");
      expect(badge.className).toMatch(/h-\[26px\]/);
      expect(badge.className).toMatch(/w-\[26px\]/);
    });

    test("renders large size", () => {
      renderBadge({ size: "lg" });
      const badge = screen.getByRole("button");
      expect(badge).toHaveClass("h-8", "w-8");
    });

    test("defaults to medium size", () => {
      renderBadge();
      const badge = screen.getByRole("button");
      expect(badge.className).toMatch(/h-\[26px\]/);
    });
  });

  describe("Published State", () => {
    test("shows blue verified background when published", () => {
      renderBadge({ isPublished: true });
      expect(screen.getByRole("button")).toHaveClass("bg-blue-500");
    });

    test("shows neutral draft background when unpublished", () => {
      renderBadge({ isPublished: false });
      expect(screen.getByRole("button")).toHaveClass("bg-neutral-300");
    });
  });

  describe("Interaction", () => {
    test("calls onToggle callback when clicked", async () => {
      const onToggle = jest.fn();
      renderBadge({ isPublished: false, onToggle });

      fireEvent.click(screen.getByRole("button"));

      await waitFor(() => {
        expect(onToggle).toHaveBeenCalledWith(true);
      });
    });

    test("stops event propagation on click", () => {
      const parentClick = jest.fn();

      render(
        <MockedProvider mocks={createMocks(false, true)} addTypename={false}>
          <div onClick={parentClick}>
            <VerifiedBadge ideaId="test-idea-1" isPublished={false} />
          </div>
        </MockedProvider>,
      );

      fireEvent.click(screen.getByRole("button"));

      expect(parentClick).not.toHaveBeenCalled();
    });
  });

  describe("Accessibility", () => {
    test("has aria-label for published state", () => {
      renderBadge({ isPublished: true });
      const badge = screen.getByRole("button");
      expect(badge.getAttribute("aria-label")).toContain("Published");
    });

    test("has aria-label for unpublished state", () => {
      renderBadge({ isPublished: false });
      const badge = screen.getByRole("button");
      expect(badge.getAttribute("aria-label")).toContain("Not published");
    });

    test("exposes aria-pressed", () => {
      renderBadge({ isPublished: true });
      expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");
    });

    test("has title tooltip", () => {
      renderBadge({ isPublished: false });
      expect(screen.getByRole("button")).toHaveAttribute("title");
    });
  });

  describe("Motion and focus", () => {
    test("uses transition on transform", () => {
      renderBadge();
      expect(screen.getByRole("button").className).toMatch(/transition-transform/);
    });

    test("uses focus-visible ring", () => {
      renderBadge();
      expect(screen.getByRole("button").className).toMatch(/focus-visible:ring-2/);
    });
  });
});

describe("VerifiedBadge X/Instagram-style verified mark", () => {
  test("published state is filled blue circle with white check stroke", () => {
    renderBadge({ isPublished: true });
    const badge = screen.getByRole("button");
    const svg = badge.querySelector("svg");

    expect(badge).toHaveClass("rounded-full", "bg-blue-500", "text-white");
    expect(svg).toBeInTheDocument();
    expect(svg?.querySelector("path")?.getAttribute("d")).toContain("M9 12.5");
  });

  test("unpublished state shows plus affordance", () => {
    renderBadge({ isPublished: false });
    const paths = screen.getByRole("button").querySelectorAll("svg path");
    expect(paths.length).toBeGreaterThanOrEqual(1);
    expect(Array.from(paths).some((p) => p.getAttribute("d")?.includes("M12 8.5"))).toBe(true);
  });
});
