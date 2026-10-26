"""Generate the fictional Australian health receipts used to evaluate the claim checker.

Every provider, patient, and number here is invented. The files are safe to commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A5
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIRECTORY = ROOT / "samples" / "claims" / "receipts"


@dataclass(frozen=True, slots=True)
class Line:
  """One service printed on a receipt."""

  date: str
  description: str
  item: str | None
  fee: Decimal


@dataclass(frozen=True, slots=True)
class Receipt:
  """One fictional receipt."""

  filename: str
  provider: str
  practice: str
  abn: str | None
  provider_number: str | None
  address: str
  patient: str
  issued: str
  lines: tuple[Line, ...]
  paid: Decimal | None
  heading: str = "TAX INVOICE / RECEIPT"


_PATIENT = "Linh Nguyen"
_CLEARVIEW = {
  "provider": "Clearview Optometry",
  "practice": "Optometrist",
  "abn": "41 824 753 912",
  "provider_number": "2426621B",
  "address": "12 Station Street, Parramatta NSW 2150",
}

RECEIPTS = (
  Receipt(
    filename="01-glasses-optometrist.pdf",
    **_CLEARVIEW,
    patient=_PATIENT,
    issued="12/10/2026",
    lines=(
      Line("12/10/2026", "Comprehensive eye examination", "10918", Decimal("75.00")),
      Line("12/10/2026", "Single vision lens - pair", "9484", Decimal("220.00")),
      Line("12/10/2026", "Frames", "9472", Decimal("100.00")),
    ),
    paid=Decimal("395.00"),
  ),
  Receipt(
    filename="02-gp-consultation.pdf",
    provider="Riverside Medical Centre",
    practice="General Practice",
    abn="63 517 204 889",
    provider_number="4471832K",
    address="88 Church Street, Parramatta NSW 2150",
    patient=_PATIENT,
    issued="14/10/2026",
    lines=(Line("14/10/2026", "Standard consultation (Level B)", "23", Decimal("85.00")),),
    paid=Decimal("85.00"),
  ),
  Receipt(
    filename="03-vague-consultation.pdf",
    provider="Harbour Health Clinic",
    practice="Health Clinic",
    abn="27 640 918 335",
    provider_number="5190276H",
    address="4 Wharf Road, Sydney NSW 2000",
    patient=_PATIENT,
    issued="15/10/2026",
    lines=(Line("15/10/2026", "Consultation", None, Decimal("150.00")),),
    paid=Decimal("150.00"),
  ),
  Receipt(
    filename="04-pharmacy.pdf",
    provider="Campus Pharmacy",
    practice="Pharmacy",
    abn="90 315 662 071",
    provider_number=None,
    address="1 University Avenue, Kensington NSW 2033",
    patient=_PATIENT,
    issued="16/10/2026",
    lines=(
      Line("16/10/2026", "Amoxicillin 500mg capsules x20 (PBS prescription)", None,
           Decimal("31.60")),
      Line("16/10/2026", "Loratadine 10mg tablets x30 (non-prescription)", None,
           Decimal("18.95")),
    ),
    paid=Decimal("50.55"),
  ),
  Receipt(
    filename="05-dental.pdf",
    provider="Smile Bright Dental",
    practice="Dentist",
    abn="52 108 973 446",
    provider_number="7782015D",
    address="230 George Street, Sydney NSW 2000",
    patient=_PATIENT,
    issued="17/10/2026",
    lines=(
      Line("17/10/2026", "Periodic oral examination", "012", Decimal("70.00")),
      Line("17/10/2026", "Removal of calculus - first visit", "114", Decimal("120.00")),
    ),
    paid=Decimal("190.00"),
  ),
  Receipt(
    filename="06-physiotherapy.pdf",
    provider="Active Motion Physiotherapy",
    practice="Physiotherapist",
    abn="18 744 290 517",
    provider_number="3059174F",
    address="9 Macquarie Street, Parramatta NSW 2150",
    patient=_PATIENT,
    issued="18/10/2026",
    lines=(Line("18/10/2026", "Initial physiotherapy consultation", "500", Decimal("95.00")),),
    paid=Decimal("95.00"),
  ),
  Receipt(
    filename="07-sunglasses.pdf",
    **_CLEARVIEW,
    patient=_PATIENT,
    issued="19/10/2026",
    lines=(Line("19/10/2026", "Sunglasses (non-prescription)", None, Decimal("180.00")),),
    paid=Decimal("180.00"),
  ),
  Receipt(
    filename="08-unclear-optical.png",
    **_CLEARVIEW,
    patient=_PATIENT,
    issued="20/10/2026",
    lines=(
      Line("20/10/2026", "Comprehensive eye examination", "10918", Decimal("75.00")),
      Line("20/10/2026", "Single vision lens - pair", "9484", Decimal("220.00")),
    ),
    paid=Decimal("295.00"),
  ),
  Receipt(
    filename="09-cafe.pdf",
    provider="Brew & Bean Cafe",
    practice="Cafe",
    abn="33 902 118 640",
    provider_number=None,
    address="3 Campus Walk, Kensington NSW 2033",
    patient="",
    issued="21/10/2026",
    lines=(
      Line("21/10/2026", "Flat white", None, Decimal("5.50")),
      Line("21/10/2026", "Chicken sandwich", None, Decimal("12.00")),
    ),
    paid=Decimal("17.50"),
    heading="RECEIPT",
  ),
  Receipt(
    filename="10-old-glasses.pdf",
    **_CLEARVIEW,
    patient=_PATIENT,
    issued="04/03/2024",
    lines=(
      Line("04/03/2024", "Single vision lens - pair", "9484", Decimal("220.00")),
      Line("04/03/2024", "Frames", "9472", Decimal("100.00")),
    ),
    paid=Decimal("320.00"),
  ),
)


def text_lines(receipt: Receipt) -> list[tuple[str, str, str, str]]:
  """Rows as (date, item, description, fee) strings, with a header row first."""
  rows = [("Date", "Item", "Description", "Fee")]
  rows += [
    (line.date, line.item or "", line.description, f"${line.fee:,.2f}")
    for line in receipt.lines
  ]
  return rows


def header(receipt: Receipt) -> list[str]:
  lines = [receipt.provider, f"{receipt.practice} | {receipt.address}"]
  identifiers = []
  if receipt.abn:
    identifiers.append(f"ABN {receipt.abn}")
  if receipt.provider_number:
    identifiers.append(f"Provider No. {receipt.provider_number}")
  if identifiers:
    lines.append("   ".join(identifiers))
  lines.append(receipt.heading)
  lines.append(f"Date issued: {receipt.issued}")
  if receipt.patient:
    lines.append(f"Patient: {receipt.patient}")
  return lines


def draw_pdf(receipt: Receipt, path: Path) -> None:
  """Draw one receipt as a single A5 PDF page."""
  width, height = A5
  canvas = Canvas(str(path), pagesize=A5)
  canvas.setTitle(receipt.heading)
  y = height - 40
  for index, line in enumerate(header(receipt)):
    canvas.setFont("Helvetica-Bold" if index in (0, len(header(receipt)) - 3) else "Helvetica",
                   13 if index == 0 else 9)
    canvas.drawString(30, y, line)
    y -= 16 if index == 0 else 13
  y -= 10
  columns = (30, 95, 140, width - 80)
  for row_index, row in enumerate(text_lines(receipt)):
    canvas.setFont("Helvetica-Bold" if row_index == 0 else "Helvetica", 8.5)
    for x, value in zip(columns, row, strict=True):
      canvas.drawString(x, y, value)
    y -= 14
  total = sum(line.fee for line in receipt.lines)
  y -= 8
  canvas.setFont("Helvetica-Bold", 9)
  canvas.drawString(columns[2], y, "Total charged")
  canvas.drawString(columns[3], y, f"${total:,.2f}")
  if receipt.paid is not None:
    y -= 14
    canvas.drawString(columns[2], y, "Paid (EFTPOS)")
    canvas.drawString(columns[3], y, f"${receipt.paid:,.2f}")
    y -= 14
    canvas.drawString(columns[2], y, "Balance")
    canvas.drawString(columns[3], y, f"${total - receipt.paid:,.2f}")
  canvas.setFont("Helvetica", 7)
  canvas.drawString(30, 30, "Fictional receipt generated for software testing.")
  canvas.showPage()
  canvas.save()


def draw_png(receipt: Receipt, path: Path) -> None:
  """Draw a phone-photo-like receipt whose second line's item code and fee are smudged."""
  image = Image.new("RGB", (900, 620), "white")
  draw = ImageDraw.Draw(image)
  font = ImageFont.load_default(size=22)
  bold = ImageFont.load_default(size=28)
  y = 30
  for index, line in enumerate(header(receipt)):
    draw.text((40, y), line, fill="black", font=bold if index == 0 else font)
    y += 40 if index == 0 else 32
  y += 10
  columns = (40, 200, 290, 760)
  smudged: list[tuple[int, int, int, int]] = []
  for row_index, row in enumerate(text_lines(receipt)):
    for x, value in zip(columns, row, strict=True):
      draw.text((x, y), value, fill="black", font=font)
    if row_index == 2:
      smudged += [(columns[1] - 5, y - 4, columns[1] + 70, y + 30),
                  (columns[3] - 5, y - 4, columns[3] + 110, y + 30)]
    y += 36
  total = sum(line.fee for line in receipt.lines)
  draw.text((columns[2], y + 10), "Total charged", fill="black", font=font)
  draw.text((columns[3], y + 10), f"${total:,.2f}", fill="black", font=font)
  draw.text((columns[2], y + 46), "Paid (EFTPOS)", fill="black", font=font)
  draw.text((columns[3], y + 46), f"${receipt.paid or 0:,.2f}", fill="black", font=font)
  for box in smudged:
    region = image.crop(box).filter(ImageFilter.GaussianBlur(radius=9))
    image.paste(region, box)
  image.save(path)


def main() -> int:
  OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
  for receipt in RECEIPTS:
    path = OUTPUT_DIRECTORY / receipt.filename
    if path.suffix == ".png":
      draw_png(receipt, path)
    else:
      draw_pdf(receipt, path)
    print(f"wrote {path.relative_to(ROOT)}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
