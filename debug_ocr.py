from pathlib import Path
from PIL import Image
from src.pipeline import extract_document
from src.ocr.image_extractor import extract_image_items
from src.ocr.preprocessing import preprocess_image
from src.ocr.engine import recognize_text

# Find the most recent pytest-generated fixture.
temp_root = Path.home() / "AppData/Local/Temp/pytest-of-suret"
pdfs = list(temp_root.glob("pytest-*/test_ocr_pipeline_recovers_sca0/hybrid_scanned.pdf"))

if not pdfs:
    print("No test PDF found. Rerun the failing pytest test first.")
    raise SystemExit(1)

pdf_path = max(pdfs, key=lambda p: p.stat().st_mtime)
print("PDF:", pdf_path)

result = extract_document(pdf_path)
print("OCR-needed pages:", [
    (flag.page_number, flag.reason)
    for flag in result.ocr_needed_pages
])

items = extract_image_items(
    pdf_path,
    extraction_result=result,
)

print("Images extracted:", len(items))

for index, item in enumerate(items, start=1):
    print(f"\n--- Image {index} ---")
    print("Kind:", item.metadata.get("kind"))
    print("Page:", item.page_number)
    print("Image size:", item.image.size)
    print("Image mode:", item.image.mode)

    processed = preprocess_image(item.image)
    print("Processed size:", processed.size)

    detections = recognize_text(processed)
    print("Detections:", detections)

    # Save the processed image for visual inspection.
    output_path = Path.cwd() / f"ocr_debug_image_{index}.png"
    processed.save(output_path)
    print("Saved:", output_path)
