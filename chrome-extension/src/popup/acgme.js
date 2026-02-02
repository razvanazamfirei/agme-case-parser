/**
 * ACGME form filling
 */

export const ACGMEForm = {
  async fill(andSubmit = false) {
    UI.hideStatus();
    const caseData = Form.getData();

    try {
      const [tab] = await chrome.tabs.query({
        active: true,
        currentWindow: true,
      });

      if (!tab.url?.includes(ACGME_URL_PATTERN)) {
        UI.showStatus("Navigate to ACGME Case Entry page first", "error");
        return;
      }

      const delayMs = Math.round(State.settings.submitDelay * 1000);
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: this._fillFormScript,
        args: [caseData, andSubmit, delayMs],
      });

      const result = results[0]?.result;
      this._handleFillResult(result, andSubmit);
    } catch (error) {
      UI.showStatus(error.message || "Error filling form", "error");
      console.error(error);
    }
  },

  _fillFormScript(data, submit, delay) {
    if (typeof window.fillACGMECase !== "function") {
      throw new Error("Content script not loaded. Refresh the ACGME page.");
    }

    const result = window.fillACGMECase(data);

    if (
      submit &&
      result?.success &&
      typeof window.submitACGMECase === "function"
    ) {
      return new Promise((resolve) => {
        setTimeout(() => {
          window.submitACGMECase();
          resolve({ ...result, submitted: true });
        }, delay);
      });
    }

    return { ...result, submitted: false };
  },

  _handleFillResult(result, andSubmit) {
    if (!result?.success) {
      if (result?.errors) {
        UI.showStatus(
          `Error filling form: ${result.errors.join("; ")}`,
          "error",
        );
      }
      return;
    }

    const warnings = result.warnings || [];
    const hasWarnings = State.settings.showWarnings && warnings.length > 0;

    if (hasWarnings) {
      console.warn("Fill warnings:", warnings);
    }

    if (andSubmit && result.submitted) {
      State.setCaseStatus(State.currentIndex, STATUS_TYPES.submitted);

      let msg = "Form filled and submitted!";
      if (hasWarnings) {
        msg += ` Warning: ${warnings.join("; ")}`;
      }

      UI.showStatus(msg, hasWarnings ? "info" : "success");
      Navigation.update();
      Storage.saveState();
      setTimeout(() => Navigation.goToNextPending(), 1000);
    } else {
      let msg = "Form filled! Review and submit on the ACGME page.";
      if (hasWarnings) {
        msg = `Form filled with warnings: ${warnings.join("; ")}`;
      }
      UI.showStatus(msg, "info");
    }
  },
};
