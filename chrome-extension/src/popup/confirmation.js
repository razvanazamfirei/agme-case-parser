/**
 * Confirmation dialog management
 */

export const Confirmation = {
  show() {
    const caseData = Form.getData();

    UI.get(DOM.confirmationSummary).innerHTML = this._buildSummary(caseData);
    UI.showSection(DOM.confirmationPanel);
    UI.get(DOM.fillSubmitBtn).disabled = true;
    State.pendingSubmission = true;
  },

  hide() {
    UI.hideSection(DOM.confirmationPanel);
    UI.get(DOM.fillSubmitBtn).disabled = false;
    State.pendingSubmission = false;
  },

  _buildSummary(caseData) {
    const items = [
      { label: "Case ID", value: caseData.caseId },
      { label: "Date", value: caseData.date },
      {
        label: "Attending",
        value:
          caseData.attending || State.settings.defaultAttending || "(not set)",
        warning: !caseData.attending && !State.settings.defaultAttending,
      },
      { label: "ASA", value: caseData.asa },
      { label: "Anesthesia", value: caseData.anesthesia },
      { label: "Procedure", value: caseData.procedureCategory || "Other" },
    ];

    return items
      .map((item) => {
        const valueClass = item.warning
          ? "summary-value warning"
          : "summary-value";
        return `<div class="summary-item"><span class="summary-label">${item.label}:</span><span class="${valueClass}">${item.value || "--"}</span></div>`;
      })
      .join("");
  },
};
