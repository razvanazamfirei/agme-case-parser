/**
 * Settings management
 */

export const Settings = {
  readFromUI() {
    return {
      defaultInstitution: UI.get(DOM.settingInstitution).value,
      defaultAttending: UI.get(DOM.settingDefaultAttending).value.trim(),
      submitDelay: parseFloat(UI.get(DOM.settingSubmitDelay).value),
      cardiacAutoFill: UI.get(DOM.settingCardiacAutoFill).checked,
      auto5EPathology: UI.get(DOM.settingAuto5EPathology).checked,
      confirmBeforeSubmit: UI.get(DOM.settingConfirmBeforeSubmit).checked,
      showWarnings: UI.get(DOM.settingShowWarnings).checked,
    };
  },

  applyToUI() {
    UI.get(DOM.settingInstitution).value =
      State.settings.defaultInstitution || "";
    UI.get(DOM.settingDefaultAttending).value =
      State.settings.defaultAttending || "";
    UI.get(DOM.settingSubmitDelay).value = State.settings.submitDelay;
    UI.get(DOM.submitDelayValue).textContent = `${State.settings.submitDelay}s`;
    UI.get(DOM.settingCardiacAutoFill).checked = State.settings.cardiacAutoFill;
    UI.get(DOM.settingAuto5EPathology).checked =
      State.settings.auto5EPathology !== false;
    UI.get(DOM.settingConfirmBeforeSubmit).checked =
      State.settings.confirmBeforeSubmit !== false;
    UI.get(DOM.settingShowWarnings).checked =
      State.settings.showWarnings !== false;
  },

  async save() {
    try {
      const settings = this.readFromUI();
      await Storage.saveSettings(settings);
      UI.showStatus("Settings saved", "success");
      UI.hideSection(DOM.settingsSection);
    } catch (error) {
      UI.showStatus("Error saving settings", "error");
    }
  },

  toggle() {
    UI.toggleSection(DOM.settingsSection);
  },
};
