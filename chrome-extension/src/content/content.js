// ACGME Case Entry Form Filler
// Maps standardized output from Python case-parser to ACGME form codes

// Patient age category mapping
const AGE_MAP = {
  a: "30",
  b: "31",
  c: "32",
  d: "33",
  e: "34",
};

// ASA Status codes
const ASA_MAP = {
  1: "156628",
  2: "156632",
  3: "156634",
  4: "156636",
  5: "156630",
  6: "156631",
  "1E": "156629",
  "2E": "156633",
  "3E": "156635",
  "4E": "156637",
  "5E": "156626",
};

// Anesthesia type codes
const ANESTHESIA_MAP = {
  GA: "1256330",
  MAC: "156641",
  Spinal: "1256331",
  Epidural: "1256332",
  CSE: "156646",
  "PNB Continuous": "156647",
  "PNB Single": "156648",
};

// Airway device codes (from Python tool output)
const AIRWAY_MAP = {
  "Oral ETT": "156654",
  ETT: "156654", // Alias for backwards compatibility
  "Nasal ETT": "156655",
  "Supraglottic Airway": "1256333",
  LMA: "1256333", // Alias for backwards compatibility
  Mask: "156650",
  DLT: "1256336",
};

// Laryngoscopy codes
const LARYNGOSCOPY_MAP = {
  "Direct Laryngoscope": "1256334",
  "Video Laryngoscope": "1256335",
  "Flexible Bronchoscopic": "2298046",
};

// Procedure category codes (matching Python tool output)
const PROCEDURE_CAT_MAP = {
  "Cardiac with CPB": "156681",
  "Cardiac without CPB": "156682",
  Cardiac: "156682", // Fallback when CPB status unknown
  "Procedures on major vessels (endovascular)": "156685",
  "Procedures on major vessels (open)": "156684",
  "Procedures Major Vessels": "156684",
  "Intracerebral (endovascular)": "156688",
  "Intracerebral Vascular (open)": "156687",
  "Intracerebral Nonvascular (open)": "156689",
  Intracerebral: "156687",
  "Cesarean del": "156692",
  Cesarean: "156692",
  "Vaginal del": "156690",
  "Vaginal Delivery": "156690",
  "Intrathoracic non-cardiac": "156683",
  Intrathoracic: "156683",
  "Other (procedure cat)": null, // Explicitly handled
};

// Vascular access codes (matching Python tool output)
const VASCULAR_MAP = {
  "Arterial Catheter": "1256338",
  "Central Venous Catheter": "1256339",
  "PA Catheter": "156700",
  "Ultrasound Guided": "156693",
};

// Monitoring codes (matching Python tool output)
const MONITORING_MAP = {
  TEE: "156707",
  Neuromonitoring: "156708",
  "CSF Drain": "1256341",
};

// Difficult Airway Management codes
const DIFFICULT_AIRWAY_MAP = {
  Anticipated: "148",
  Unanticipated: "149",
};

// Life-Threatening Pathology codes
const LIFE_THREATENING_PATHOLOGY_MAP = {
  "Non-Trauma": "46",
  Trauma: "134",
};

// Institution IDs
const INSTITUTION_MAP = {
  CHOP: "12763",
  "Penn Hospital": "12771",
  HUP: "12748",
  PPMC: "12871",
};

function getFieldId(type) {
  if (type === "caseId") {
    const el = document.querySelector('input[id^="7129"]');
    return el ? el.id : null;
  }
  if (type === "date") {
    const el = document.querySelector('input[id^="5b1c"]');
    return el ? el.id : null;
  }
  return null;
}

function setSelectValue(selectId, value) {
  const select = document.getElementById(selectId);
  if (!select) {
    console.warn("Select not found:", selectId);
    return false;
  }

  select.value = value;

  if (
    typeof $ !== "undefined" &&
    $(select).hasClass("select2-hidden-accessible")
  ) {
    $(select).val(value).trigger("change");
  } else {
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }
  return true;
}

