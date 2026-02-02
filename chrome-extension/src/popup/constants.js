/**
 * Constants and configuration
 */

const _DOM = {
  // Sections
  uploadSection: "uploadSection",
  navSection: "navSection",
  previewSection: "previewSection",
  settingsSection: "settingsSection",
  statusSection: "statusSection",
  confirmationPanel: "confirmationPanel",

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
  cancelSubmitBtn: "cancelSubmitBtn",
  confirmSubmitBtn: "confirmSubmitBtn",

  // Settings
  settingsToggle: "settingsToggle",
  settingInstitution: "settingInstitution",
  settingDefaultAttending: "settingDefaultAttending",
  settingSubmitDelay: "settingSubmitDelay",
  submitDelayValue: "submitDelayValue",
  settingCardiacAutoFill: "settingCardiacAutoFill",
  settingAuto5EPathology: "settingAuto5EPathology",
  settingConfirmBeforeSubmit: "settingConfirmBeforeSubmit",
  settingShowWarnings: "settingShowWarnings",
  saveSettingsBtn: "saveSettingsBtn",
  clearSessionBtn: "clearSessionBtn",

  // Status
  statusMessage: "statusMessage",
  confirmationSummary: "confirmationSummary",
};

const _EXPECTED_COLUMNS = [
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

const _STORAGE_KEYS = {
  cases: "acgme_cases",
  currentIndex: "acgme_currentIndex",
  caseStatuses: "acgme_caseStatuses",
  settings: "acgme_settings",
};

const _STATUS_TYPES = {
  pending: "pending",
  submitted: "submitted",
  skipped: "skipped",
};

const _ACGME_URL_PATTERN = "apps.acgme.org/ads/CaseLogs/CaseEntry";
