import React, { useId } from "react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  className?: string;
}

const Input: React.FC<InputProps> = ({
  label,
  error,
  value,
  onChange,
  placeholder,
  type = "text",
  className = "",
  ...props
}) => {
  const generatedId = useId();
  const inputId = props.id || generatedId;
  const errorId = `${inputId}-error`;

  return (
    <div className="min-w-0 flex-1 space-y-2">
      {label ? (
        <label htmlFor={inputId} className="manifest-label">
          {label}
        </label>
      ) : null}
      <input
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className={`manifest-field ${className}`}
        {...props}
        id={inputId}
        aria-invalid={error ? true : props["aria-invalid"]}
        aria-describedby={[props["aria-describedby"], error ? errorId : undefined].filter(Boolean).join(" ") || undefined}
      />
      {error ? <p id={errorId} className="text-sm text-red-600 dark:text-red-400">{error}</p> : null}
    </div>
  );
};

export default Input;