function setInputValue(inputId, value) {
  const input = document.getElementById(inputId);
  if (!input) {
    console.warn("Input not found:", inputId);
    return false;
  }
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

function checkProcedure(codeId) {
  const input = document.getElementById(String(codeId));
  if (!input) {
    console.warn("Input element not found:", codeId);
    return false;
  }
  if (!input.checked) {
    input.click();
  }
  return input.checked;
}

function checkRadioProcedure(codeId) {
  const radio = document.getElementById(`CaseTypes_${codeId}`);
  if (!radio) {
    console.warn("Radio button not found:", `CaseTypes_${codeId}`);
    return false;
  }
  if (!radio.checked) {
    radio.click();
  }
  return radio.checked;
}

function uncheckAllProcedures() {
  document.querySelectorAll(".cbprocedureid:checked").forEach((cb) => {
    cb.click();
  });
}

// Attending lookup with high-confidence matching only
function findAttendingId(name, returnAllMatches = false) {
  const select = document.getElementById("Attendings");
  if (!select) {
    return returnAllMatches ? [] : null;
  }

  const normalize = (text) =>
    text
      .toLowerCase()
      .replace(/[.,]/g, " ")
      .replace(/\s+/g, " ")
      .trim();

  const nameNormalized = normalize(name);
  const matches = [];

  // Extract name parts (expecting "Last, First" but tolerant of spacing)
  const nameParts = nameNormalized.split(/\s+/).filter(Boolean);
  const lastName = nameParts[0] || "";
  const firstName = nameParts[1] || "";

  for (const opt of select.options) {
    if (!opt.value || opt.value === "") {
      continue;
    }
    const optText = opt.text;
    const optNormalized = normalize(optText);

    // Exact match (normalized)
    if (optNormalized === nameNormalized) {
      if (returnAllMatches) {
        matches.push({ value: opt.value, text: opt.text, matchType: "exact" });
      } else {
        return opt.value;
      }
    }
    // High-confidence prefix match (e.g., missing middle initial), require first+last
    else if (
      lastName &&
      firstName &&
      optNormalized.startsWith(`${lastName} ${firstName}`)
    ) {
      matches.push({ value: opt.value, text: opt.text, matchType: "prefix" });
    }
  }

  if (returnAllMatches) {
    return matches;
  }

  // Return only if there's a single high-confidence non-exact match
  const nonExactMatches = matches.filter((m) => m.matchType !== "exact");
  if (nonExactMatches.length === 1) {
    return nonExactMatches[0].value;
  }
  return null;
}

// Get available attending options for display
function getAttendingOptions() {
  const select = document.getElementById("Attendings");
  if (!select) {
    return [];
  }

  const options = [];
  for (const opt of select.options) {
    if (opt.value && opt.value !== "") {
      options.push({ value: opt.value, text: opt.text });
    }
  }
  return options;
}

function fillCase(caseData) {
  console.log("Filling case:", caseData);

  const result = {
    success: true,
    filled: [],
    warnings: [],
    errors: [],
  };

  // Clear previous selections
  uncheckAllProcedures();

  // Set Case ID
  const caseIdField = getFieldId("caseId");
  if (caseIdField && caseData.caseId) {
    if (setInputValue(caseIdField, caseData.caseId)) {
      result.filled.push("caseId");
    }
  }

  // Set Date
  const dateField = getFieldId("date");
  if (dateField && caseData.date) {
    if (setInputValue(dateField, caseData.date)) {
      result.filled.push("date");
    }
  }

  // Set Institution
  if (caseData.institution) {
    const instId =
      INSTITUTION_MAP[caseData.institution] || caseData.institution;
    if (setSelectValue("Institutions", instId)) {
      result.filled.push("institution");
    }
  }

  // Set Attending with improved lookup
  let attendingSet = false;
  if (caseData.attending) {
    const attId = findAttendingId(caseData.attending);
    if (attId) {
      if (setSelectValue("Attendings", attId)) {
        result.filled.push("attending");
        attendingSet = true;
      }
    } else {
      // Try high-confidence matches only (unique prefix match)
      const matches = findAttendingId(caseData.attending, true).filter(
        (m) => m.matchType !== "exact",
      );
      if (matches.length === 1) {
        if (setSelectValue("Attendings", matches[0].value)) {
          result.filled.push("attending");
          if (caseData.showWarnings !== false) {
            result.warnings.push(
              `Attending "${caseData.attending}" not found exactly, used "${matches[0].text}"`,
            );
          }
          attendingSet = true;
        }
      }
    }
  }

  // Use default attending if not set
  if (!attendingSet && caseData.defaultAttending) {
    const attId = findAttendingId(caseData.defaultAttending);
    if (attId) {
      if (setSelectValue("Attendings", attId)) {
        result.filled.push("attending");
        if (caseData.showWarnings !== false) {
          result.warnings.push(
            `Used default attending: ${caseData.defaultAttending}`,
          );
        }
        attendingSet = true;
      }
    }
  }

  // Fall back to FACULTY, FACULTY if still not set
  if (!attendingSet) {
    const facultyId = findAttendingId("FACULTY, FACULTY");
    if (facultyId) {
      if (setSelectValue("Attendings", facultyId)) {
        result.filled.push("attending");
        if (caseData.showWarnings !== false) {
          result.warnings.push(
            `Attending "${caseData.attending || "(none)"}" not found, used FACULTY, FACULTY`,
          );
        }
      }
    } else {
      if (caseData.showWarnings !== false) {
        result.warnings.push(
          `Could not set attending - no matching option found`,
        );
      }
    }
  }

  // Set Patient Age
  if (caseData.ageCategory) {
    const ageKey = caseData.ageCategory.charAt(0).toLowerCase();
    const ageId = AGE_MAP[ageKey];
    if (ageId) {
      if (setSelectValue("PatientTypes", ageId)) {
        result.filled.push("age");
      }
    }
  }

  // Set Comments
  if (caseData.comments) {
    const commentsContainer = document.getElementById("commentsContainer");
    if (commentsContainer && !commentsContainer.classList.contains("show")) {
      commentsContainer.classList.add("show");
    }
    const commentsArea = document.getElementById("Comments");
    if (commentsArea) {
      commentsArea.value = caseData.comments;
      result.filled.push("comments");
    }
  }

  // Set ASA Status
  if (caseData.asa) {
    const asaCode = ASA_MAP[caseData.asa.toString().toUpperCase()];
    if (asaCode) {
      console.log("Checking ASA:", caseData.asa, "-> code", asaCode);
      if (checkProcedure(asaCode)) {
        result.filled.push("asa");
      }
    }
  }

  // Set Anesthesia Type
  if (caseData.anesthesia) {
    const code = ANESTHESIA_MAP[caseData.anesthesia];
    if (code) {
      console.log("Checking Anesthesia:", caseData.anesthesia, "-> code", code);
      if (checkProcedure(code)) {
        result.filled.push("anesthesia");
      }
    }
  }

  // Set Airway Management (semicolon-separated from Python tool)
  if (caseData.airway) {
    caseData.airway.split(";").forEach((item) => {
      item = item.trim();
      if (!item) {
        return;
      }

      // Check airway device
      if (AIRWAY_MAP[item]) {
        console.log(
          "Checking Airway device:",
          item,
          "-> code",
          AIRWAY_MAP[item],
        );
        if (checkProcedure(AIRWAY_MAP[item])) {
          result.filled.push(`airway:${item}`);
        }
      }

      // Check laryngoscopy type
      if (LARYNGOSCOPY_MAP[item]) {
        console.log(
          "Checking Laryngoscopy:",
          item,
          "-> code",
          LARYNGOSCOPY_MAP[item],
        );
        if (checkProcedure(LARYNGOSCOPY_MAP[item])) {
          result.filled.push(`laryngoscopy:${item}`);
        }
      }
    });
  }

  // Set Procedure Category
  const procCat = caseData.procedureCategory;
  if (procCat && procCat !== "Other (procedure cat)") {
    const code = PROCEDURE_CAT_MAP[procCat];
    if (code) {
      console.log("Checking Procedure Cat:", procCat, "-> code", code);
      if (checkProcedure(code)) {
        result.filled.push("procedureCategory");
      }
    }
  }

  // Determine if cardiac case for auto-checks
  const isCardiac =
    procCat === "Cardiac with CPB" || procCat === "Cardiac without CPB";

  // Check if cardiac auto-fill is enabled (default true for backwards compatibility)
  const cardiacAutoFill = caseData.cardiacAutoFill !== false;

  // For cardiac cases, optionally auto-check standard monitoring/access
  if (isCardiac && cardiacAutoFill) {
    console.log(
      "Cardiac case - auto-checking TEE, arterial, central, ultrasound, PA catheter",
    );

    // Only add items not already in the data
    const existingVascular = (caseData.vascularAccess || "").toLowerCase();
    const existingMonitoring = (caseData.monitoring || "").toLowerCase();

    // TEE (if not already specified)
    if (!existingMonitoring.includes("tee")) {
      checkProcedure(MONITORING_MAP.TEE);
      result.filled.push("cardiac:TEE");
    }
    // Arterial (if not already specified)
    if (!existingVascular.includes("arterial")) {
      checkProcedure(VASCULAR_MAP["Arterial Catheter"]);
      result.filled.push("cardiac:Arterial");
    }
    // Central line (if not already specified)
    if (!existingVascular.includes("central")) {
      checkProcedure(VASCULAR_MAP["Central Venous Catheter"]);
      result.filled.push("cardiac:Central");
    }
    // Ultrasound guided (if not already specified)
    if (!existingVascular.includes("ultrasound")) {
      checkProcedure(VASCULAR_MAP["Ultrasound Guided"]);
      result.filled.push("cardiac:Ultrasound");
    }
    // PA Catheter (if not already specified)
    if (!existingVascular.includes("pa catheter")) {
      checkProcedure(VASCULAR_MAP["PA Catheter"]);
      result.filled.push("cardiac:PA");
    }
  }

  // Always check vascular access from data (for both cardiac and non-cardiac)
  if (caseData.vascularAccess) {
    caseData.vascularAccess.split(";").forEach((item) => {
      item = item.trim();
      if (item && VASCULAR_MAP[item]) {
        console.log("Checking Vascular:", item, "-> code", VASCULAR_MAP[item]);
        if (checkProcedure(VASCULAR_MAP[item])) {
          result.filled.push(`vascular:${item}`);
        }
      }
    });
  }

  // Set Monitoring
  if (caseData.monitoring) {
    caseData.monitoring.split(";").forEach((item) => {
      item = item.trim();
      if (!item) {
        return;
      }

      if (MONITORING_MAP[item]) {
        console.log(
          "Checking Monitoring:",
          item,
          "-> code",
          MONITORING_MAP[item],
        );
        if (checkProcedure(MONITORING_MAP[item])) {
          result.filled.push(`monitoring:${item}`);
        }
      }
    });
  }

  // Set Difficult Airway Management
  if (caseData.difficultAirway) {
    const code = DIFFICULT_AIRWAY_MAP[caseData.difficultAirway];
    if (code) {
      console.log(
        "Checking Difficult Airway:",
        caseData.difficultAirway,
        "-> code",
        code,
      );
      if (checkRadioProcedure(code)) {
        result.filled.push(`difficultAirway:${caseData.difficultAirway}`);
      }
    }
  }

  // Set Life-Threatening Pathology
  // Auto-check Non-Trauma for 5E cases if setting enabled
  const isFiveE =
    caseData.asa && caseData.asa.toString().toUpperCase() === "5E";
  let pathologyToCheck = caseData.lifeThreateningPathology;

  if (caseData.auto5EPathology !== false && isFiveE && !pathologyToCheck) {
    pathologyToCheck = "Non-Trauma";
    if (caseData.showWarnings !== false) {
      result.warnings.push(
        "Automatically checked Non-Trauma Life-Threatening Pathology for 5E case",
      );
    }
  }

  if (pathologyToCheck) {
    const code = LIFE_THREATENING_PATHOLOGY_MAP[pathologyToCheck];
    if (code) {
      console.log(
        "Checking Life-Threatening Pathology:",
        pathologyToCheck,
        "-> code",
        code,
      );
      if (checkRadioProcedure(code)) {
        result.filled.push(`lifeThreateningPathology:${pathologyToCheck}`);
      }
    }
  }

  console.log("Case fill complete:", result);
  return result;
}

function submitCase() {
  // Try multiple selectors for the submit button
  const submitBtn =
    document.getElementById("btnSave") ||
    document.querySelector('button[type="submit"]') ||
    document.querySelector('input[type="submit"]') ||
    document.querySelector(".btn-save") ||
    document.querySelector('[onclick*="Save"]') ||
    document.querySelector('[onclick*="save"]');

  if (!submitBtn) {
    console.error("Submit button not found");
    console.log("Available buttons:", document.querySelectorAll("button"));
    return false;
  }

  console.log("Found submit button:", submitBtn);
  submitBtn.click();
  console.log("Submit button clicked");
  return true;
}

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "fillCase") {
    try {
      const result = fillCase(message.data);
      if (message.autoSubmit) {
        result.submitted = submitCase();
      }
      sendResponse({ success: true, result });
    } catch (error) {
      console.error("Error filling case:", error);
      sendResponse({ success: false, errors: [error.message] });
    }
    return true; // Keep channel open for async response
  }

  if (message.action === "submitCase") {
    try {
      const submitted = submitCase();
      if (submitted) {
        sendResponse({ success: true });
      } else {
        sendResponse({ success: false, errors: ["Submit button not found."] });
      }
    } catch (error) {
      console.error("Error submitting case:", error);
      sendResponse({ success: false, errors: [error.message] });
    }
    return true;
  }

  if (message.action === "getAttendingOptions") {
    try {
      const options = getAttendingOptions();
      sendResponse({ success: true, options });
    } catch (error) {
      console.error("Error getting attending options:", error);
      sendResponse({ success: false, errors: [error.message] });
    }
    return true;
  }

  return false; // Not our message
});

console.log("ACGME Case Submitter content script loaded.");
