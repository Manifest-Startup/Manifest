import React, { useState, useRef, useEffect } from "react";
import { useApolloClient, useQuery, useMutation, useReactiveVar } from "@apollo/client/react";
import { accountVar, userVar } from "features/core/apollo/localState";
import { GET_ACCOUNT, UPDATE_ACCOUNT, GET_MY_PORTFOLIO } from "features/core/apollo/queries";
import { useSafeQuery } from 'features/common-ui/api/useSafeQuery';
import { uploadProfilePicture } from "features/account/api/uploadProfilePicture";
import { getAvatarUrl, normalizeGravatarInput } from "features/account/utils/gravatar";
import IOSPageWrapper from "../components/IOSPageWrapper";
import AiKeySection from "features/account/components/AiKeySection";
import IntegrationsSection from "features/account/components/IntegrationsSection";
import OpenMediaSection from "features/account/components/OpenMediaSection";
import ApiAccessSection from "features/account/components/ApiAccessSection";
import PrivacyControlsPanel from "features/account/components/PrivacyControlsPanel";
import SecuritySettingsPanel from "features/account/components/SecuritySettingsPanel";
import ImportExportModal from "features/ideas/components/ImportExportModal";
import ProductFeedbackSurveyCard from "features/feedback/ProductFeedbackSurveyCard";
import SurveyInsightsPanel from "features/feedback/SurveyInsightsPanel";
import { useTheme } from "context/ThemeContext";
import { Link } from "react-router-dom";
import { useFormState, useInputHandlers } from "features/common-ui/hooks/formHooks";
import type { PortfolioItem } from "features/core/apollo/operationTypes";

