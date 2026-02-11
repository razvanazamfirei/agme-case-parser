/**
 * Persistence layer for state and settings
 */

import { STORAGE_KEYS } from "./constants.js";
import { State } from "./state.js";

export const Storage = {
  async loadState() {
    try {
      const result = await chrome.storage.local.get([
        STORAGE_KEYS.cases,
        STORAGE_KEYS.currentIndex,
        STORAGE_KEYS.caseStatuses,
      ]);

      if (result[STORAGE_KEYS.cases]?.length > 0) {
        State.cases = result[STORAGE_KEYS.cases];
        State.currentIndex = result[STORAGE_KEYS.currentIndex] || 0;
        State.caseStatuses = result[STORAGE_KEYS.caseStatuses] || {};

        if (State.currentIndex >= State.cases.length) {
          State.currentIndex = 0;
        }

        return true;
      }
      return false;
    } catch (error) {
      console.error("Error loading state:", error);
      return false;
    }
  },

  async saveState() {
    try {
      await chrome.storage.local.set({
        [STORAGE_KEYS.cases]: State.cases,
        [STORAGE_KEYS.currentIndex]: State.currentIndex,
        [STORAGE_KEYS.caseStatuses]: State.caseStatuses,
      });
    } catch (error) {
      console.error("Error saving state:", error);
    }
  },

  async clearState() {
    try {
      await chrome.storage.local.remove([
        STORAGE_KEYS.cases,
        STORAGE_KEYS.currentIndex,
        STORAGE_KEYS.caseStatuses,
      ]);
      State.reset();
    } catch (error) {
      console.error("Error clearing state:", error);
    }
  },

  async loadSettings() {
    try {
      const result = await chrome.storage.sync.get(STORAGE_KEYS.settings);
      if (result[STORAGE_KEYS.settings]) {
        State.settings = {
          ...State.settings,
          ...result[STORAGE_KEYS.settings],
        };
      }
    } catch (error) {
      console.error("Error loading settings:", error);
    }
  },

  async saveSettings(settings) {
    try {
      State.settings = settings;
      await chrome.storage.sync.set({ [STORAGE_KEYS.settings]: settings });
    } catch (error) {
      console.error("Error saving settings:", error);
      throw error;
    }
  },
};
