import type { Preview } from '@storybook/react-webpack5'
import '../src/index.css'; // Import Tailwind/global styles

import React, { useEffect } from 'react';
import { Provider } from 'react-redux';
import { store } from '../src/store';
import { MessageProvider } from '../src/context/MessageContext';
import { MemoryRouter } from 'react-router-dom';

const withProviders = (Story: any) => {
  return React.createElement(
    Provider as React.ComponentType<any>,
    { store, children: React.createElement(
      MessageProvider as React.ComponentType<any>,
      { children: React.createElement(Story as React.ComponentType<any>, null) }
    ) }
  );
};

const FontLoader: React.FC = () => {
  useEffect(() => {
    const link = document.createElement('link');
    link.href = 'https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap';
    link.rel = 'stylesheet';
    document.head.appendChild(link);
    return () => {
      document.head.removeChild(link);
    };
  }, []);
  return null;
};

const withFont = (Story: any) => (
  <>
    <FontLoader />
    <Story />
  </>
);

const withRouter = (Story: any) => (
  <MemoryRouter>
    <Story />
  </MemoryRouter>
);

const preview: Preview = {
  decorators: [withRouter, withFont, withProviders],
  parameters: {
    controls: {
      matchers: {
       color: /(background|color)$/i,
       date: /Date$/i,
      },
    },
  },
};

export default preview;