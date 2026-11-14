import type { StorybookConfig } from '@storybook/react-webpack5';
import webpack from 'webpack';

const config: StorybookConfig = {
  "stories": [
    "../src/**/*.mdx",
    "../src/**/*.stories.@(js|jsx|mjs|ts|tsx)"
  ],
  "addons": [
    "@storybook/addon-docs",
    "@storybook/addon-onboarding"
  ],
  "framework": {
    "name": "@storybook/react-webpack5",
    "options": {}
  },
  "staticDirs": [
    "../public"
  ],
  webpackFinal: async (config) => {
    config.resolve = config.resolve || {};
    config.resolve.fallback = {
      ...config.resolve.fallback,
      "process": require.resolve("process/browser"),
    };
    config.plugins = [
      ...(config.plugins || []),
      new webpack.ProvidePlugin({
        process: 'process/browser',
      }),
    ];
    return config;
  },
};
export default config;
