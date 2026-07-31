import { useEffect } from 'react';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';

import useAlertStore, { type AlertItem } from '../stores/alertStore';

const ICONS = { error: AlertCircle, success: CheckCircle2, notice: Info } as const;
const AUTO_DISMISS_MS = 5000;

function Alert({ alert }: { alert: AlertItem }) {
  const removeAlert = useAlertStore((state) => state.removeAlert);
  useEffect(() => {
    const timer = window.setTimeout(() => removeAlert(alert.id), AUTO_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [alert.id, removeAlert]);
  const Icon = ICONS[alert.type];
  return (
    <div className={`alert-toast ${alert.type}`} role="status">
      <Icon size={15} />
      <span>{alert.title}</span>
      <button onClick={() => removeAlert(alert.id)} aria-label="Dismiss"><X size={13} /></button>
    </div>
  );
}

/** Stacked toast area (langflow's alert display), rendered once at app root. */
export default function AlertDisplayArea() {
  const alerts = useAlertStore((state) => state.alerts);
  if (!alerts.length) return null;
  return <div className="alert-stack">{alerts.map((alert) => <Alert key={alert.id} alert={alert} />)}</div>;
}
