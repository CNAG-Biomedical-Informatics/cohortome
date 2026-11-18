import { useId } from 'react';
import type { SelectHTMLAttributes } from 'react';

type SelectFieldProps = SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  inline?: boolean;
};

// Keep native keyboard navigation and option pickers. Views own the value;
// this component owns the accessible label and shared control presentation.
export function SelectField({ label, id, inline = false, children, ...props }: SelectFieldProps) {
  const generatedId = useId();
  const controlId = id || generatedId;
  return (
    <div className={`ui-select-field${inline ? ' ui-select-field--inline' : ''}`}>
      <label htmlFor={controlId}>{label}</label>
      <select {...props} id={controlId}>
        {children}
      </select>
    </div>
  );
}
