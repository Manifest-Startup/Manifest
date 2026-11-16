import { getPersonaBySlug, LEGACY_E2E_USER } from "./e2ePersonas";

const graphqlUrl = Cypress.env("graphqlUrl") || "http://localhost:8000/graphql";

/**
 * Sign in the only way Manifest offers: "Continue with Open Media".
 *
 * Against a local stack in demo mode (no DATABASE_URL), the backend signs in the
 * demo user directly, so specs run without Open Media. Against a stack that talks
 * to a real Open Media, set `openMediaOrigin` and the persona's password; the
 * gateway's password form is driven with `cy.origin`.
 */
function signInWithOpenMedia(persona = LEGACY_E2E_USER, visitOptions = {}) {
  cy.clearCookies();
  cy.clearLocalStorage();
  cy.visit("/login", visitOptions);
  cy.get('[data-testid="continue-with-open-media"]', { timeout: 10000 }).should("be.visible").click();
  const openMediaOrigin = Cypress.env("openMediaOrigin");
  if (openMediaOrigin && persona.password) {
    cy.origin(openMediaOrigin, { args: { email: persona.email, password: persona.password } }, ({ email, password }) => {
      cy.contains(/use a password instead/i, { timeout: 15000 }).click();
      cy.get('input[type="email"]').first().clear().type(email);
      cy.get('input[type="password"]').first().clear().type(password, { log: false });
      cy.contains("button", /continue|sign in/i).click();
    });
  }
  cy.url({ timeout: 20000 }).should("include", "/ideas");
}

Cypress.Commands.add("signInWithOpenMedia", (slug = LEGACY_E2E_USER.slug, visitOptions = {}) => {
  const persona = getPersonaBySlug(slug);
  expect(persona, `persona ${slug}`).to.exist;
  signInWithOpenMedia(persona, visitOptions);
});

Cypress.Commands.add("loginAsDefaultUser", () => {
  signInWithOpenMedia(LEGACY_E2E_USER);
});

Cypress.Commands.add("loginAsPersona", (slug) => {
  const persona = getPersonaBySlug(slug);
  expect(persona, `persona ${slug}`).to.exist;
  signInWithOpenMedia(persona);
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