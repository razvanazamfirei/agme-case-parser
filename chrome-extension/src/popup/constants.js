/**
 * Constants and configuration
 */

export const DOM = {
  // Sections
  uploadSection: "uploadSection",
  navSection: "navSection",
  previewSection: "previewSection",
  settingsSection: "settingsSection",
  statusSection: "statusSection",

  // Upload
  uploadBtn: "uploadBtn",
  fileInput: "fileInput",
  fileName: "fileName",

  // Navigation
  prevBtn: "prevBtn",
  nextBtn: "nextBtn",
  caseJump: "caseJump",
  filterPending: "filterPending",
  currentIndex: "currentIndex",
  totalCount: "totalCount",
  pendingCount: "pendingCount",
  submittedCount: "submittedCount",
  skippedCount: "skippedCount",

  // Form fields
  caseId: "caseId",
  date: "date",
  attending: "attending",
  ageCategory: "ageCategory",
  asa: "asa",
  anesthesia: "anesthesia",
  procedureCategory: "procedureCategory",
  comments: "comments",
  caseStatus: "caseStatus",

  // Actions
  skipBtn: "skipBtn",
  fillBtn: "fillBtn",
  fillSubmitBtn: "fillSubmitBtn",

  // Settings
  settingsToggle: "settingsToggle",
  settingInstitution: "settingInstitution",
  settingDefaultAttending: "settingDefaultAttending",
  settingSubmitDelay: "settingSubmitDelay",
  submitDelayValue: "submitDelayValue",
  settingCardiacAutoFill: "settingCardiacAutoFill",
  settingAuto5EPathology: "settingAuto5EPathology",
  settingShowWarnings: "settingShowWarnings",
  saveSettingsBtn: "saveSettingsBtn",
  clearSessionBtn: "clearSessionBtn",

  // Status
  statusMessage: "statusMessage",

  // Validation
  validationSummary: "validationSummary",
  validationText: "validationText",
};

export const EXPECTED_COLUMNS = [
  "Case ID",
  "Case Date",
  "Supervisor",
  "Age",
  "Original Procedure",
  "ASA Physical Status",
  "Anesthesia Type",
  "Airway Management",
  "Procedure Category",
  "Specialized Vascular Access",
  "Specialized Monitoring Techniques",
];

export const STORAGE_KEYS = {
  cases: "acgme_cases",
  currentIndex: "acgme_currentIndex",
  caseStatuses: "acgme_caseStatuses",
  settings: "acgme_settings",
};

export const STATUS_TYPES = {
  pending: "pending",
  submitted: "submitted",
  skipped: "skipped",
};

export const ACGME_URL_PATTERN = "apps.acgme.org/ads/CaseLogs/CaseEntry";
