import { CircleHelp } from "lucide-react";
export function ErrorState({ message }) {
  return (
    <div className="error-state" role="alert">
      <CircleHelp size={18} aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}
