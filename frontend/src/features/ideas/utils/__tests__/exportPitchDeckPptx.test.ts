import { parsePitchDeckDocument, sanitizeFilename } from '../pitchDeckDocument';

const SAMPLE_DECK = `# Slide 1: Company Purpose
We help retailers retain customers.
- Headline takeaway
- Wedge segment

# Slide 2: Problem
Shoppers churn because rewards do not travel.
- Pain point one
- Pain point two`;

describe('exportPitchDeckPptx integration', () => {
  it('derives export filename from deck title', () => {
    const parsed = parsePitchDeckDocument(SAMPLE_DECK, 'Retail Loyalty');
    expect(`${sanitizeFilename(parsed.documentTitle)}-pitch-deck.pptx`).toBe('retail-loyalty-pitch-deck.pptx');
  });

  it('maps one export slide per parsed section', () => {
    const parsed = parsePitchDeckDocument(SAMPLE_DECK, 'Retail Loyalty');
    expect(parsed.sections).toHaveLength(2);
    expect(parsed.sections[0].title).toBe('Slide 1: Company Purpose');
  });
});
