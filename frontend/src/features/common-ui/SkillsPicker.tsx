import React, { useMemo, useState } from 'react';

interface SkillsPickerProps {
  availableSkills: string[];
  value: string[];
  onChange: (skills: string[]) => void;
  label?: string;
  disabled?: boolean;
  placeholder?: string;
}

export const SkillsPicker: React.FC<SkillsPickerProps> = ({
  availableSkills,
  value,
  onChange,
  label,
  disabled = false,
  placeholder = 'Search skills…',
}) => {
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return availableSkills;
    return availableSkills.filter((s) => s.toLowerCase().includes(q));
  }, [availableSkills, query]);

  const toggle = (skill: string) => {
    if (disabled) return;
    if (value.includes(skill)) {
      onChange(value.filter((s) => s !== skill));
    } else {
      onChange([...value, skill]);
    }
  };

  return (
    <div className="space-y-3">
      {label ? (
        <label className="block text-sm font-medium text-neutral900 dark:text-white">
          {label}
        </label>
      ) : null}

      {value.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {value.map((skill) => (
            <span
              key={skill}
              className="inline-flex items-center gap-1.5 rounded-full bg-neutral900 px-3 py-1 text-xs font-medium text-white dark:bg-white dark:text-neutral900"
            >
              {skill}
              {!disabled ? (
                <button
                  aria-label={`Remove ${skill}`}
                  className="ml-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full opacity-70 transition-opacity hover:opacity-100"
                  onClick={() => toggle(skill)}
                  type="button"
                >
                  ×
                </button>
              ) : null}
            </span>
          ))}
        </div>
      ) : null}

      <input
        className="w-full rounded-xl border border-gray200 bg-white px-3.5 py-2 text-sm text-neutral900 placeholder-gray400 outline-none transition focus:border-neutral400 focus:ring-2 focus:ring-neutral900/10 disabled:opacity-50 dark:border-neutral700 dark:bg-neutral900 dark:text-white dark:placeholder-gray500"
        disabled={disabled}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder}
        type="text"
        value={query}
      />

      {filtered.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {filtered.map((skill) => {
            const selected = value.includes(skill);
            return (
              <button
                className={
                  selected
                    ? 'rounded-full bg-neutral900 px-3 py-1.5 text-xs font-medium text-white transition-colors dark:bg-white dark:text-neutral900'
                    : 'rounded-full border border-gray200 bg-white px-3 py-1.5 text-xs font-medium text-gray700 transition-colors hover:border-neutral400 hover:text-neutral900 disabled:cursor-not-allowed disabled:opacity-40 dark:border-neutral700 dark:bg-transparent dark:text-gray300'
                }
                disabled={disabled}
                key={skill}
                onClick={() => toggle(skill)}
                type="button"
              >
                {selected ? '✓ ' : ''}{skill}
              </button>
            );
          })}
        </div>
      ) : (
        <p className="text-xs text-gray400 dark:text-gray500">No skills match your search.</p>
      )}
    </div>
  );
};

export default SkillsPicker;
