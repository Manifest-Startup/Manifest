import { knownIntegrationServiceIds } from 'features/account/lib/integrationsCatalog';

const BMC_SECTION_SPLIT_REGEX = /(?=^#{1,3}\s+)/gm;
const INTEGRATION_HINT_BLOCK_REGEX = /```bmc-key-partners-integrations\s*([\s\S]*?)```/i;

export interface ParsedBusinessModelCanvasSection {
  title: string;
  content: string;
  suggestedServiceIds: string[];
}

const normalizeServiceId = (value: unknown): string | null => {
  if (typeof value !== 'string') {
    return null;
  }

  const normalized = value.trim().toLowerCase();
  return normalized || null;
};

const isKeyPartnersSection = (title: string) => title.trim().toLowerCase() === 'key partners';

export const parseKeyPartnersIntegrationHints = (
  content: string,
): Pick<ParsedBusinessModelCanvasSection, 'content' | 'suggestedServiceIds'> => {
  const match = content.match(INTEGRATION_HINT_BLOCK_REGEX);
  const cleanContent = content.replace(INTEGRATION_HINT_BLOCK_REGEX, '').trim();

  if (!match) {
    return { content: cleanContent, suggestedServiceIds: [] };
  }

  try {
    const parsed = JSON.parse(match[1].trim()) as { suggestedServiceIds?: unknown };
    const rawIds: unknown[] = Array.isArray(parsed?.suggestedServiceIds) ? parsed.suggestedServiceIds : [];
    const suggestedServiceIds: string[] = Array.from(
      new Set(
        rawIds
          .map(normalizeServiceId)
          .filter((id): id is string => id !== null && knownIntegrationServiceIds.has(id)),
      ),
    );

    return {
      content: cleanContent,
      suggestedServiceIds,
    };
  } catch {
    return {
      content: cleanContent,
      suggestedServiceIds: [],
    };
  }
};

export const parseBusinessModelCanvasSections = (content: string): ParsedBusinessModelCanvasSection[] => {
  const sections = content.split(BMC_SECTION_SPLIT_REGEX).filter((section) => section.trim());

  return sections
    .map((section) => {
      const lines = section.split('\n').filter((line) => line.trim() || line === '');
      if (lines.length === 0) {
        return null;
      }

      let titleLineIndex = -1;
      let title = '';
      for (let i = 0; i < lines.length; i += 1) {
        if (lines[i].match(/^#{1,3}\s+/)) {
          titleLineIndex = i;
          title = lines[i].replace(/^#+\s*/, '').trim();
          break;
        }
      }

      if (titleLineIndex === -1) {
        return null;
      }

      const contentText = lines.slice(titleLineIndex + 1).join('\n').trim();
      if (!isKeyPartnersSection(title)) {
        return {
          title,
          content: contentText,
          suggestedServiceIds: [],
        };
      }

      const parsedKeyPartners = parseKeyPartnersIntegrationHints(contentText);
      return {
        title,
        content: parsedKeyPartners.content,
        suggestedServiceIds: parsedKeyPartners.suggestedServiceIds,
      };
    })
    .filter((section): section is ParsedBusinessModelCanvasSection => !!section);
};
