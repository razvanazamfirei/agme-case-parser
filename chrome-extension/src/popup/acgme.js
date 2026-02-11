/**
 * ACGME form filling
 */

import { ACGME_URL_PATTERN, STATUS_TYPES } from "./constants.js";
import { Form } from "./form.js";
import { Navigation } from "./navigation.js";
import { State } from "./state.js";
import { Storage } from "./storage.js";
import { UI } from "./ui.js";

export const ACGMEForm = {
  async fill(andSubmit = false) {
    if (process.env.NODE_ENV === "development") {
      console.log("ACGMEForm.fill called, andSubmit:", andSubmit);
    }
    UI.hideStatus();
    const caseData = Form.getData();

    try {
      const [tab] = await chrome.tabs.query({
        active: true,
        currentWindow: true,
      });

      if (!tab?.id) {
        const result = {
          success: false,
          errors: ["Could not find the active browser tab."],
        };
        this._handleFillResult(result, andSubmit);
        return result;
      }

      if (!tab.url?.includes(ACGME_URL_PATTERN)) {
        UI.showStatus("Navigate to ACGME Case Entry page first", "error");
        return {
          success: false,
          errors: ["Active tab is not the ACGME Case Entry page."],
        };
      }

      // Send message to content script to fill the form
      const response = await new Promise((resolve) => {
        const message = {
          action: "fillCase",
          data: caseData,
          autoSubmit: false, // We'll handle submit separately with delay
        };

        chrome.tabs.sendMessage(tab.id, message, (response) => {
          if (chrome.runtime.lastError) {
            resolve({
              success: false,
              errors: [
                "Content script not loaded. Refresh the ACGME page and try again.",
              ],
            });
            return;
          }
          resolve(response);
        });
      });

      // Extract the actual result from the response
      const result = response?.success
        ? response.result
        : response || {
            success: false,
            errors: ["No response from the ACGME page content script."],
          };

      // If auto-submit is requested and fill was successful, submit after delay
      if (andSubmit && result?.success) {
        const delayMs = Math.round(State.settings.submitDelay * 1000);
        await new Promise((resolve) => setTimeout(resolve, delayMs));

        const submitResponse = await new Promise((resolve) => {
          chrome.tabs.sendMessage(
            tab.id,
            { action: "submitCase" },
            (response) => {
              if (chrome.runtime.lastError) {
                console.error("Error submitting:", chrome.runtime.lastError);
                resolve({
                  success: false,
                  errors: ["Submit command failed in the ACGME page."],
                });
                return;
              }
              resolve(response);
            },
          );
        });

        result.submitted = submitResponse?.success === true;
        if (!result.submitted) {
          const submitErrors = submitResponse?.errors || [
            "Form fill succeeded, but submit failed.",
          ];
          result.errors = [...(result.errors || []), ...submitErrors];
        }
      } else {
        result.submitted = false;
      }

      this._handleFillResult(result, andSubmit);
      return result;
    } catch (error) {
      console.error("Error in ACGMEForm.fill:", error);
      const result = {
        success: false,
        errors: [error.message || "Error filling form"],
      };
      this._handleFillResult(result, andSubmit);
      return result;
    }
  },

  _handleFillResult(result, andSubmit) {
    if (!result?.success) {
      if (result?.errors?.length > 0) {
        UI.showStatus(
          `Error filling form: ${result.errors.join("; ")}`,
          "error",
        );
      } else {
        UI.showStatus("Error filling form", "error");
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
