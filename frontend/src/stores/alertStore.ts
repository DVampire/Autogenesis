import { create } from 'zustand';

// Ported (simplified) from langflow's stores/alertStore.ts: a queue of typed
// alerts rendered by src/alerts as stacked toasts.

export type AlertType = 'error' | 'notice' | 'success';
export interface AlertItem { id: string; type: AlertType; title: string; }

let alertSequence = 0;

interface AlertStore {
  alerts: AlertItem[];
  notify: (title: string, type?: AlertType) => void;
  setErrorData: (data: { title: string }) => void;
  setSuccessData: (data: { title: string }) => void;
  removeAlert: (id: string) => void;
}

const useAlertStore = create<AlertStore>((set, get) => ({
  alerts: [],
  notify: (title, type = 'notice') => {
    if (!title.trim()) return;
    const last = get().alerts[get().alerts.length - 1];
    if (last && last.title === title && last.type === type) return; // dedupe bursts
    alertSequence += 1;
    set({ alerts: [...get().alerts.slice(-4), { id: `alert-${alertSequence}`, type, title }] });
  },
  setErrorData: ({ title }) => get().notify(title, 'error'),
  setSuccessData: ({ title }) => get().notify(title, 'success'),
  removeAlert: (id) => set({ alerts: get().alerts.filter((alert) => alert.id !== id) }),
}));

export default useAlertStore;
