/**
 * Form manipulation and data handling
 */

import { DOM } from "./constants.js";
import { State } from "./state.js";
import { UI } from "./ui.js";

export const Form = {
  setSelect(selectId, value) {
    const select = UI.get(selectId);
    if (!select || !value) {
      if (select) {
        select.value = "";
      }
      return { type: "none", original: value };
    }

    const options = [...select.options];

    // Exact match
    if (options.some((opt) => opt.value === value)) {
      select.value = value;
      return { type: "exact", original: value, matched: value };
    }

    // Case-insensitive match
    const valueLower = value.toLowerCase();
    const caseInsensitive = options.find(
      (opt) => opt.value.toLowerCase() === valueLower,
    );
    if (caseInsensitive) {
      select.value = caseInsensitive.value;
      return {
        type: "exact",
        original: value,
        matched: caseInsensitive.value,
      };
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
      return { type: "partial", original: value, matched: partial.value };
    }

    select.value = "";
    return { type: "none", original: value };
  },

  setCheckboxGroup(name, valuesString) {
    const checkboxes = document.querySelectorAll(`input[name="${name}"]`);
    const matchInfo = { exact: [], partial: [], unmatched: [] };

    checkboxes.forEach((cb) => {
      cb.checked = false;
    });

    if (!valuesString) {
      return { type: "none", matches: matchInfo };
    }

    const values = valuesString.split(";").map((v) => v.trim().toLowerCase());

    checkboxes.forEach((cb) => {
      const cbValue = cb.value.toLowerCase();
      const exactMatch = values.find((v) => v === cbValue);
      const partialMatch = values.find(
        (v) => cbValue.includes(v) || v.includes(cbValue),
      );

      if (exactMatch) {
        cb.checked = true;
        matchInfo.exact.push({ original: exactMatch, matched: cb.value });
      } else if (partialMatch) {
        cb.checked = true;
        matchInfo.partial.push({ original: partialMatch, matched: cb.value });
      }
    });

    // Track unmatched values
    const matchedOriginals = [
      ...matchInfo.exact.map((m) => m.original),
      ...matchInfo.partial.map((m) => m.original),
    ];
    matchInfo.unmatched = values.filter((v) => !matchedOriginals.includes(v));

    const hasPartial = matchInfo.partial.length > 0;
    const hasExact = matchInfo.exact.length > 0;

    if (hasExact) {
      return {
        type: hasPartial ? "partial" : "exact",
        matches: matchInfo,
      };
    } else {
      return {
        type: hasPartial ? "partial" : "none",
        matches: matchInfo,
      };
    }
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

    // Clear all match badges first
    UI.clearMatchBadges();

    UI.get(DOM.caseId).value = caseData.caseId || "";
    UI.get(DOM.date).value = caseData.date || "";
    UI.get(DOM.attending).value = caseData.attending || "";
    UI.get(DOM.comments).value = caseData.comments || "";

    const ageCategoryMatch = this.setSelect(
      DOM.ageCategory,
      caseData.ageCategory,
    );
    const asaMatch = this.setSelect(DOM.asa, caseData.asa);
    const anesthesiaMatch = this.setSelect(DOM.anesthesia, caseData.anesthesia);
    const procedureCategoryMatch = this.setSelect(
      DOM.procedureCategory,
      caseData.procedureCategory,
    );

    const airwayMatch = this.setCheckboxGroup("airway", caseData.airway);
    const vascularMatch = this.setCheckboxGroup(
      "vascular",
      caseData.vascularAccess,
    );
    const monitoringMatch = this.setCheckboxGroup(
      "monitoring",
      caseData.monitoring,
    );

    // Show match badges for partial matches
    UI.showMatchBadge(DOM.ageCategory, ageCategoryMatch);
    UI.showMatchBadge(DOM.asa, asaMatch);
    UI.showMatchBadge(DOM.anesthesia, anesthesiaMatch);
    UI.showMatchBadge(DOM.procedureCategory, procedureCategoryMatch);

    this.setRadioGroup("difficultAirway", caseData.difficultAirway || "");
    this.setRadioGroup(
      "lifeThreateningPathology",
      caseData.lifeThreateningPathology || "",
    );

    this._apply5ELogic(caseData);
    this._updateStatusBadge();
  },

  _apply5ELogic(caseData) {
    const isFiveE = caseData.asa?.toString().toUpperCase() === "5E";
    if (
      State.settings.auto5EPathology &&
      isFiveE &&
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

  validate() {
    const missing = [];
    const warnings = [];

    const data = this.getData();
    const hasAttending = data.attending || State.settings.defaultAttending;

    if (!hasAttending) {
      missing.push("Attending");
    }
    if (!data.asa) {
      missing.push("ASA");
    }
    if (!data.anesthesia) {
      missing.push("Anesthesia Type");
    }
    if (!data.procedureCategory) {
      warnings.push("Procedure Category");
    }

    return {
      isValid: missing.length === 0,
      missing,
      warnings,
      hasWarnings: warnings.length > 0,
    };
  },
};
