"""Generate data/samples/sample_contract_hardeeville.pdf: a FICTIONAL contract for demos and tests.
Run from backend/:  python scripts/make_sample_contract.py"""
from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parents[1] / "data" / "samples" / "sample_contract_hardeeville.pdf"

LINES = [
    ("h", "SAMPLE CONSTRUCTION CONTRACT - FICTIONAL, FOR DEMONSTRATION ONLY"),
    ("p", "This document is invented for the Gridlock demo. The companies, prices and terms are not real."),
    ("s", "1. Project"),
    ("p", "Project name: Hardeeville Area Reliability Project - Jasper to Bluffton 115 kV Line Rebuild"),
    ("p", "Owner: Lowcountry Line Builders LLC (fictional)"),
    ("p", "Utility: Dominion Energy South Carolina"),
    ("p", "Work type: Transmission line rebuild"),
    ("p", "Voltage: 115 kV"),
    ("p", "Endpoints: Jasper Substation to Bluffton Substation"),
    ("p", "Location: Hardeeville, Jasper County, SC"),
    ("p", "Line length: 17.5 miles"),
    ("s", "2. Schedule"),
    ("p", "Start date: June 1, 2027"),
    ("p", "Completion date: December 15, 2027"),
    ("s", "3. Price"),
    ("p", "Contract price: $9,850,000"),
    ("s", "4. Resources"),
    ("p", "Crew size: 14 workers"),
    ("p", "Equipment: 3 bucket trucks, 1 60-ton crane, 2 digger derricks"),
    ("s", "5. Traffic control"),
    ("p", "Roads affected: US-17, I-95"),
    ("p", "Lane closures: Nighttime northbound lane closure on US-17 near Hardeeville"),
    ("p", "Work hours: 21:00-05:00"),
    ("s", "6. Terms"),
    ("p", "The contractor shall furnish all labor, equipment and materials to rebuild the line described above, "
          "coordinate all road work with the state DOT, and maintain traffic control at every road crossing. "
          "Payment follows the schedule of values attached as Exhibit A (not included in this sample)."),
]


def main():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(18, 18)
    for kind, text in LINES:
        if kind == "h":
            pdf.set_font("Helvetica", "B", 13)
            pdf.multi_cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
        elif kind == "s":
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Helvetica", "", 10.5)
            pdf.multi_cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
