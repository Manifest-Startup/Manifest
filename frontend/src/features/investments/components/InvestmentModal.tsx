import React, { useState, useCallback, useMemo } from 'react';
import { useMutation, useLazyQuery } from '@apollo/client/react';
import { CREATE_INVESTMENT, CALCULATE_SWEAT_EQUITY } from 'features/core/apollo/queries';

interface InvestmentModalProps {
  ideaId: string;
  ideaTitle: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  /** Dark panel styling for immersive surfaces (e.g. Pitch Reels). */
  tone?: 'light' | 'dark';
}

const InvestmentModal: React.FC<InvestmentModalProps> = ({
  ideaId,
  ideaTitle,
  isOpen,
  onClose,
  onSuccess,
  tone = 'light',
}) => {
  const [investmentType, setInvestmentType] = useState<'cash' | 'sweat' | 'both'>('cash');
  const [cashAmount, setCashAmount] = useState('');
  const [sweatHours, setSweatHours] = useState('');
  const [hourlyRate, setHourlyRate] = useState('50');
  const [equityPercentage, setEquityPercentage] = useState('');
  const [role, setRole] = useState('');
  const [notes, setNotes] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [createInvestment] = useMutation(CREATE_INVESTMENT);
  const [calculateSweatEquity, { data: sweatCalc }] = useLazyQuery(CALCULATE_SWEAT_EQUITY);

  const c = useMemo(() => {
    if (tone === 'dark') {
      return {
        overlay: 'bg-black/70',
        panel: 'bg-[#0f1419] border border-white/10',
        title: 'text-white',
        close: 'text-white/50 hover:text-white',
        muted: 'text-white/70',
        label: 'text-white/85',
        input:
          'bg-white/5 border-white/15 text-white placeholder:text-white/35 focus:ring-blue-500 focus:border-transparent',
        typeIdle: 'bg-white/10 text-white/90 hover:bg-white/14',
        typeActive: 'bg-blue-600 text-white',
        sweatBox: 'bg-blue-950/40 border border-blue-500/25 text-blue-100',
        sweatStrong: 'text-blue-200',
        sweatMuted: 'text-blue-300/90',
        cancel: 'border-white/20 text-white hover:bg-white/10',
        submit: 'bg-blue-600 text-white hover:bg-blue-500',
      };
    }
    return {
      overlay: 'bg-black bg-opacity-50',
      panel: 'bg-white',
      title: 'text-gray-900',
      close: 'text-gray-400 hover:text-gray-600',
      muted: 'text-gray-600',
      label: 'text-gray-700',
      input:
        'bg-white border-gray-300 text-gray-900 placeholder:text-gray-400 focus:ring-blue-500 focus:border-transparent',
      typeIdle: 'bg-gray-100 text-gray-700 hover:bg-gray-200',
      typeActive: 'bg-blue-600 text-white',
      sweatBox: 'bg-blue-50',
      sweatStrong: 'text-blue-800',
      sweatMuted: 'text-blue-600',
      cancel: 'border-gray-300 text-gray-700 hover:bg-gray-50',
      submit: 'bg-blue-600 text-white hover:bg-blue-700',
    };
  }, [tone]);

  const handleSweatHoursChange = useCallback(
    (value: string) => {
      setSweatHours(value);
      const hours = parseFloat(value);
      const rate = parseFloat(hourlyRate);
      if (!isNaN(hours) && !isNaN(rate) && hours > 0) {
        calculateSweatEquity({
          variables: { hours, hourlyRate: rate, totalValuation: 100000 },
        });
      }
    },
    [hourlyRate, calculateSweatEquity],
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      await createInvestment({
        variables: {
          input: {
            ideaId,
            cashAmount: parseFloat(cashAmount) || 0,
            sweatEquityHours: parseFloat(sweatHours) || 0,
            hourlyRate: parseFloat(hourlyRate) || 50,
            equityPercentage: parseFloat(equityPercentage) || 0,
            investmentType,
            role: role || null,
            notes: notes || null,
          },
        },
      });

      onSuccess?.();
      onClose();
      setCashAmount('');
      setSweatHours('');
      setEquityPercentage('');
      setRole('');
      setNotes('');
    } catch (error) {
      console.error('Failed to create investment:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const inputBase = `w-full px-3 py-2 border rounded-lg focus:ring-2 ${c.input}`;

  return (
    <div
      className={`fixed inset-0 ${c.overlay} flex items-center justify-center z-50`}
      role="presentation"
      onClick={onClose}
      data-testid="investment-modal-overlay"
    >
      <div
        className={`${c.panel} rounded-lg shadow-xl max-w-md w-full mx-4 max-h-[90vh] overflow-y-auto`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="investment-modal-title"
        onClick={(e) => e.stopPropagation()}
        data-testid="investment-modal"
      >
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 id="investment-modal-title" className={`text-xl font-semibold ${c.title}`}>
              Invest in Idea
            </h2>
            <button type="button" onClick={onClose} className={c.close} aria-label="Close" data-testid="investment-close">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <p className={`${c.muted} mb-4 text-sm`}>{ideaTitle}</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className={`block text-sm font-medium ${c.label} mb-2`}>Investment Type</label>
              <div className="flex space-x-2">
                {(['cash', 'sweat', 'both'] as const).map((type) => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setInvestmentType(type)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      investmentType === type ? c.typeActive : c.typeIdle
                    }`}
                  >
                    {type === 'cash' ? 'Cash' : type === 'sweat' ? 'Sweat Equity' : 'Both'}
                  </button>
                ))}
              </div>
            </div>

            {(investmentType === 'cash' || investmentType === 'both') && (
              <div>
                <label className={`block text-sm font-medium ${c.label} mb-1`}>Cash Amount ($)</label>
                <input
                  type="number"
                  value={cashAmount}
                  onChange={(e) => setCashAmount(e.target.value)}
                  className={inputBase}
                  placeholder="10000"
                  min="0"
                  step="100"
                  data-testid="investment-cash-amount"
                />
              </div>
            )}

            {(investmentType === 'sweat' || investmentType === 'both') && (
              <>
                <div>
                  <label className={`block text-sm font-medium ${c.label} mb-1`}>Hours to Contribute</label>
                  <input
                    type="number"
                    value={sweatHours}
                    onChange={(e) => handleSweatHoursChange(e.target.value)}
                    className={inputBase}
                    placeholder="100"
                    min="0"
                  />
                </div>

                <div>
                  <label className={`block text-sm font-medium ${c.label} mb-1`}>Hourly Rate ($)</label>
                  <input
                    type="number"
                    value={hourlyRate}
                    onChange={(e) => setHourlyRate(e.target.value)}
                    className={inputBase}
                    placeholder="50"
                    min="0"
                  />
                </div>

                {sweatCalc?.calculateSweatEquity && (
                  <div className={`p-3 rounded-lg text-sm ${c.sweatBox}`}>
                    <p className={c.sweatStrong}>
                      Sweat Equity Value:{' '}
                      <strong>${sweatCalc.calculateSweatEquity.sweatValue.toLocaleString()}</strong>
                    </p>
                    <p className={c.sweatMuted}>
                      Estimated Equity: <strong>{sweatCalc.calculateSweatEquity.equityPercentage.toFixed(2)}%</strong>
                    </p>
                  </div>
                )}
              </>
            )}

            <div>
              <label className={`block text-sm font-medium ${c.label} mb-1`}>Equity Percentage (%)</label>
              <input
                type="number"
                value={equityPercentage}
                onChange={(e) => setEquityPercentage(e.target.value)}
                className={inputBase}
                placeholder="5"
                min="0"
                max="100"
                step="0.1"
                data-testid="investment-equity"
              />
            </div>

            <div>
              <label className={`block text-sm font-medium ${c.label} mb-1`}>Role (optional)</label>
              <input
                type="text"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className={inputBase}
                placeholder="Advisor, Developer, Marketing..."
              />
            </div>

            <div>
              <label className={`block text-sm font-medium ${c.label} mb-1`}>Notes (optional)</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className={inputBase}
                rows={3}
                placeholder="Additional terms or notes..."
              />
            </div>

            <div className="flex space-x-3 pt-4">
              <button
                type="button"
                onClick={onClose}
                className={`flex-1 px-4 py-2 border rounded-lg transition-colors ${c.cancel}`}
                data-testid="investment-cancel"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className={`flex-1 px-4 py-2 rounded-lg disabled:opacity-50 transition-colors ${c.submit}`}
                data-testid="investment-submit"
              >
                {isSubmitting ? 'Submitting...' : 'Invest'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default InvestmentModal;
