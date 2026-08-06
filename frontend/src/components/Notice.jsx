import { AlertCircle, CheckCircle2, X } from "lucide-react";

export default function Notice({ type = "info", message, onClose }) {
  if (!message) return null;
  return (
    <div className={`notice ${type}`}>
      {type === "error" ? <AlertCircle size={19} /> : <CheckCircle2 size={19} />}
      <span>{message}</span>
      {onClose && <button aria-label="Close" onClick={onClose}><X size={17} /></button>}
    </div>
  );
}

