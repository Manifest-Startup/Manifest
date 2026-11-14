module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: {
      jsx: true,
    },
  },
  env: {
    browser: true,
    es2022: true,
    node: true,
    jest: true,
  },
  plugins: ['@typescript-eslint', 'react-hooks'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
  ],
  ignorePatterns: ['build/', 'dist/', 'coverage/', 'node_modules/'],
  overrides: [
    {
      files: ['src/utils/logError.ts'],
      rules: {
        'no-console': 'off',
      },
    },
  ],
  rules: {
    // Disallow console.* in production code; encourage createLogger. Allow console.error and console.warn.
    'no-console': ['error', { allow: ['warn', 'error', 'log', 'debug'] }],
    '@typescript-eslint/no-empty-function': 'off',
    '@typescript-eslint/no-explicit-any': 'off',
    '@typescript-eslint/no-unused-vars': 'off',
    '@typescript-eslint/no-var-requires': 'off',
    '@typescript-eslint/ban-types': 'off',
    '@typescript-eslint/prefer-as-const': 'off',
    '@typescript-eslint/no-empty-object-type': 'off',
    '@typescript-eslint/no-require-imports': 'off',
    'no-var': 'off',
  },
};
