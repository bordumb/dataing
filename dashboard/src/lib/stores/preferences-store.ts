import { create } from "zustand";

type Density = "comfortable" | "compact";

interface PreferencesState {
  density: Density;
  notifications: boolean;
  setDensity: (density: Density) => void;
  setNotifications: (value: boolean) => void;
}

export const usePreferencesStore = create<PreferencesState>((set) => ({
  density: "comfortable",
  notifications: true,
  setDensity: (density) => set({ density }),
  setNotifications: (notifications) => set({ notifications }),
}));
