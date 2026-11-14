import { htmlToPlainText } from "../htmlToPlainText";

describe("htmlToPlainText", () => {
  test("returns empty for nullish or blank", () => {
    expect(htmlToPlainText(null)).toBe("");
    expect(htmlToPlainText(undefined)).toBe("");
    expect(htmlToPlainText("   ")).toBe("");
  });

  test("passes through plain text", () => {
    expect(htmlToPlainText("Hello world")).toBe("Hello world");
  });

  test("strips tags and collapses whitespace from HTML", () => {
    const html =
      "<p>Property management, software.</p> <h2>Voice Strategy</h2> " +
      "<p><strong>Working title:</strong> Student Housing</p>";
    const out = htmlToPlainText(html);
    expect(out).not.toMatch(/</);
    expect(out).toContain("Property management, software.");
    expect(out).toContain("Voice Strategy");
    expect(out).toContain("Working title:");
    expect(out).toContain("Student Housing");
  });
});
