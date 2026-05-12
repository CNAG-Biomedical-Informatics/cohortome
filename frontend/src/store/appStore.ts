import { create } from "zustand";

type AppState = {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  selectedDatasetIds: string[];
  setSelectedDatasetIds: (ids: string[]) => void;
  pendingDatasetIds: string[];
  setPendingDatasetIds: (ids: string[]) => void;
  selectedSavedCohortIds: string[];
  setSelectedSavedCohortIds: (ids: string[]) => void;
};

export const useAppStore = create<AppState>((set) => ({
  activeTab: "pheno",
  setActiveTab: (activeTab) => set({ activeTab }),
  selectedDatasetIds: [],
  setSelectedDatasetIds: (selectedDatasetIds) => set({ selectedDatasetIds }),
  pendingDatasetIds: [],
  setPendingDatasetIds: (pendingDatasetIds) => set({ pendingDatasetIds }),
  selectedSavedCohortIds: [],
  setSelectedSavedCohortIds: (selectedSavedCohortIds) => set({ selectedSavedCohortIds }),
}));
