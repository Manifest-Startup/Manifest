import {
  hasPitchDeckSlideHeadings,
  parsePitchDeckDocument,
  parseSlideBody,
  parseSlideTitle,
  sanitizeFilename,
} from "../pitchDeckDocument";

const SAMPLE_DECK = `# Slide 1: Company Purpose
We help retailers retain customers with blockchain-backed loyalty rewards.
- **Headline:** Loyalty that travels with the customer
- Wedge: mid-market retail chains
- Model: SaaS plus transaction fees

# Slide 2: Problem
Retailers lose repeat buyers because loyalty programs are fragmented.
- Points expire across brands
- Redemption feels opaque
- Fraud erodes margin

# Slide 3: Solution
A shared ledger lets shoppers earn once and redeem anywhere in the network.
- Unified wallet for shoppers
- Real-time settlement for merchants
- API-first integration`;

describe("pitchDeckDocument", () => {
  it("detects standard slide headings", () => {
    expect(hasPitchDeckSlideHeadings(SAMPLE_DECK)).toBe(true);
    expect(hasPitchDeckSlideHeadings("# Product doc\n## Goals")).toBe(false);
  });

  it("parses every slide heading as its own section", () => {
    const parsed = parsePitchDeckDocument(
      SAMPLE_DECK,
      "Blockchain Loyalty Rewards Program",
    );

    expect(parsed.documentTitle).toBe("Blockchain Loyalty Rewards Program");
    expect(parsed.sections).toHaveLength(3);
    expect(parsed.sections[0].title).toBe("Slide 1: Company Purpose");
    expect(parsed.sections[1].title).toBe("Slide 2: Problem");
    expect(parsed.summary).toContain("blockchain backed loyalty");
  });

  it("extracts slide number and display title", () => {
    expect(parseSlideTitle("Slide 5: Market Opportunity", 4)).toEqual({
      slideNumber: "5",
      slideTitle: "Market Opportunity",
    });
  });

  it("parses slide body into paragraphs, bullets, and tables", () => {
    const body = `One narrative sentence.

| Layer | Sizing | Assumption |
| --- | --- | --- |
| TAM | $4B | Global retail loyalty spend |

- Bullet one
- Bullet two`;

    const parts = parseSlideBody(body);
    expect(parts.map((part) => part.kind)).toEqual([
      "paragraph",
      "table",
      "bullet",
    ]);
    expect(parts[0].text).toContain("narrative sentence");
    expect(parts[1].rows).toHaveLength(2);
    expect(parts[1].rows?.[0]).toEqual(["Layer", "Sizing", "Assumption"]);
    expect(parts[2].text).toContain("Bullet one");
  });

  it("sanitizes filenames for export", () => {
    expect(sanitizeFilename("Blockchain Loyalty Rewards!")).toBe(
      "blockchain-loyalty-rewards",
    );
  });
});

it("preserves empty cells and table headers for PowerPoint export", () => {
  const part = parseSlideBody(
    "| Metric | Current | Target |\n| --- | --- | --- |\n| Revenue | | TBD |",
  )[0];
  expect(part.rows).toEqual([
    ["Metric", "Current", "Target"],
    ["Revenue", "", "TBD"],
  ]);
});
