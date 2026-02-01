/**
 * Application initialization and event handlers
 */

const FileUpload = {
  async handleFile(file) {
    if (!file) {
      return;
    }

    UI.get(DOM.fileName).textContent = file.name;

    try {
      const cases = await Excel.parseFile(file);

      if (cases.length === 0) {
        UI.showStatus("No valid cases found in file", "error");
        return;
      }

      State.setCases(cases);
      Navigation.showCaseView();
      Form.populate(State.getCurrentCase());
      Navigation.update();
      Storage.saveState();
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
      UI.showStatus("Error clearing session", "error");
      console.error(error);
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
    // Upload
    UI.get(DOM.uploadBtn).addEventListener("click", () =>
      FileUpload.openFilePicker(),
    );
    UI.get(DOM.fileInput).addEventListener("change", (e) =>
      FileUpload.handleFile(e.target.files[0]),
    );

    // Navigation
    UI.get(DOM.prevBtn).addEventListener("click", () =>
      Navigation.goToCase(State.currentIndex - 1),
    );
    UI.get(DOM.nextBtn).addEventListener("click", () =>
      Navigation.goToCase(State.currentIndex + 1),
    );
    UI.get(DOM.caseJump).addEventListener("change", (e) =>
      Navigation.goToCase(parseInt(e.target.value, 10)),
    );
    UI.get(DOM.filterPending).addEventListener("change", () =>
      Navigation.update(),
    );

    // Actions
    UI.get(DOM.skipBtn).addEventListener("click", () => {
      State.setCaseStatus(State.currentIndex, STATUS_TYPES.skipped);
      Navigation.update();
      Storage.saveState();
      Navigation.goToNextPending();
    });

    UI.get(DOM.fillBtn).addEventListener("click", () => ACGMEForm.fill(false));

    UI.get(DOM.fillSubmitBtn).addEventListener("click", () => {
      if (!State.pendingSubmission) {
        if (State.settings.confirmBeforeSubmit) {
          Confirmation.show();
        } else {
          ACGMEForm.fill(true);
        }
      }
    });

    UI.get(DOM.cancelSubmitBtn).addEventListener("click", () =>
      Confirmation.hide(),
    );
    UI.get(DOM.confirmSubmitBtn).addEventListener("click", () => {
      Confirmation.hide();
      ACGMEForm.fill(true);
    });

    // Settings
    UI.get(DOM.settingsToggle).addEventListener("click", () =>
      Settings.toggle(),
    );
    UI.get(DOM.settingSubmitDelay).addEventListener("input", (e) => {
      UI.get(DOM.submitDelayValue).textContent = `${e.target.value}s`;
    });
    UI.get(DOM.saveSettingsBtn).addEventListener("click", () =>
      Settings.save(),
    );
    UI.get(DOM.clearSessionBtn).addEventListener("click", () =>
      Session.clear(),
    );

    // ASA field - auto-check 5E pathology
    UI.get(DOM.asa).addEventListener("change", (e) => {
      const is5E = e.target.value === "5E";
      const currentPathology = Form.getRadioGroup("lifeThreateningPathology");

      if (State.settings.auto5EPathology && is5E && !currentPathology) {
        Form.setRadioGroup("lifeThreateningPathology", "Non-Trauma");
      }
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
      } else if (e.key === "Escape" && State.pendingSubmission) {
        Confirmation.hide();
      }
    });
  },
};

const App = {
  async init() {
    await Storage.loadSettings();
    Settings.applyToUI();
    await Session.restore();
    EventHandlers.register();
  },
};

document.addEventListener("DOMContentLoaded", () => App.init());
