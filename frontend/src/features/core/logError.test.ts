import { createLogger } from './logError';

describe('createLogger', () => {
  const originalNodeEnv = process.env.NODE_ENV;

  afterEach(() => {
    process.env.NODE_ENV = originalNodeEnv;
    delete (window as any).__LOGS__;
    delete (window as any).Sentry;
  });

  it('forwards logs to Sentry in production', () => {
    process.env.NODE_ENV = 'production';
    const captureMessage = jest.fn();
    (window as any).Sentry = { captureMessage };

    const logger = createLogger('account');
    logger.error('Failed to fetch profile', new Error('boom'));

    expect(captureMessage).toHaveBeenCalledTimes(1);
    expect(captureMessage).toHaveBeenCalledWith(
      'ERROR [account] Failed to fetch profile',
      expect.objectContaining({ level: 'error' })
    );
    expect((window as any).__LOGS__).toBeUndefined();
  });
});
