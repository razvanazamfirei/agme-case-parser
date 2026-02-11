/**
 * UI utilities and helpers
 */

import { DOM } from "./constants.js";
import { State } from "./state.js";

export const UI = {
  get(id) {
    return document.getElementById(id);
  },

  showStatus(msg, type = "info") {
    const section = this.get(DOM.statusSection);
    const message = this.get(DOM.statusMessage);

    section.classList.remove("hidden");
    message.className = `status-message ${type}`;
    message.textContent = msg;

    if (type === "success" || type === "info") {
      setTimeout(() => section.classList.add("hidden"), 3000);
    }
  },

  hideStatus() {
    this.get(DOM.statusSection).classList.add("hidden");
  },

  toggleSection(id) {
    this.get(id).classList.toggle("hidden");
  },

  showSection(id) {
    this.get(id).classList.remove("hidden");
  },

  hideSection(id) {
    this.get(id).classList.add("hidden");
  },

  updateStats() {
    const stats = State.getStats();
    this.get(DOM.pendingCount).textContent = stats.pending.toString();
    this.get(DOM.submittedCount).textContent = stats.submitted.toString();
    this.get(DOM.skippedCount).textContent = stats.skipped.toString();
  },

  capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
  },

  showValidation(validationResult) {
    const summary = this.get("validationSummary");
    const text = this.get("validationText");

    if (!validationResult.isValid || validationResult.hasWarnings) {
      const parts = [];
      if (validationResult.missing.length > 0) {
        parts.push(`Missing required: ${validationResult.missing.join(", ")}`);
      }
      if (validationResult.warnings.length > 0) {
        parts.push(`Recommended: ${validationResult.warnings.join(", ")}`);
      }
      text.textContent = parts.join(". ");
      summary.classList.remove("hidden");
    } else {
      summary.classList.add("hidden");
    }
  },

  hideValidation() {
    this.get("validationSummary").classList.add("hidden");
  },

  showMatchBadge(fieldId, matchInfo) {
    if (!matchInfo || matchInfo.type === "exact" || matchInfo.type === "none") {
      return;
    }

    const field = this.get(fieldId);
    if (!field) {
      return;
    }

    const parent = field.parentElement;
    let badge = parent.querySelector(".match-badge");

    if (!badge) {
      badge = document.createElement("span");
      badge.className = "match-badge";
      parent.appendChild(badge);
    }

    if (matchInfo.type === "partial") {
      badge.className = "match-badge partial";
      badge.textContent = "Partial";
      badge.title = `Original: "${matchInfo.original}" → Matched: "${matchInfo.matched}"`;
    }
  },

  clearMatchBadges() {
    document.querySelectorAll(".match-badge").forEach((badge) => {
      badge.remove();
    });
  },

  showMappingStatus(mappingResult) {
    const { totalMapped, totalExpected, missing } = mappingResult;

    if (totalMapped === totalExpected) {
      this.showStatus(
        `Column mapping: ${totalMapped}/${totalExpected} columns mapped`,
        "success",
      );
    } else {
      const missingList = missing.join(", ");
      this.showStatus(
        `Column mapping: ${totalMapped}/${totalExpected} mapped. Missing: ${missingList}`,
        "error",
      );
    }
  },
};
