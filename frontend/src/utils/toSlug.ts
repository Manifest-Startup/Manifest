export const toSlug = (input: string): string =>
  input
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '') // remove non-alphanumerics
    .replace(/\s+/g, '-')         // replace whitespace with dash
    .replace(/-+/g, '-');          // collapse multiple dashes 