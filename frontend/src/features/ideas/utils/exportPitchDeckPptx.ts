import pptxgen from 'pptxgenjs';
import {
  parsePitchDeckDocument,
  parseSlideBody,
  parseSlideTitle,
  sanitizeFilename,
  type ParsedSection,
} from './pitchDeckDocument';

const SLIDE_LAYOUT = 'LAYOUT_16x9';

const addSlideContent = (slide: pptxgen.Slide, section: ParsedSection) => {
  const { slideTitle } = parseSlideTitle(section.title, 0);
  const parts = parseSlideBody(section.body);
  let yPos = 1.05;

  slide.addText(slideTitle, {
    x: 0.6,
    y: 0.45,
    w: 8.8,
    h: 0.6,
    fontSize: 28,
    bold: true,
    color: '1A1A1A',
    fontFace: 'Arial',
  });

  parts.forEach((part) => {
    if (part.kind === 'paragraph' && part.text) {
      slide.addText(part.text, {
        x: 0.6,
        y: yPos,
        w: 8.8,
        h: 0.55,
        fontSize: 14,
        color: '444444',
        fontFace: 'Arial',
        valign: 'top',
      });
      yPos += 0.65;
      return;
    }

    if (part.kind === 'bullet' && part.text) {
      const bullets = part.text.split('\n').filter(Boolean);
      slide.addText(
        bullets.map((bullet) => ({ text: bullet, options: { bullet: true, breakLine: true } })),
        {
          x: 0.6,
          y: yPos,
          w: 8.8,
          h: Math.min(3.2, 0.35 * bullets.length + 0.2),
          fontSize: 13,
          color: '333333',
          fontFace: 'Arial',
          valign: 'top',
        },
      );
      yPos += Math.min(3.2, 0.35 * bullets.length + 0.35);
      return;
    }

    if (part.kind === 'table' && part.rows?.length) {
      const tableRows = part.rows.map((row) =>
        row.map((cell) => ({
          text: cell,
          options: { fontSize: 11, color: '333333', fontFace: 'Arial' },
        })),
      );

      slide.addTable(tableRows, {
        x: 0.6,
        y: yPos,
        w: 8.8,
        colW: Array(part.rows[0].length).fill(8.8 / part.rows[0].length),
        border: { type: 'solid', color: 'D6D1C4', pt: 1 },
        fill: { color: 'FFFFFF' },
        fontSize: 11,
      });
      yPos += Math.min(2.4, 0.35 * part.rows.length + 0.5);
    }
  });
};

export const buildPitchDeckPptx = (content: string, deckTitle?: string) => {
  const parsed = parsePitchDeckDocument(content, deckTitle);
  const presentation = new pptxgen();

  presentation.layout = SLIDE_LAYOUT;
  presentation.author = 'Manifest';
  presentation.title = parsed.documentTitle;

  parsed.sections.forEach((section) => {
    const slide = presentation.addSlide();
    slide.background = { color: 'FFFFFF' };
    addSlideContent(slide, section);
  });

  return presentation;
};

export const exportPitchDeckPptx = async (content: string, deckTitle?: string) => {
  const parsed = parsePitchDeckDocument(content, deckTitle);
  const presentation = buildPitchDeckPptx(content, deckTitle);
  const filename = `${sanitizeFilename(parsed.documentTitle)}-pitch-deck.pptx`;
  await presentation.writeFile({ fileName: filename });
};

export { parsePitchDeckDocument };
