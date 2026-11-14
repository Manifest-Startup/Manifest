import personas from "../fixtures/e2ePersonas.json";

export const E2E_PERSONAS = personas;
// Must satisfy backend signup policy (3 of: upper, lower, digit, symbol).
export const E2E_DEFAULT_PASSWORD = Cypress.env("e2ePassword") || "Mnfst_E2e_CI_9x!";
export const LEGACY_E2E_USER = {
  slug: "legacy-default",
  displayName: "Legacy Default User",
  email: "hello@manifeststartup.com",
  password: E2E_DEFAULT_PASSWORD,
  persona: "Backward-compatible default account for existing Cypress specs.",
};

export const getPersonaBySlug = (slug) => {
  if (slug === LEGACY_E2E_USER.slug) {
    return LEGACY_E2E_USER;
  }

  return E2E_PERSONAS.find((persona) => persona.slug === slug);
};
