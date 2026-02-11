/**
 * Application initialization and event handlers
 */

import { ACGMEForm } from "./acgme.js";
import { DOM, STATUS_TYPES } from "./constants.js";
import { Excel } from "./excel.js";
import { Form } from "./form.js";
import { Navigation } from "./navigation.js";
import { Settings } from "./settings.js";
import { State } from "./state.js";
import { Storage } from "./storage.js";
import { UI } from "./ui.js";

const FileUpload = {
  async handleFile(file) {
    if (!file) {
      return;
    }

    UI.get(DOM.fileName).textContent = file.name;

    try {
      const result = await Excel.parseFile(file);
      const { cases, mappingResult } = result;

      if (cases.length === 0) {
        UI.showStatus("No valid cases found in file", "error");
        return;
      }

      State.setCases(cases);
      Navigation.showCaseView();
      Form.populate(State.getCurrentCase());
      Navigation.update();
      Storage.saveState();

      // Show mapping status
      UI.showMappingStatus(mappingResult);

      UI.showStatus(`Loaded ${cases.length} cases`, "success");
    } catch (error) {
      UI.showStatus(`Error parsing file: ${error.message}`, "error");
      console.error(error);
    }
  },

  openFilePicker() {
    UI.get(DOM.fileInput).click();
  },
};

const Session = {
  async clear() {
    if (
      !confirm("Clear all loaded cases and progress? This cannot be undone.")
    ) {
      return;
    }

    try {
      await Storage.clearState();
      Navigation.showUploadView();
      UI.get(DOM.fileName).textContent = "";
      UI.get(DOM.fileInput).value = "";
      UI.showStatus("Session cleared", "success");
    } catch (error) {
      console.error("Error clearing session:", error);
      UI.showStatus("Error clearing session", "error");
    }
  },

  async restore() {
    const restored = await Storage.loadState();
    if (restored) {
      Navigation.showCaseView();
      Form.populate(State.getCurrentCase());
      Navigation.update();
      UI.showStatus(
        `Restored ${State.cases.length} cases from previous session`,
        "info",
      );
    }
  },
};

const EventHandlers = {
  register() {
    const addListener = (id, event, handler) => {
      const element = UI.get(id);
      if (!element) {
        if (process.env.NODE_ENV === "development") {
          console.error(`Element not found: ${id}`);
        }
        return;
      }
      element.addEventListener(event, (...args) => {
        if (process.env.NODE_ENV === "development") {
          console.log(`Button clicked: ${id}`);
        }
        try {
          handler(...args);
        } catch (error) {
          console.error(`Error in ${id} handler:`, error);
        }
      });
    };

    // Upload
    addListener(DOM.uploadBtn, "click", () => FileUpload.openFilePicker());
    addListener(DOM.fileInput, "change", (e) =>
      FileUpload.handleFile(e.target.files[0]),
    );

    // Navigation
    addListener(DOM.prevBtn, "click", () =>
      Navigation.goToCase(State.currentIndex - 1),
    );
    addListener(DOM.nextBtn, "click", () =>
      Navigation.goToCase(State.currentIndex + 1),
    );
    addListener(DOM.caseJump, "change", (e) =>
      Navigation.goToCase(Number.parseInt(e.target.value, 10)),
    );
    addListener(DOM.filterPending, "change", () => Navigation.update());

    // Actions
    addListener(DOM.skipBtn, "click", () => {
      State.setCaseStatus(State.currentIndex, STATUS_TYPES.skipped);
      Navigation.update();
      Storage.saveState();
      Navigation.goToNextPending();
    });

    addListener(DOM.fillBtn, "click", async () => {
      const validation = Form.validate();
      if (!validation.isValid) {
        UI.showValidation(validation);
        UI.showStatus(
          "Please complete required fields before filling",
          "error",
        );
        return;
      }

      UI.get(DOM.fillBtn).disabled = true;
      try {
        const result = await ACGMEForm.fill(false);
        // Enable Submit only after a successful fill operation
        UI.get(DOM.fillSubmitBtn).disabled = !result?.success;
      } finally {
        UI.get(DOM.fillBtn).disabled = false;
      }
    });

    addListener(DOM.fillSubmitBtn, "click", async () => {
      const validation = Form.validate();
      if (!validation.isValid) {
        UI.showValidation(validation);
        UI.showStatus(
          "Please complete required fields before submitting",
          "error",
        );
        return;
      }
      UI.get(DOM.fillSubmitBtn).disabled = true;
      try {
        await ACGMEForm.fill(true);
      } finally {
        if (
          State.getCaseStatus(State.currentIndex) !== STATUS_TYPES.submitted
        ) {
          UI.get(DOM.fillSubmitBtn).disabled = false;
        }
      }
    });

    // Settings
    addListener(DOM.settingsToggle, "click", () => Settings.toggle());
    addListener(DOM.settingSubmitDelay, "input", (e) => {
      UI.get(DOM.submitDelayValue).textContent = `${e.target.value}s`;
    });
    addListener(DOM.saveSettingsBtn, "click", () => Settings.save());
    addListener(DOM.clearSessionBtn, "click", () => Session.clear());

    // ASA field - auto-check 5E pathology
    addListener(DOM.asa, "change", (e) => {
      const isFiveE = e.target.value === "5E";
      const currentPathology = Form.getRadioGroup("lifeThreateningPathology");

      if (State.settings.auto5EPathology && isFiveE && !currentPathology) {
        Form.setRadioGroup("lifeThreateningPathology", "Non-Trauma");
      }

      // Real-time validation
      const validation = Form.validate();
      UI.showValidation(validation);
    });

    // Real-time validation for other required fields
    const requiredFields = [
      DOM.attending,
      DOM.anesthesia,
      DOM.procedureCategory,
    ];
    requiredFields.forEach((fieldId) => {
      addListener(fieldId, "change", () => {
        const validation = Form.validate();
        UI.showValidation(validation);
      });
    });

    // Keyboard shortcuts
    document.addEventListener("keydown", (e) => {
      if (State.cases.length === 0) {
        return;
      }

      const isInputFocused = e.target.matches("input, textarea, select");

      if (e.key === "ArrowLeft" && !isInputFocused) {
        e.preventDefault();
        Navigation.goToCase(State.currentIndex - 1);
      } else if (e.key === "ArrowRight" && !isInputFocused) {
        e.preventDefault();
        Navigation.goToCase(State.currentIndex + 1);
      }
    });

    if (process.env.NODE_ENV === "development") {
      console.log("Event handlers registered successfully");
    }
  },
};

const App = {
  async init() {
    try {
      await Storage.loadSettings();
      Settings.applyToUI();
      await Session.restore();
      EventHandlers.register();
      if (process.env.NODE_ENV === "development") {
        console.log("ACGME Case Submitter initialized successfully");
      }
    } catch (error) {
      console.error("Error initializing app:", error);
    }
  },
};

// Handle both DOMContentLoaded and already-loaded cases
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => App.init());
} else {
  // DOM already loaded
  App.init();
}
