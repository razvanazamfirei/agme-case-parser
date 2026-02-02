/**
 * Form manipulation and data handling
 */

export const Form = {
  setSelect(selectId, value) {
    const select = UI.get(selectId);
    if (!select || !value) {
      if (select) {
        select.value = "";
      }
      return;
    }

    const options = [...select.options];

    // Exact match
    if (options.some((opt) => opt.value === value)) {
      select.value = value;
      return;
    }

    // Case-insensitive match
    const valueLower = value.toLowerCase();
    const caseInsensitive = options.find(
      (opt) => opt.value.toLowerCase() === valueLower,
    );
    if (caseInsensitive) {
      select.value = caseInsensitive.value;
      return;
    }

    // Partial match
    const partial = options.find(
      (opt) =>
        opt.value &&
        (valueLower.startsWith(opt.value.toLowerCase()) ||
          opt.value.toLowerCase().startsWith(valueLower)),
    );
    if (partial) {
      select.value = partial.value;
      return;
    }

    select.value = "";
  },

  setCheckboxGroup(name, valuesString) {
    const checkboxes = document.querySelectorAll(`input[name="${name}"]`);

    checkboxes.forEach((cb) => {
      cb.checked = false;
    });

    if (!valuesString) {
      return;
    }

    const values = valuesString.split(";").map((v) => v.trim().toLowerCase());

    checkboxes.forEach((cb) => {
      const cbValue = cb.value.toLowerCase();
      const matches = values.some(
        (v) => v === cbValue || cbValue.includes(v) || v.includes(cbValue),
      );
      if (matches) {
        cb.checked = true;
      }
    });
  },

  getCheckboxGroup(name) {
    const checked = [];
    document.querySelectorAll(`input[name="${name}"]:checked`).forEach((cb) => {
      checked.push(cb.value);
    });
    return checked.join("; ");
  },

  setRadioGroup(name, value) {
    if (!value) {
      const emptyRadio = document.querySelector(
        `input[name="${name}"][value=""]`,
      );
      if (emptyRadio) {
        emptyRadio.checked = true;
      }
      return;
    }

    document.querySelectorAll(`input[name="${name}"]`).forEach((radio) => {
      if (radio.value === value) {
        radio.checked = true;
      }
    });
  },

  getRadioGroup(name) {
    const checked = document.querySelector(`input[name="${name}"]:checked`);
    return checked ? checked.value : "";
  },

  populate(caseData) {
    if (!caseData) {
      return;
    }

    UI.get(DOM.caseId).value = caseData.caseId || "";
    UI.get(DOM.date).value = caseData.date || "";
    UI.get(DOM.attending).value = caseData.attending || "";
    UI.get(DOM.comments).value = caseData.comments || "";

    this.setSelect(DOM.ageCategory, caseData.ageCategory);
    this.setSelect(DOM.asa, caseData.asa);
    this.setSelect(DOM.anesthesia, caseData.anesthesia);
    this.setSelect(DOM.procedureCategory, caseData.procedureCategory);

    this.setCheckboxGroup("airway", caseData.airway);
    this.setCheckboxGroup("vascular", caseData.vascularAccess);
    this.setCheckboxGroup("monitoring", caseData.monitoring);

    this.setRadioGroup("difficultAirway", caseData.difficultAirway || "");
    this.setRadioGroup(
      "lifeThreateningPathology",
      caseData.lifeThreateningPathology || "",
    );

    this._apply5ELogic(caseData);
    this._updateStatusBadge();
  },

  _apply5ELogic(caseData) {
    const is5E = caseData.asa?.toString().toUpperCase() === "5E";
    if (
      State.settings.auto5EPathology &&
      is5E &&
      !caseData.lifeThreateningPathology
    ) {
      this.setRadioGroup("lifeThreateningPathology", "Non-Trauma");
    }
  },

  _updateStatusBadge() {
    const status = State.getCaseStatus(State.currentIndex);
    const badge = UI.get(DOM.caseStatus);
    badge.className = `status-badge ${status}`;
    badge.textContent = UI.capitalize(status);
  },

  getData() {
    return {
      caseId: UI.get(DOM.caseId).value,
      date: UI.get(DOM.date).value,
      attending: UI.get(DOM.attending).value,
      ageCategory: UI.get(DOM.ageCategory).value,
      asa: UI.get(DOM.asa).value,
      anesthesia: UI.get(DOM.anesthesia).value,
      airway: this.getCheckboxGroup("airway"),
      procedureCategory: UI.get(DOM.procedureCategory).value,
      vascularAccess: this.getCheckboxGroup("vascular"),
      monitoring: this.getCheckboxGroup("monitoring"),
      difficultAirway: this.getRadioGroup("difficultAirway"),
      lifeThreateningPathology: this.getRadioGroup("lifeThreateningPathology"),
      comments: UI.get(DOM.comments).value,
      institution: State.settings.defaultInstitution,
      defaultAttending: State.settings.defaultAttending,
      cardiacAutoFill: State.settings.cardiacAutoFill,
      auto5EPathology: State.settings.auto5EPathology,
      showWarnings: State.settings.showWarnings,
    };
  },
};
