import React from "react";
import { gql } from "@apollo/client";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing/react";

import { GET_IDEAS } from "../../../core/apollo/queries";
import PublishTick from "../PublishTick";

const TOGGLE_PUBLISH_IDEA = gql`
  mutation TogglePublishIdea($ideaId: String!) {
    togglePublishIdea(ideaId: $ideaId) {
      ideaId
      isPublished
    }
  }
`;

const mocksForToggle = (nextPublished: boolean) => [
  {
    request: {
      query: TOGGLE_PUBLISH_IDEA,
      variables: { ideaId: "ios-idea-1" },
    },
    result: {
      data: {
        togglePublishIdea: {
          ideaId: "ios-idea-1",
          isPublished: nextPublished,
        },
      },
    },
  },
  {
    request: { query: GET_IDEAS },
    result: { data: { ideas: [] } },
  },
];

describe("PublishTick (IdeaPublishBadge wrapper)", () => {
  test("renders same control as verified badge", () => {
    render(
      <MockedProvider mocks={mocksForToggle(true)} addTypename={false}>
        <PublishTick ideaId="ios-idea-1" isPublished={false} size="sm" />
      </MockedProvider>,
    );
    expect(screen.getByTestId("idea-publish-badge")).toBeInTheDocument();
  });

  test("toggle fires mutation and updates optimistic UI", async () => {
    render(
      <MockedProvider mocks={mocksForToggle(true)} addTypename={false}>
        <PublishTick ideaId="ios-idea-1" isPublished={false} />
      </MockedProvider>,
    );

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(screen.getByRole("button")).toHaveClass("bg-blue-500");
    });
  });
});
