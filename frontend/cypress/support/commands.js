import { E2E_DEFAULT_PASSWORD, getPersonaBySlug, LEGACY_E2E_USER } from "./e2ePersonas";

const emailSelector = 'input[name="email"], input[type="email"]';
const passwordSelector = 'input[name="password"], input[type="password"]';
const graphqlUrl = Cypress.env("graphqlUrl") || "http://localhost:8000/graphql";

function loginWithEmailPassword(email, password = E2E_DEFAULT_PASSWORD, visitOptions = {}) {
  cy.clearCookies();
  cy.clearLocalStorage();
  cy.visit("/auth", visitOptions);
  cy.get(emailSelector, { timeout: 10000 }).first().should("be.visible").clear().type(email);
  cy.get(passwordSelector).first().clear().type(password);
  cy.get('button[type="submit"]').click();
  cy.url({ timeout: 15000 }).should("include", "/ideas");
}

Cypress.Commands.add("loginWithEmailPassword", (email, password = E2E_DEFAULT_PASSWORD, visitOptions = {}) => {
  loginWithEmailPassword(email, password, visitOptions);
});

Cypress.Commands.add("loginAsDefaultUser", () => {
  loginWithEmailPassword(LEGACY_E2E_USER.email, LEGACY_E2E_USER.password);
});

Cypress.Commands.add("loginAsPersona", (slug) => {
  const persona = getPersonaBySlug(slug);
  expect(persona, `persona ${slug}`).to.exist;
  loginWithEmailPassword(persona.email, persona.password || E2E_DEFAULT_PASSWORD);
});

Cypress.Commands.add("resetAuthState", () => {
  cy.clearCookies();
  cy.clearLocalStorage();
});

Cypress.Commands.add("graphqlRequest", ({ operationName, query, variables = {}, failOnStatusCode = true }) => {
  return cy.window().then((win) => {
    const token = win.localStorage.getItem("access_token");
    const headers = token ? { Authorization: `Bearer ${token}` } : undefined;

    return cy.request({
      method: "POST",
      url: graphqlUrl,
      headers,
      failOnStatusCode,
      body: {
        operationName,
        query,
        variables,
      },
    });
  });
});