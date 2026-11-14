import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MockedProvider } from '@apollo/client/testing/react';
import InvestmentModal from '../InvestmentModal';
import { CREATE_INVESTMENT, CALCULATE_SWEAT_EQUITY } from 'features/core/apollo/queries';

const mockOnClose = jest.fn();
const mockOnSuccess = jest.fn();

const createInvestmentMock = {
  request: {
    query: CREATE_INVESTMENT,
    variables: {
      input: {
        ideaId: 'idea-123',
        cashAmount: 10000,
        sweatEquityHours: 0,
        hourlyRate: 50,
        equityPercentage: 5,
        investmentType: 'cash',
        role: null,
        notes: null
      }
    }
  },
  result: {
    data: {
      createInvestment: {
        investmentId: 'inv-123',
        ideaId: 'idea-123',
        investorId: 'user-456',
        cashAmount: 10000,
        sweatEquityHours: 0,
        sweatEquityValue: 0,
        equityPercentage: 5,
        investmentType: 'cash',
        role: null,
        status: 'pending',
        notes: null,
        createdAt: '2025-01-01T00:00:00Z',
        investorName: 'Test User',
        investorAvatar: null
      }
    }
  }
};

const calculateSweatEquityMock = {
  request: {
    query: CALCULATE_SWEAT_EQUITY,
    variables: {
      hours: 100,
      hourlyRate: 50,
      totalValuation: 100000
    }
  },
  result: {
    data: {
      calculateSweatEquity: {
        sweatValue: 5000,
        equityPercentage: 5,
        hours: 100,
        hourlyRate: 50
      }
    }
  }
};

const renderModal = (
  isOpen = true,
  mocks = [createInvestmentMock, calculateSweatEquityMock],
  tone: 'light' | 'dark' = 'light',
) => {
  return render(
    <MockedProvider mocks={mocks} addTypename={false}>
      <InvestmentModal
        ideaId="idea-123"
        ideaTitle="Test Startup Idea"
        isOpen={isOpen}
        onClose={mockOnClose}
        onSuccess={mockOnSuccess}
        tone={tone}
      />
    </MockedProvider>
  );
};

describe('InvestmentModal', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders nothing when closed', () => {
    renderModal(false);
    expect(screen.queryByText('Invest in Idea')).not.toBeInTheDocument();
  });

  it('renders the modal when open', () => {
    renderModal();
    expect(screen.getByText('Invest in Idea')).toBeInTheDocument();
    expect(screen.getByText('Test Startup Idea')).toBeInTheDocument();
  });

  it('shows investment type buttons', () => {
    renderModal();
    expect(screen.getByText('Cash')).toBeInTheDocument();
    expect(screen.getByText('Sweat Equity')).toBeInTheDocument();
    expect(screen.getByText('Both')).toBeInTheDocument();
  });

  it('shows cash amount input by default', () => {
    renderModal();
    expect(screen.getByPlaceholderText('10000')).toBeInTheDocument();
  });

  it('switches to sweat equity fields when selected', () => {
    renderModal();
    fireEvent.click(screen.getByText('Sweat Equity'));
    expect(screen.getByPlaceholderText('100')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('50')).toBeInTheDocument();
  });

  it('shows both cash and sweat fields when Both is selected', () => {
    renderModal();
    fireEvent.click(screen.getByText('Both'));
    expect(screen.getByPlaceholderText('10000')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('100')).toBeInTheDocument();
  });

  it('closes when cancel is clicked', () => {
    renderModal();
    fireEvent.click(screen.getByText('Cancel'));
    expect(mockOnClose).toHaveBeenCalled();
  });

  it('closes when X button is clicked', () => {
    renderModal();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(mockOnClose).toHaveBeenCalled();
  });

  it('uses dark surface classes when tone is dark', () => {
    renderModal(true, [createInvestmentMock, calculateSweatEquityMock], 'dark');
    const panel = screen.getByRole('dialog');
    expect(panel.className).toMatch(/#0f1419/);
  });

  it('submits cash investment', async () => {
    renderModal();
    
    fireEvent.change(screen.getByPlaceholderText('10000'), {
      target: { value: '10000' }
    });
    
    fireEvent.change(screen.getByPlaceholderText('5'), {
      target: { value: '5' }
    });

    fireEvent.click(screen.getByText('Invest'));

    await waitFor(() => {
      expect(mockOnSuccess).toHaveBeenCalled();
    });
  });

  it('shows equity percentage field', () => {
    renderModal();
    expect(screen.getByPlaceholderText('5')).toBeInTheDocument();
  });

  it('shows optional role field', () => {
    renderModal();
    expect(screen.getByPlaceholderText('Advisor, Developer, Marketing...')).toBeInTheDocument();
  });

  it('shows optional notes field', () => {
    renderModal();
    expect(screen.getByPlaceholderText('Additional terms or notes...')).toBeInTheDocument();
  });
});
