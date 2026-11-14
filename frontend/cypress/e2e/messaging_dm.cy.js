const GET_PROFILE_QUERY = `
  query GetProfile {
    profile {
      userId
      email
      isGuest
    }
  }
`;

const START_CONVERSATION_MUTATION = `
  mutation StartConversation($otherUserId: String!, $ideaId: String) {
    startConversation(otherUserId: $otherUserId, ideaId: $ideaId) {
      conversationId
      otherUserId
      otherUserName
    }
  }
`;

const openConversationThread = (conversationId) => {
  cy.visit(`/messages/${conversationId}`);
  cy.get('[data-testid="messages-page"]', { timeout: 15000 }).should("be.visible");
  cy.get('[data-testid="chat-panel"]', { timeout: 15000 }).should("be.visible");
};

describe("Multi-user direct messaging", () => {
  it("sends and receives messages between two seeded personas", () => {
    const senderMessage = `Alice to Farah ${Date.now()}`;
    const replyMessage = `Farah reply ${Date.now()}`;
    let recipientUserId = "";
    let conversationId = "";

    cy.loginAsPersona("farah-nasir");
    cy.graphqlRequest({
      operationName: "GetProfile",
      query: GET_PROFILE_QUERY,
    }).then((response) => {
      recipientUserId = response.body?.data?.profile?.userId;
      expect(recipientUserId).to.be.a("string").and.not.be.empty;
    });

    cy.resetAuthState();
    cy.loginAsPersona("alice-chen");
    cy.graphqlRequest({
      operationName: "StartConversation",
      query: START_CONVERSATION_MUTATION,
      variables: {
        otherUserId: recipientUserId,
        ideaId: null,
      },
    }).then((response) => {
      conversationId = response.body?.data?.startConversation?.conversationId;
      expect(conversationId).to.be.a("string").and.not.be.empty;
    });

    openConversationThread(conversationId);
    cy.get('[data-testid="chat-message-input"]').type(senderMessage);
    cy.get('[data-testid="chat-send-button"]').click();
    cy.contains(senderMessage, { timeout: 15000 }).should("be.visible");

    cy.resetAuthState();
    cy.loginAsPersona("farah-nasir");
    openConversationThread(conversationId);
    cy.contains(senderMessage, { timeout: 15000 }).should("be.visible");
    cy.get('[data-testid="chat-message-input"]').type(replyMessage);
    cy.get('[data-testid="chat-send-button"]').click();
    cy.contains(replyMessage, { timeout: 15000 }).should("be.visible");

    cy.resetAuthState();
    cy.loginAsPersona("alice-chen");
    openConversationThread(conversationId);
    cy.contains(replyMessage, { timeout: 15000 }).should("be.visible");
  });
});
