/**
 * Utility for conditionally combining class names.
 *
 * Uses clsx for conditional logic and tailwind-merge for deduplication.
 */

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Combines class names with Tailwind CSS conflict resolution.
 *
 * @example
 * cn("px-2 py-1", "px-4") // => "py-1 px-4"
 * cn("text-red-500", condition && "text-blue-500")
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export default cn;
