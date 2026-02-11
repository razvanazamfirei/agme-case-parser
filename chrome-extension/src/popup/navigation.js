/**
 * Case navigation logic
 */

import { DOM, STATUS_TYPES } from "./constants.js";
import { Form } from "./form.js";
import { State } from "./state.js";
import { Storage } from "./storage.js";
import { UI } from "./ui.js";

export const Navigation = {
  goToCase(index) {
    if (index < 0 || index >= State.cases.length) {
      return;
    }

    State.currentIndex = index;
    Form.populate(State.getCurrentCase());
    this.update();
    UI.hideStatus();
    // Disable Submit button when navigating to new case
    const submitBtn = UI.get(DOM.fillSubmitBtn);
    if (submitBtn) {
      submitBtn.disabled = true;
    }
    Storage.saveState();
  },

  goToNextPending() {
    const nextIndex = State.findNextPending(State.currentIndex);
    if (nextIndex === null) {
      UI.showStatus("All cases have been processed!", "success");
    } else {
      this.goToCase(nextIndex);
    }
  },

  update() {
    UI.get(DOM.currentIndex).textContent = (State.currentIndex + 1).toString();
    UI.get(DOM.totalCount).textContent = State.cases.length.toString();

    UI.get(DOM.prevBtn).disabled = State.currentIndex === 0;
    UI.get(DOM.nextBtn).disabled = State.currentIndex >= State.cases.length - 1;

    this._updateJumpDropdown();
    UI.updateStats();
  },

  _updateJumpDropdown() {
    const jumpSelect = UI.get(DOM.caseJump);
    const filterPending = UI.get(DOM.filterPending).checked;

    jumpSelect.innerHTML = "";

    for (let i = 0; i < State.cases.length; i++) {
      const status = State.getCaseStatus(i);
      if (filterPending && status !== STATUS_TYPES.pending) {
        continue;
      }

      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = `${i + 1}. ${State.cases[i].caseId} (${status})`;
      opt.selected = i === State.currentIndex;
      jumpSelect.appendChild(opt);
    }
  },

  showCaseView() {
    UI.hideSection(DOM.uploadSection);
    UI.showSection(DOM.navSection);
    UI.showSection(DOM.previewSection);
  },

  showUploadView() {
    UI.showSection(DOM.uploadSection);
    UI.hideSection(DOM.navSection);
    UI.hideSection(DOM.previewSection);
  },
};
