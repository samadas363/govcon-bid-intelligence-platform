from pathlib import Path
from reportlab.pdfgen import canvas

output_dir = Path("data/solicitations")
output_dir.mkdir(parents=True, exist_ok=True)

pdf_path = output_dir / "sample_it_solicitation.pdf"

lines = [
    "SAMPLE FEDERAL IT SERVICES SOLICITATION",
    "FICTIONAL TEST DOCUMENT - NOT A REAL OPPORTUNITY",
    "",
    "1. Scope of Work",
    "The contractor shall provide cloud infrastructure support, DevOps automation,",
    "CI/CD pipeline management, system monitoring, and technical documentation.",
    "",
    "2. Submission Deadline",
    "Proposals are due November 20, 2026, at 2:00 PM Eastern Time.",
    "",
    "3. Mandatory Requirements",
    "The contractor must submit a technical proposal and a separate price proposal.",
    "The proposal must describe its cloud security and incident response approach.",
    "",
    "4. Evaluation Criteria",
    "The government will evaluate technical capability, relevant experience,",
    "management approach, and total evaluated price.",
    "",
    "5. Contract Information",
    "This fictional example is for testing document extraction only.",
    "No real government agency issued this document.",
]

pdf = canvas.Canvas(str(pdf_path))
pdf.setTitle("Sample Federal IT Services Solicitation")

y = 770

for line in lines:
    pdf.drawString(55, y, line)
    y -= 28

pdf.save()

print("PDF created successfully.")
print("Location:", pdf_path.resolve())
print("File size:", pdf_path.stat().st_size, "bytes")
