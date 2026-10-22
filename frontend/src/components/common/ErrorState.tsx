import { CircleHelp } from "lucide-react";

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="error-state">
      <CircleHelp size={18} />
      <span>{message}</span>
    </div>
  );
}
