import React, { ButtonHTMLAttributes, ReactNode } from "react";
import type { Meta, StoryObj } from '@storybook/react-webpack5';

// Define the allowed variants for the button
type Variant = "primary" | "secondary" | "danger" | "disabled" | "navbar" | "dropdown";

// Define the props interface including standard button props
// TODO: Ask Mihir: Do we need to add any other attributes to this interface?
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: Variant;
  className?: string;
}

// A reusable Button component that supports multiple visual variants and standard props.
const ButtonComponent: React.FC<ButtonProps> = ({
  children,
  variant = "primary",
  className = "",
  ...props
}) => {
  // Define the base CSS classes for all button variants
  const baseClasses = "px-4 py-2 font-bold rounded focus:outline-none font-sans transition disabled:opacity-60 disabled:cursor-not-allowed";

  // Define variant-specific CSS classes
  // TODO: Ask Mihir: Are these the final color schemes for each variant?
  const variantClasses: Record<Variant, string> = {
    primary: "bg-primary text-background hover:bg-neutral800",
    secondary: "bg-gray200 text-primary hover:bg-gray300 border border-border",
    danger: "bg-danger text-background hover:bg-red-700",
    disabled: "bg-gray200 text-gray500 cursor-not-allowed border border-border",
    navbar: "bg-transparent text-neutral900 hover:bg-gray200 rounded-md px-3 py-2 font-semibold shadow-none border-none transition-colors",
    dropdown: "bg-background text-gray500 hover:bg-gray200 hover:text-primary w-full text-left px-4 py-2 font-normal rounded-none border-0 transition-colors text-sm",
  };

  // Debug log for props passed to Button
  // TODO: Ask Mihir: Do we need to log all props or just specific ones?
  logger.log("Button props:", { variant, className, ...props });

  // Combine base classes, selected variant classes, and any additional custom classes.
  // Disable the button if the 'disabled' variant is selected.
  // TODO: Ask Mihir: Should we handle the 'disabled' state differently?
  const classes = `${baseClasses} ${variantClasses[variant]} ${className}`;

  return (
    <button
      className={classes}
      disabled={variant === "disabled" || props.disabled}
      {...props}
    >
      {children}
    </button>
  );
};

const meta: Meta<typeof ButtonComponent> = {
  title: 'Common/Button',
  component: ButtonComponent,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['primary', 'secondary', 'danger', 'disabled', 'navbar', 'dropdown'],
    },
    children: {
      control: 'text',
    },
    disabled: {
      control: 'boolean',
    },
  },
};

export default meta;
type Story = StoryObj<typeof ButtonComponent>;

export const Primary: Story = {
  args: {
    variant: 'primary',
    children: 'Primary Button',
  },
};

export const Secondary: Story = {
  args: {
    variant: 'secondary',
    children: 'Secondary Button',
  },
};

export const Danger: Story = {
  args: {
    variant: 'danger',
    children: 'Danger Button',
  },
};

export const Disabled: Story = {
  args: {
    variant: 'disabled',
    children: 'Disabled Button',
  },
};

export const Navbar: Story = {
  args: {
    variant: 'navbar',
    children: 'Navbar Button',
  },
};

export const Dropdown: Story = {
  args: {
    variant: 'dropdown',
    children: 'Dropdown Button',
  },
};