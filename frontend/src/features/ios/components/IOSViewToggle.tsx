import React from "react";
import { getViewMode, setViewMode, ViewMode } from "../utils/viewMode";
import { detectDevice } from "../utils/deviceDetection";

interface IOSViewToggleProps {
  onToggle?: (mode: ViewMode) => void;
}

/**
 * Toggle button to switch between desktop and iOS views
 */
const IOSViewToggle: React.FC<IOSViewToggleProps> = ({ onToggle }) => {
  const [currentMode, setCurrentMode] = React.useState<ViewMode>(() => getViewMode());
  const device = detectDevice();

  const handleToggle = () => {
    let newMode: ViewMode;
    if (currentMode === 'auto') {
      newMode = device.isIOS ? 'desktop' : 'ios';
    } else if (currentMode === 'ios') {
      newMode = 'desktop';
    } else {
      newMode = 'ios';
    }

    setCurrentMode(newMode);
    setViewMode(newMode);
    onToggle?.(newMode);
    
    // Reload to apply changes
    window.location.reload();
  };

  const getLabel = () => {
    if (currentMode === 'auto') return 'Auto';
    if (currentMode === 'ios') return 'Desktop';
    return 'iOS';
  };

  const isIOSMode = currentMode === 'ios' || (currentMode === 'auto' && device.isIOS);

  return (
    <button
      onClick={handleToggle}
      className={`fixed ${isIOSMode ? 'bottom-20' : 'bottom-4'} right-4 z-50 px-4 py-2 bg-accent-600 text-white rounded-full shadow-lg hover:bg-accent-700 active:scale-95 transition-all text-sm font-medium`}
      title={`Switch to ${isIOSMode ? 'Desktop' : 'iOS'} view`}
    >
      {getLabel()}
    </button>
  );
};

export default IOSViewToggle;

