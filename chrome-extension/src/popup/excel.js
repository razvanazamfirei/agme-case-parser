/**
 * Excel file parsing
 */

import { EXPECTED_COLUMNS } from "./constants.js";

export const Excel = {
  async parseFile(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();

      reader.onload = (e) => {
        try {
          const data = new Uint8Array(e.target.result);
          const workbook = XLSX.read(data, { type: "array" });
          const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
          const rows = XLSX.utils.sheet_to_json(firstSheet, { header: 1 });

          if (rows.length < 2) {
            reject(new Error("File has no data rows"));
            return;
          }

          const result = this._parseRows(rows);
          resolve(result);
        } catch (err) {
          reject(err);
        }
      };

      reader.onerror = () => reject(new Error("Failed to read file"));
      reader.readAsArrayBuffer(file);
    });
  },

  _parseRows(rows) {
    const headers = rows[0].map((h) => String(h || "").trim());
    const mappingResult = this._mapColumns(headers);
    const colIndex = mappingResult.colIndex;
    const cases = [];

    for (let i = 1; i < rows.length; i++) {
      const row = rows[i];
      if (!row || row.length === 0) {
        continue;
      }

      const caseData = {
        caseId: this._getString(row, colIndex["Case ID"]),
        date: this._formatDate(row[colIndex["Case Date"]]),
        attending: this._getString(row, colIndex.Supervisor),
        ageCategory: this._getString(row, colIndex.Age),
        comments: this._getString(row, colIndex["Original Procedure"]),
        asa: this._getString(row, colIndex["ASA Physical Status"]),
        anesthesia: this._getString(row, colIndex["Anesthesia Type"]),
        airway: this._getString(row, colIndex["Airway Management"]),
        procedureCategory: this._getString(row, colIndex["Procedure Category"]),
        vascularAccess: this._getString(
          row,
          colIndex["Specialized Vascular Access"],
        ),
        monitoring: this._getString(
          row,
          colIndex["Specialized Monitoring Techniques"],
        ),
      };

      if (caseData.caseId) {
        cases.push(caseData);
      }
    }

    return { cases, mappingResult };
  },

  _mapColumns(headers) {
    const colIndex = {};
    const mapped = [];
    const missing = [];

    EXPECTED_COLUMNS.forEach((col) => {
      const idx = headers.findIndex(
        (h) => h.toLowerCase() === col.toLowerCase(),
      );
      if (idx === -1) {
        missing.push(col);
      } else {
        colIndex[col] = idx;
        mapped.push(col);
      }
    });

    return {
      colIndex,
      mapped,
      missing,
      totalExpected: EXPECTED_COLUMNS.length,
      totalMapped: mapped.length,
    };
  },

  _getString(row, idx) {
    if (idx === undefined || idx === null) {
      return "";
    }
    const val = row[idx];
    if (val === null || val === undefined) {
      return "";
    }
    return String(val).trim();
  },

  _formatDate(val) {
    if (!val) {
      return "";
    }

    if (typeof val === "string" && /^\d{1,2}\/\d{1,2}\/\d{4}$/.test(val)) {
      return val;
    }

    if (typeof val === "number") {
      const date = new Date((val - 25569) * 86400 * 1000);
      return `${date.getMonth() + 1}/${date.getDate()}/${date.getFullYear()}`;
    }

    const d = new Date(val);
    if (!Number.isNaN(d.getTime())) {
      return `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()}`;
    }

    return String(val);
  },
};
