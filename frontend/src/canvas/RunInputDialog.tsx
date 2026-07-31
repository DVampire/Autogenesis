import { useState } from 'react';
import { Play } from 'lucide-react';

import { Button } from '../components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';

export interface RunInputField { name: string; type: string; required: boolean; value: string; }

/** Collects flow-input values before a run (shadcn Dialog from components/ui). */
export function RunInputDialog({ fields: initial, onCancel, onRun }: {
  fields: RunInputField[];
  onCancel: () => void;
  onRun: (input: Record<string, unknown>) => void;
}) {
  const [fields, setFields] = useState(initial);
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onCancel(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Flow inputs</DialogTitle>
          <DialogDescription>Values for this run; array/object fields accept JSON.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          {fields.map((field, index) => (
            <div className="grid gap-1.5" key={field.name}>
              <Label htmlFor={`run-input-${field.name}`}>
                {field.name}{field.required ? ' *' : ''} <span className="text-muted-foreground">({field.type})</span>
              </Label>
              <Textarea
                id={`run-input-${field.name}`}
                rows={field.type === 'array' || field.type === 'object' ? 3 : 1}
                value={field.value}
                placeholder={field.type === 'array' ? '["a", "b"]' : field.type === 'object' ? '{ }' : ''}
                onChange={(event) => setFields((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, value: event.target.value } : item))}
              />
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="primary" onClick={onCancel}>Cancel</Button>
          <Button onClick={() => {
            const input: Record<string, unknown> = {};
            for (const field of fields) {
              if (!field.value.trim()) continue;
              if (['array', 'object', 'number', 'boolean'].includes(field.type)) {
                try { input[field.name] = JSON.parse(field.value); } catch { input[field.name] = field.value; }
              } else input[field.name] = field.value;
            }
            onRun(input);
          }}><Play /> Run</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
