import React, { useEffect, useMemo } from "react";
import { MarkdownDisplay } from "./MarkdownDisplay";
import "./documents.css";
import { useMessage } from "features/notifications/context/MessageContext";
import {
  DocumentGenerationNotice,
  type DocumentGenerationState,
} from "./DocumentGenerationNotice";

interface CostStructureDisplayProps {
  cost: any;
  generationState?: DocumentGenerationState | null;
}

interface CostDriver {
  category: string;
  detail?: string;
  group?: string;
  highlights?: string[];
  title: string;
}

const categoryRules = [
  {
    category: "Production",
    keywords: [
      "manufacturing",
      "materials",
      "raw material",
      "production",
      "hardware",
      "component",
      "assembly",
      "tooling",
      "inventory",
    ],
  },
  {
    category: "Product & Engineering",
    keywords: [
      "engineering",
      "development",
      "design",
      "prototype",
      "research",
      "software",
      "product",
      "model training",
    ],
  },
  {
    category: "People",
    keywords: [
      "founder",
      "hiring",
      "sales",
      "customer success",
      "support",
      "team",
      "consultant",
      "payroll",
      "salary",
    ],
  },
  {
    category: "Infrastructure",
    keywords: [
      "cloud",
      "hosting",
      "compute",
      "storage",
      "api",
      "integration",
      "tooling",
      "platform",
    ],
  },
  {
    category: "Go-To-Market",
    keywords: [
      "marketing",
      "ads",
      "acquisition",
      "channel",
      "partnership",
      "outbound",
      "campaign",
    ],
  },
  {
    category: "Legal & Compliance",
    keywords: [
      "legal",
      "compliance",
      "security",
      "audit",
      "insurance",
      "privacy",
    ],
  },
];

const titleize = (value: string) =>
  value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
    .trim();

const stripMarkdownSyntax = (value: string) =>
  value
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/\[(.*?)\]\(.*?\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/[*_>#]/g, "")
    .replace(/\s+/g, " ")
    .trim();

const dedupe = (values: string[]) =>
  Array.from(new Set(values.filter(Boolean)));

const extractHighlights = (value: string) => {
  const normalized = stripMarkdownSyntax(value);
  const currencyMatches =
    normalized.match(
      /\$\s?\d[\d,]*(?:\.\d+)?(?:\s*(?:-|to)\s*\$?\s?\d[\d,]*(?:\.\d+)?)?(?:\s*(?:\/|per)\s*(?:month|mo|year|yr|week|wk|day|unit|seat|employee|customer))?/gi,
    ) || [];
  const percentageMatches =
    normalized.match(/\b\d+(?:\.\d+)?%\b(?:\s+of\s+[a-z][a-z\s-]*)?/gi) || [];

  return dedupe(
    [...currencyMatches, ...percentageMatches].map((match) =>
      match.replace(/\s+/g, " ").trim(),
    ),
  ).slice(0, 3);
};

const classifyCostItem = (value: string) => {
  const normalized = stripMarkdownSyntax(value).toLowerCase();
  const match = categoryRules.find((rule) =>
    rule.keywords.some((keyword) => normalized.includes(keyword)),
  );
  return match?.category || "Operations";
};

const buildCostDriver = ({
  title,
  detail,
  group,
}: {
  title: string;
  detail?: string;
  group?: string;
}): CostDriver | null => {
  const normalizedTitle = stripMarkdownSyntax(title).replace(/:$/, "").trim();
  const normalizedDetail = detail ? stripMarkdownSyntax(detail) : undefined;

  if (!normalizedTitle) {
    return null;
  }

  return {
    category: classifyCostItem(
      [normalizedTitle, normalizedDetail, group].filter(Boolean).join(" "),
    ),
    detail: normalizedDetail,
    group: group ? stripMarkdownSyntax(group) : undefined,
    highlights: extractHighlights(
      [normalizedTitle, normalizedDetail].filter(Boolean).join(" "),
    ),
    title: normalizedTitle,
  };
};

const structuredCostKeyPattern =
  /^(estimate|estimated[_\s-]?cost|estimated[_\s-]?range|amount|range|monthly|annual|yearly|one[_\s-]?time|detail|details|description|notes|share|percentage|budget|rationale)$/i;

const isStructuredCostObject = (value: Record<string, unknown>) =>
  Object.entries(value).some(
    ([key, nestedValue]) =>
      structuredCostKeyPattern.test(key) && typeof nestedValue !== "object",
  );

const composeStructuredDetail = (value: Record<string, unknown>) =>
  Object.entries(value)
    .flatMap(([key, nestedValue]) => {
      if (nestedValue == null || typeof nestedValue === "object") {
        return [];
      }

      const normalizedValue = String(nestedValue).trim();
      if (!normalizedValue) {
        return [];
      }

      if (/^(details?|description|notes?|rationale)$/i.test(key)) {
        return [normalizedValue];
      }

      return [`${titleize(key)}: ${normalizedValue}`];
    })
    .join(". ");

const parseMaybeJson = (value: unknown): unknown => {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try {
        return parseMaybeJson(JSON.parse(trimmed));
      } catch {
        return value;
      }
    }

    return value;
  }

  if (Array.isArray(value)) {
    return value.map((item) => parseMaybeJson(item));
  }

  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(
        ([key, nestedValue]) => [key, parseMaybeJson(nestedValue)],
      ),
    );
  }

  return value;
};

