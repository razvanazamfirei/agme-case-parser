/**
 * Application state management
 */

export const State = {
  cases: [],
  currentIndex: 0,
  caseStatuses: {},
  pendingSubmission: false,

  settings: {
    defaultInstitution: "",
    defaultAttending: "",
    submitDelay: 0.5,
    cardiacAutoFill: true,
    auto5EPathology: true,
    confirmBeforeSubmit: true,
    showWarnings: true,
  },

  reset() {
    this.cases = [];
    this.currentIndex = 0;
    this.caseStatuses = {};
    this.pendingSubmission = false;
  },

  setCases(cases) {
    this.cases = cases;
    this.caseStatuses = {};
    for (let i = 0; i < cases.length; i++) {
      this.caseStatuses[i] = STATUS_TYPES.pending;
    }
    this.currentIndex = 0;
  },

  getCurrentCase() {
    return this.cases[this.currentIndex];
  },

  getCaseStatus(index) {
    return this.caseStatuses[index] || STATUS_TYPES.pending;
  },

  setCaseStatus(index, status) {
    this.caseStatuses[index] = status;
  },

  getStats() {
    const stats = { pending: 0, submitted: 0, skipped: 0 };
    for (let i = 0; i < this.cases.length; i++) {
      const status = this.getCaseStatus(i);
      stats[status]++;
    }
    return stats;
  },

  findNextPending(fromIndex) {
    // Search forward
    for (let i = fromIndex + 1; i < this.cases.length; i++) {
      if (this.getCaseStatus(i) === STATUS_TYPES.pending) {
        return i;
      }
    }
    // Wrap around
    for (let i = 0; i < fromIndex; i++) {
      if (this.getCaseStatus(i) === STATUS_TYPES.pending) {
        return i;
      }
    }
    return null;
  },
};
