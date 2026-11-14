import React from 'react';
import { render, screen } from '@testing-library/react';

import { CostStructureDisplay } from '../CostStructureDisplay';

jest.mock('features/notifications/context/MessageContext', () => ({
  useMessage: () => ({
    setMessage: jest.fn(),
  }),
}));

describe('CostStructureDisplay', () => {
  it('renders formatted markdown cost drivers without raw markdown tokens and surfaces numeric estimates', () => {
    render(
      <CostStructureDisplay
        cost={`## Primary Cost Drivers
- **Manufacturing Costs**: $45,000 to $70,000 one-time for raw materials, tooling, and assembly. Approximately 30% of the MVP budget.
- **Cloud Infrastructure**: $1,200 per month for hosting, storage, and monitoring during the launch phase.`}
      />,
    );

    expect(screen.getByText('Manufacturing Costs')).toBeInTheDocument();
    expect(screen.queryByText('**Manufacturing Costs**')).not.toBeInTheDocument();
    expect(screen.getByText('Production')).toBeInTheDocument();
    expect(screen.getAllByText(/\$45,000 to \$70,000/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/30% of the mvp budget/i)).toBeInTheDocument();
    expect(screen.getAllByText(/\$1,200 per month/i).length).toBeGreaterThan(0);
  });

  it('normalizes nested stringified json cost data into readable cards', () => {
    render(
      <CostStructureDisplay
        cost={JSON.stringify({
          primary_cost_drivers: JSON.stringify({
            manufacturing_costs: {
              estimate: '$60,000',
              details: 'Tooling, raw materials, and contract assembly for the first pilot run.',
            },
          }),
        })}
      />,
    );

    expect(screen.getByText('Manufacturing Costs')).toBeInTheDocument();
    expect(screen.getAllByText(/\$60,000/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/tooling, raw materials, and contract assembly/i)).toBeInTheDocument();
  });
});