const flattenObjectCost = (
  value: unknown,
  group: string | undefined,
  drivers: CostDriver[],
) => {
  if (!value) {
    return;
  }

  if (typeof value === "string") {
    const driver = buildCostDriver({ title: value, group });
    if (driver) {
      drivers.push(driver);
    }
    return;
  }

  if (Array.isArray(value)) {
    value.forEach((item) => flattenObjectCost(item, group, drivers));
    return;
  }

  if (typeof value === "object") {
    Object.entries(value as Record<string, unknown>).forEach(
      ([key, nestedValue]) => {
        if (typeof nestedValue === "string") {
          const driver = buildCostDriver({
            title: titleize(key),
            detail: nestedValue,
            group,
          });
          if (driver) {
            drivers.push(driver);
          }
          return;
        }

        if (typeof nestedValue === "number") {
          const driver = buildCostDriver({
            title: titleize(key),
            detail: `${nestedValue}`,
            group,
          });
          if (driver) {
            drivers.push(driver);
          }
          return;
        }

        if (
          nestedValue &&
          typeof nestedValue === "object" &&
          !Array.isArray(nestedValue) &&
          isStructuredCostObject(nestedValue as Record<string, unknown>)
        ) {
          const driver = buildCostDriver({
            title: titleize(key),
            detail: composeStructuredDetail(
              nestedValue as Record<string, unknown>,
            ),
            group,
          });
          if (driver) {
            drivers.push(driver);
          }
          return;
        }

        flattenObjectCost(nestedValue, titleize(key), drivers);
      },
    );
  }
};

const parseStructuredLine = (
  text: string,
  group: string,
): CostDriver | null => {
  const cleanedText = text.trim();
  if (!cleanedText) {
    return null;
  }

  const emphasizedMatch = cleanedText.match(/^\*\*(.+?)\*\*\s*:?\s*(.+)$/);
  if (emphasizedMatch) {
    return buildCostDriver({
      title: emphasizedMatch[1],
      detail: emphasizedMatch[2],
      group,
    });
  }

  const colonIndex = cleanedText.indexOf(":");
  if (colonIndex > 0 && colonIndex < 90) {
    return buildCostDriver({
      title: cleanedText.slice(0, colonIndex),
      detail: cleanedText.slice(colonIndex + 1),
      group,
    });
  }

  return buildCostDriver({ title: cleanedText, group });
};

const parseMarkdownTableCost = (markdown: string): CostDriver[] => {
  const lines = markdown
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("|"));

  if (lines.length < 3) {
    return [];
  }

  const [headerLine, separatorLine, ...dataLines] = lines;
  if (!/^\|\s*[:\-| ]+\|?$/.test(separatorLine)) {
    return [];
  }

  const headers = headerLine
    .split("|")
    .map((cell) => stripMarkdownSyntax(cell))
    .filter(Boolean)
    .map((cell) => cell.toLowerCase());

  const titleIndex = headers.findIndex((header) =>
    /(item|driver|category|cost|name)/i.test(header),
  );
  const detailIndex = headers.findIndex((header) =>
    /(detail|description|note|rationale)/i.test(header),
  );
  const estimateIndex = headers.findIndex((header) =>
    /(estimate|amount|range|budget)/i.test(header),
  );

  if (titleIndex === -1) {
    return [];
  }

  return dataLines
    .map((line) =>
      line
        .split("|")
        .map((cell) => stripMarkdownSyntax(cell))
        .filter(Boolean),
    )
    .filter((cells) => cells.length > titleIndex)
    .map((cells) => {
      const estimate = estimateIndex >= 0 ? cells[estimateIndex] : "";
      const detail = detailIndex >= 0 ? cells[detailIndex] : "";
      return buildCostDriver({
        title: cells[titleIndex],
        detail: [estimate, detail].filter(Boolean).join(". "),
        group: "Primary Cost Drivers",
      });
    })
    .filter((driver): driver is CostDriver => Boolean(driver));
};

