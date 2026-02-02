/**
 * UI utilities and helpers
 */

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
};
