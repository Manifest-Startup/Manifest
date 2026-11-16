import { Navigate, useLocation } from "react-router-dom";
import React from "react";
import { useMessage } from "features/notifications/context/MessageContext";
import { useReactiveVar } from '@apollo/client/react';
import { isLogoutRedirectInProgress } from "features/auth/logout";
import { userVar } from "features/core/apollo/localState";

const PrivateRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const { setMessage } = useMessage();
  const { authChecked, isLoggedIn } = useReactiveVar(userVar);

  const handleAuthEffect = () => {
    if (authChecked !== false && !isLoggedIn && !isLogoutRedirectInProgress()) {
      setMessage("Please log in to access this page.", "error");
    }
  };

  React.useEffect(handleAuthEffect, [authChecked, isLoggedIn, location.pathname, setMessage]);

  if (authChecked === false && !isLoggedIn) {
    return <div className="flex items-center justify-center h-screen">Loading...</div>;
  }

  if (isLoggedIn) {
    return <>{children}</>;
  }

  // If not logged in, redirect to login page with return URL
  return <Navigate to="/login" state={{ from: location }} replace />;
};

// Exporting the PrivateRoute component
export default PrivateRoute;
