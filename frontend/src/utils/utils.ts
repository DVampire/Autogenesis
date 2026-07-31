// Ported from langflow's utils/utils.ts.
import clsx, { type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function toTitleCase(text: string): string {
  return text.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