const parseMarkdownCost = (markdown: string): CostDriver[] => {
  const tableDrivers = parseMarkdownTableCost(markdown);
  if (tableDrivers.length > 0) {
    return tableDrivers;
  }

  const drivers: CostDriver[] = [];
  const fallbackLines: string[] = [];
  let currentGroup = "Primary cost drivers";

  markdown
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .forEach((line) => {
      const headingMatch = line.match(/^#+\s+(.+)$/);
      if (headingMatch) {
        currentGroup = stripMarkdownSyntax(headingMatch[1].trim());
        return;
      }

      const bulletMatch = line.match(/^[-*]\s+(.+)$/);
      const orderedMatch = line.match(/^\d+\.\s+(.+)$/);
      const text = bulletMatch?.[1] || orderedMatch?.[1] || line;

      if (
        bulletMatch ||
        orderedMatch ||
        /^\*\*(.+?)\*\*/.test(text) ||
        /^[^:]{2,80}:\s+.+$/.test(text)
      ) {
        const driver = parseStructuredLine(text, currentGroup);
        if (driver) {
          drivers.push(driver);
        }
        return;
      }

      fallbackLines.push(text);
    });

  if (drivers.length > 0) {
    return drivers;
  }

  return fallbackLines
    .map((line) => parseStructuredLine(line, currentGroup))
    .filter((driver): driver is CostDriver => Boolean(driver));
};

const parseCostData = (cost: unknown) => {
  if (cost == null) {
    return { drivers: [] as CostDriver[], parseError: false };
  }

  if (typeof cost === "string") {
    try {
      const parsed = parseMaybeJson(JSON.parse(cost));
      const drivers: CostDriver[] = [];
      flattenObjectCost(parsed, undefined, drivers);
      return { drivers, parseError: false };
    } catch {
      return { drivers: parseMarkdownCost(cost), parseError: false };
    }
  }

  if (typeof cost === "object") {
    const drivers: CostDriver[] = [];
    flattenObjectCost(parseMaybeJson(cost), undefined, drivers);
    return { drivers, parseError: false };
  }

  return { drivers: [], parseError: true };
};

export const CostStructureDisplay: React.FC<CostStructureDisplayProps> = ({
  cost,
  generationState,
}) => {
  const { setMessage } = useMessage();

  const { drivers, parseError } = useMemo(() => parseCostData(cost), [cost]);

  useEffect(() => {
    if (parseError) {
      setMessage("Failed to parse cost structure data.", "error");
    }
  }, [parseError, setMessage]);

  if (parseError) {
    return null;
  }

  // Render worksheets verbatim so cadence, currencies, assumptions and totals survive.
  if (typeof cost === "string" && /^\s*\|.+\|\s*$/m.test(cost)) {
    return (
      <MarkdownDisplay
        content={cost}
        fallbackMessage="No costs yet."
        title="Cost Structure"
        generationState={generationState}
      />
    );
  }

  if (drivers.length === 0) {
    if (generationState) {
      return (
        <DocumentGenerationNotice
          state={generationState}
          title="Cost Structure"
          variant="cost-structure"
        />
      );
    }

    return (
      <div className="rounded-[28px] border border-dashed border-stone-300 bg-stone-50 px-6 py-10 text-center dark:border-neutral700 dark:bg-neutral900/60">
        <h3 className="text-xl font-semibold tracking-tight text-neutral900 dark:text-white">
          Cost Structure
        </h3>
        <p className="mt-2 text-sm leading-6 text-gray500 dark:text-gray400">
          Cost drivers will appear here once the business model canvas has
          enough detail to infer the operating model.
        </p>
      </div>
    );
  }

  return (
    <div className="manifest-costs">
      {generationState && (
        <DocumentGenerationNotice
          layout="inline"
          state={generationState}
          title="Cost Structure"
          variant="cost-structure"
        />
      )}
      <header className="manifest-document-header">
        <div>
          <h3>Cost Structure</h3>
          <p>
            Planning estimates · Validate amounts and periods before budgeting
          </p>
        </div>
      </header>
      <div
        className="manifest-document-table"
        tabIndex={0}
        role="region"
        aria-label="Cost worksheet"
      >
        <table>
          <thead>
            <tr>
              <th scope="col">Cost driver</th>
              <th scope="col">Category</th>
              <th scope="col">Estimate / basis</th>
            </tr>
          </thead>
          <tbody>
            {drivers.map((driver, index) => (
              <tr key={index}>
                <th scope="row">{driver.title}</th>
                <td>{driver.category}</td>
                <td>
                  {driver.detail || "Estimate and cadence not yet specified"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export const extractCostStructure = (
  bmcMarkdown: string | undefined | null,
): any => {
  if (!bmcMarkdown || typeof bmcMarkdown !== "string") {
    return null;
  }

  const lines = bmcMarkdown.split("\n");
  const start = lines.findIndex((line) =>
    /^#{1,6}\s+(?:\d+[.)]?\s*)?Cost Structure\s*#*\s*$/i.test(line),
  );
  if (start < 0) return null;
  const level = lines[start].match(/^#+/)![0].length;
  const end = lines.findIndex(
    (line, index) =>
      index > start &&
      /^(#{1,6})\s+/.test(line) &&
      line.match(/^#+/)![0].length <= level,
  );
  return (
    lines
      .slice(start + 1, end < 0 ? undefined : end)
      .join("\n")
      .trim() || null
  );
};