const IOSAccountPage: React.FC = () => {
  const { isLoggedIn } = useReactiveVar(userVar);
  const { data, loading, error } = useSafeQuery(GET_ACCOUNT);
  const { data: portfolioData, loading: portfolioLoading } = useQuery(GET_MY_PORTFOLIO, {
    skip: !isLoggedIn
  });
  const [updateAccount] = useMutation(UPDATE_ACCOUNT, {
    refetchQueries: [{ query: GET_ACCOUNT }],
  });
  const client = useApolloClient();

  const { theme, setTheme } = useTheme();
  const [activeTab, setActiveTab] = useState<'portfolio' | 'settings'>('portfolio');
  const [gravatarInput, setGravatarInput] = useState('');
  const [localProfilePreviewUrl, setLocalProfilePreviewUrl] = useState<string | null>(null);
  const [uploadMessage, setUploadMessage] = useState('');
  const [profilePictureUploading, setProfilePictureUploading] = useState(false);
  const { formData, updateField } = useFormState<{ email: string; firstName: string; lastName: string }>({ email: '', firstName: '', lastName: '' });
  const { handleInputChange } = useInputHandlers(updateField);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isImportExportOpen, setIsImportExportOpen] = useState(false);

  const investments: PortfolioItem[] = portfolioData?.myPortfolio || [];
  const { accountData } = useReactiveVar(accountVar);

  useEffect(() => {
    if (data) {
      const account = data.account;
      accountVar({ accountData: account, loading: false, error: null });
      const gravatar = account?.gravatarHash || '';
      setGravatarInput(gravatar);
      updateField('email', account?.email || '');
      updateField('firstName', account?.firstName || '');
      updateField('lastName', account?.lastName || '');
    }
  }, [data, updateField]);

  useEffect(() => {
    return () => {
      if (localProfilePreviewUrl) {
        URL.revokeObjectURL(localProfilePreviewUrl);
      }
    };
  }, [localProfilePreviewUrl]);

  const handleProfilePictureUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setProfilePictureUploading(true);
    setUploadMessage('');
    try {
      await uploadProfilePicture(file);
      await client.refetchQueries({ include: [GET_ACCOUNT] });
      if (localProfilePreviewUrl) {
        URL.revokeObjectURL(localProfilePreviewUrl);
      }
      setLocalProfilePreviewUrl(null);
      setUploadMessage('Profile picture saved.');
    } catch (err) {
      console.error('Profile picture upload failed', err);
      setUploadMessage(err instanceof Error ? err.message : 'Could not upload profile picture.');
    } finally {
      setProfilePictureUploading(false);
      e.target.value = '';
    }
  };

  const handleSaveDetails = async () => {
    try {
      const normalizedGravatar = normalizeGravatarInput(gravatarInput);
      const { data: updatedData } = await updateAccount({
        variables: {
          input: {
            firstName: formData.firstName,
            lastName: formData.lastName,
            email: formData.email,
            gravatarHash: normalizedGravatar
          }
        }
      });
      if (updatedData?.updateAccount) {
        accountVar({ accountData: updatedData.updateAccount, loading: false, error: null });
        setGravatarInput(updatedData.updateAccount.gravatarHash || normalizedGravatar);
        setUploadMessage('');
      }
    } catch (err) {
      console.error('Failed to update account details', err);
    }
  };

  if (loading) {
    return (
      <IOSPageWrapper>
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="animate-spin w-8 h-8 border-4 border-accent-600 dark:border-accent-400 border-t-transparent rounded-full" />
        </div>
      </IOSPageWrapper>
    );
  }

  if (error) {
    return (
      <IOSPageWrapper>
        <div className="p-8 text-red-500 dark:text-red-400 text-center">Error loading account information</div>
      </IOSPageWrapper>
    );
  }

  const userDetails = accountData || {};
  const totalInvested = investments.reduce((sum, inv) => sum + inv.cashAmount + inv.sweatEquityValue, 0);
  const totalEquity = investments.reduce((sum, inv) => sum + inv.equityPercentage, 0);
  const avatarSrc =
    localProfilePreviewUrl ||
    getAvatarUrl({
      profilePictureUrl: userDetails.profilePictureUrl,
      gravatarHash: gravatarInput || userDetails.gravatarHash,
      size: 80,
    });

  return (
    <IOSPageWrapper>
      <div className="max-w-screen-sm mx-auto px-4 py-5 pb-24">
        <div className="border-b border-theme-primary pb-5 mb-4">
          <div className="flex items-center gap-4">
            <img
              src={avatarSrc}
              alt="Profile"
              className="w-14 h-14 shrink-0 rounded-full border-2 border-gray-200 dark:border-neutral600"
            />
            <div className="min-w-0 break-words">
              <h2 className="manifest-page-title">
                {userDetails.firstName && userDetails.lastName 
                  ? `${userDetails.firstName} ${userDetails.lastName}` 
                  : userDetails.email || 'User'}
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">Account Settings</p>
            </div>
          </div>
        </div>

        <div className="flex bg-gray-100 dark:bg-neutral800 rounded-xl p-1 mb-4">
          <button
            onClick={() => setActiveTab('portfolio')}
            className={`flex-1 py-2.5 px-4 rounded-lg font-medium text-sm transition-all ${
              activeTab === 'portfolio' 
                ? 'bg-white dark:bg-neutral700 text-gray-900 dark:text-white shadow-none'
                : 'text-gray-600 dark:text-gray-400'
            }`}
          >
            Portfolio
          </button>
          <button
            onClick={() => setActiveTab('settings')}
            className={`flex-1 py-2.5 px-4 rounded-lg font-medium text-sm transition-all ${
              activeTab === 'settings' 
                ? 'bg-white dark:bg-neutral700 text-gray-900 dark:text-white shadow-none'
                : 'text-gray-600 dark:text-gray-400'
            }`}
          >
            Settings
          </button>
        </div>

        {activeTab === 'portfolio' && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-white dark:bg-neutral800 rounded-xl p-4 shadow-none border border-gray-100 dark:border-neutral700 text-center transition-colors">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Investments</p>
                <p className="manifest-page-title">{investments.length}</p>
              </div>
              <div className="bg-white dark:bg-neutral800 rounded-xl p-4 shadow-none border border-gray-100 dark:border-neutral700 text-center transition-colors">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Total Value</p>
                <p className="text-xl font-bold text-green-600 dark:text-green-400">${totalInvested.toLocaleString()}</p>
              </div>
              <div className="bg-white dark:bg-neutral800 rounded-xl p-4 shadow-none border border-gray-100 dark:border-neutral700 text-center transition-colors">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Equity</p>
                <p className="text-xl font-bold text-accent-600 dark:text-accent-400">{totalEquity.toFixed(1)}%</p>
              </div>
            </div>

            {portfolioLoading ? (
              <div className="space-y-3">
                {[1, 2].map((i) => (
                  <div key={i} className="bg-white dark:bg-neutral800 rounded-xl p-4 animate-pulse">
                    <div className="h-5 w-32 bg-gray-200 dark:bg-neutral700 rounded mb-2" />
                    <div className="h-4 w-full bg-gray-200 dark:bg-neutral700 rounded" />
                  </div>
                ))}
              </div>
            ) : investments.length === 0 ? (
              <div className="bg-white dark:bg-neutral800 rounded-xl p-8 shadow-none border border-gray-100 dark:border-neutral700 text-center transition-colors">
                <svg className="w-12 h-12 mx-auto mb-3 text-gray-300 dark:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                <h3 className="font-semibold text-gray-900 dark:text-white mb-2">No investments yet</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Browse pitch reels to spot investable ideas</p>
                <Link
                  to="/pitch-reels"
                  className="inline-flex px-5 py-2.5 bg-accent-600 text-white rounded-full font-medium text-sm"
                >
                  Open Pitch Reels
                </Link>
              </div>
            ) : (
              <div className="space-y-3">
                {investments.map((investment) => (
                  <Link
                    key={investment.investmentId}
                    to={`/ideas/${investment.ideaId}`}
                    className="block bg-white dark:bg-neutral800 rounded-xl p-4 shadow-none border border-gray-100 dark:border-neutral700 active:scale-[0.98] transition-all"
                  >
                    <div className="flex justify-between items-start mb-2">
                      <h3 className="font-semibold text-gray-900 dark:text-white">{investment.ideaTitle}</h3>
                      <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${
                        investment.status === 'confirmed' 
                          ? 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300'
                          : 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300'
                      }`}>
                        {investment.status}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-500 dark:text-gray-400">
                        ${(investment.cashAmount + investment.sweatEquityValue).toLocaleString()}
                      </span>
                      <span className="text-accent-600 dark:text-accent-400 font-medium">
                        {investment.equityPercentage.toFixed(2)}% equity
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="space-y-4">
            <SurveyInsightsPanel variant="ios" />
            <ProductFeedbackSurveyCard variant="ios" />
            <div className="bg-white dark:bg-neutral800 rounded-xl p-4 shadow-none border border-gray-100 dark:border-neutral700 transition-colors">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Appearance</h3>
              <div className="grid grid-cols-3 gap-2">
                {(['light', 'dark', 'system'] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setTheme(mode)}
                    className={`flex flex-col items-center p-3 rounded-xl border-2 transition-all ${
                      theme === mode
                        ? 'border-accent-500 bg-accent-50 dark:bg-accent-900/20'
                        : 'border-gray-200 dark:border-neutral600'
                    }`}
                  >
                    {mode === 'light' && (
                      <svg className="w-5 h-5 mb-1 text-yellow-500" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M12 2.25a.75.75 0 01.75.75v2.25a.75.75 0 01-1.5 0V3a.75.75 0 01.75-.75zM7.5 12a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM18.894 6.166a.75.75 0 00-1.06-1.06l-1.591 1.59a.75.75 0 101.06 1.061l1.591-1.59z" />
                      </svg>
                    )}
                    {mode === 'dark' && (
                      <svg className="w-5 h-5 mb-1 text-indigo-500" fill="currentColor" viewBox="0 0 24 24">
                        <path fillRule="evenodd" d="M9.528 1.718a.75.75 0 01.162.819A8.97 8.97 0 009 6a9 9 0 009 9 8.97 8.97 0 003.463-.69.75.75 0 01.981.98 10.503 10.503 0 01-9.694 6.46c-5.799 0-10.5-4.701-10.5-10.5 0-4.368 2.667-8.112 6.46-9.694a.75.75 0 01.818.162z" clipRule="evenodd" />
                      </svg>
                    )}
                    {mode === 'system' && (
                      <svg className="w-5 h-5 mb-1 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25m18 0A2.25 2.25 0 0018.75 3H5.25A2.25 2.25 0 003 5.25m18 0V12a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 12V5.25" />
                      </svg>
                    )}
                    <span className={`text-xs font-medium capitalize ${theme === mode ? 'text-accent-600 dark:text-accent-400' : 'text-gray-700 dark:text-gray-300'}`}>
                      {mode}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="bg-white dark:bg-neutral800 rounded-xl p-4 shadow-none border border-gray-100 dark:border-neutral700 transition-colors">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Profile</h3>
              <div className="flex items-center gap-4 mb-4">
                <img
                  src={avatarSrc}
                  alt="Profile"
                  className="w-16 h-16 rounded-full border-2 border-gray-200 dark:border-neutral600"
                />
                <div className="flex-1">
                  <input
                    type="file"
                    accept="image/*"
                    ref={fileInputRef}
                    onChange={handleProfilePictureUpload}
                    className="hidden"
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={profilePictureUploading}
                    className="px-4 py-2 text-sm font-medium text-accent-600 dark:text-accent-400 border border-accent-600 dark:border-accent-400 rounded-lg disabled:opacity-50"
                  >
                    {profilePictureUploading ? 'Uploading…' : 'Upload photo'}
                  </button>
                  {uploadMessage ? <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">{uploadMessage}</p> : null}
                </div>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">First Name</label>
                  <input
                    type="text"
                    value={formData.firstName}
                    name="firstName"
                    onChange={handleInputChange}
                    className="w-full px-3 py-2.5 bg-gray-50 dark:bg-neutral700 border border-gray-200 dark:border-neutral600 rounded-lg text-gray-900 dark:text-white text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Last Name</label>
                  <input
                    type="text"
                    value={formData.lastName}
                    name="lastName"
                    onChange={handleInputChange}
                    className="w-full px-3 py-2.5 bg-gray-50 dark:bg-neutral700 border border-gray-200 dark:border-neutral600 rounded-lg text-gray-900 dark:text-white text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Email</label>
                  <input
                    type="email"
                    value={formData.email}
                    name="email"
                    onChange={handleInputChange}
                    className="w-full px-3 py-2.5 bg-gray-50 dark:bg-neutral700 border border-gray-200 dark:border-neutral600 rounded-lg text-gray-900 dark:text-white text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Gravatar URL Or Hash</label>
                  <input
                    type="text"
                    value={gravatarInput}
                    onChange={(event) => setGravatarInput(event.target.value)}
                    placeholder="Paste a Gravatar URL or raw hash"
                    className="w-full px-3 py-2.5 bg-gray-50 dark:bg-neutral700 border border-gray-200 dark:border-neutral600 rounded-lg text-gray-900 dark:text-white text-sm"
                  />
                </div>
                <button
                  onClick={handleSaveDetails}
                  className="w-full py-2.5 bg-accent-600 text-white rounded-lg font-medium text-sm active:scale-[0.98] transition-transform"
                >
                  Save Changes
                </button>
              </div>
            </div>

            <div id="ai-key" className="bg-white dark:bg-neutral800 rounded-xl p-4 shadow-none border border-gray-100 dark:border-neutral700 transition-colors">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Your OpenAI key</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">AI features run on your own OpenAI account. The key is verified, encrypted, and never shown again.</p>
              <AiKeySection />
            </div>

            <div id="open-media" className="bg-white dark:bg-neutral800 rounded-xl p-4 shadow-none border border-gray-100 dark:border-neutral700 transition-colors">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Sign-in</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">One account for Manifest and Open Media. Messages and Pitch Shorts run on it too.</p>
              <OpenMediaSection />
            </div>

            <IntegrationsSection />
            
            <ApiAccessSection />

            <div className="bg-white dark:bg-neutral800 rounded-xl p-4 shadow-none border border-gray-100 dark:border-neutral700 transition-colors">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Sessions</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Review where you are signed in to Manifest and revoke old browsers or devices.</p>
              <SecuritySettingsPanel />
            </div>

            <div className="bg-white dark:bg-neutral800 rounded-xl p-4 shadow-none border border-gray-100 dark:border-neutral700 transition-colors">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Data Management</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">Bring startup ideas in from Apple Notes or Google Keep, or export your workspace for backup.</p>
              <button
                onClick={() => setIsImportExportOpen(true)}
                className="w-full py-2.5 border border-gray-200 dark:border-neutral600 text-gray-700 dark:text-gray-300 rounded-lg font-medium text-sm active:scale-[0.98] transition-transform"
              >
                Import / Export Ideas
              </button>
            </div>

            <div className="bg-white dark:bg-neutral800 rounded-xl p-4 shadow-none border border-gray-100 dark:border-neutral700 transition-colors">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-2">Privacy</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Review retention windows and request account deletion.</p>
              <PrivacyControlsPanel accountEmail={userDetails.email} />
            </div>
          </div>
        )}
      </div>
      
      <ImportExportModal isOpen={isImportExportOpen} onClose={() => setIsImportExportOpen(false)} />
    </IOSPageWrapper>
  );
};

export default IOSAccountPage;
