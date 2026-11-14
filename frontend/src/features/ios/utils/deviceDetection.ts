/**
 * Device detection utilities for iOS app view
 */

import React from 'react';

export type DeviceType = 'mobile' | 'tablet' | 'desktop' | 'ios';

export interface DeviceInfo {
  type: DeviceType;
  isIOS: boolean;
  isMobile: boolean;
  isTablet: boolean;
  isDesktop: boolean;
  width: number;
  height: number;
}

/**
 * Detects the current device type based on user agent and screen size
 */
export const detectDevice = (): DeviceInfo => {
  if (typeof window === 'undefined') {
    return {
      type: 'desktop',
      isIOS: false,
      isMobile: false,
      isTablet: false,
      isDesktop: true,
      width: 1920,
      height: 1080,
    };
  }

  const width = window.innerWidth;
  const height = window.innerHeight;
  const userAgent = navigator.userAgent || navigator.vendor || (window as any).opera;

  // Check for iOS
  const isIOS = /iPad|iPhone|iPod/.test(userAgent) || 
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

  // Determine device type based on screen size
  const isMobile = width < 768;
  const isTablet = width >= 768 && width < 1024;
  const isDesktop = width >= 1024;

  let type: DeviceType = 'desktop';
  if (isIOS) {
    type = isMobile ? 'ios' : isTablet ? 'ios' : 'desktop';
  } else if (isMobile) {
    type = 'mobile';
  } else if (isTablet) {
    type = 'tablet';
  }

  return {
    type,
    isIOS,
    isMobile,
    isTablet,
    isDesktop,
    width,
    height,
  };
};

/**
 * Hook to get device info with reactive updates on window resize
 */
export const useDeviceDetection = (): DeviceInfo => {
  const [deviceInfo, setDeviceInfo] = React.useState<DeviceInfo>(() => detectDevice());

  React.useEffect(() => {
    const handleResize = () => {
      setDeviceInfo(detectDevice());
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return deviceInfo;
};

