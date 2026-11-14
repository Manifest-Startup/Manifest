const { defineConfig } = require("cypress");
const performanceReporter = require('./cypress/plugins/performance-reporter');

module.exports = defineConfig({
  projectId: 'djezsb',
  defaultCommandTimeout: 15000,
  requestTimeout: 20000,
  responseTimeout: 20000,
  env: {
    e2ePassword: 'manifest',
    graphqlUrl: 'http://localhost:8000/graphql',
  },
  e2e: {
    baseUrl: 'http://localhost:3000',
    setupNodeEvents(on, config) {
      performanceReporter(on, config);
    },
    reporter: 'mochawesome',
    reporterOptions: {
      reportDir: '../docs/performance/mochawesome-report',
      overwrite: true,
      html: true,
      json: true,
      charts: true,
      embeddedScreenshots: true,
      inlineAssets: true
    }
  },
});
