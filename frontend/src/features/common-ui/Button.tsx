import React, { ButtonHTMLAttributes, ReactNode } from "react";

type Variant =
  | "primary"
  | "secondary"
  | "danger"
  | "disabled"
  | "navbar"
  | "dropdown"
  | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: Variant;
  className?: string;
}

const Button: React.FC<ButtonProps> = ({
  children,
  variant = "primary",
  className = "",
  ...props
}) => {
  const baseClasses = "manifest-control shrink-0 disabled:cursor-not-allowed disabled:opacity-50";
  const variantClasses: Record<Variant, string> = {
    primary: "manifest-control-primary",
    secondary: "manifest-control-secondary",
    danger: "bg-danger text-white hover:bg-red-700",
    disabled: "bg-theme-tertiary text-theme-tertiary border border-theme-primary",
    navbar: "manifest-control-ghost",
    dropdown: "manifest-control-ghost w-full justify-start text-left",
    ghost: "manifest-control-ghost",
  };

  const classes = `${baseClasses} ${variantClasses[variant]} ${className}`;

  return (
    <button className={classes} {...props} disabled={variant === "disabled" || props.disabled}>
      {children}
    </button>
  );
};

export default Button;
