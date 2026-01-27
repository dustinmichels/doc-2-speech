import argparse
import os
import sys
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered

def extract_pdf(path):
    print(f"Stage 1: Extracting text from {path} with Marker...")
    # Initialize marker with default configuration
    converter = PdfConverter(artifact_dict=create_model_dict())
    rendered = converter(path)
    text, _, _ = text_from_rendered(rendered)
    return text

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 1: Extract text from PDF")
    parser.add_argument("pdf_path", help="Path to the input PDF file")
    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"Error: The file '{args.pdf_path}' does not exist.")
        sys.exit(1)

    # Determine output directory based on PDF filename
    pdf_name = os.path.splitext(os.path.basename(args.pdf_path))[0]
    output_dir = os.path.join("out", pdf_name)
    os.makedirs(output_dir, exist_ok=True)

    try:
        raw_content = extract_pdf(args.pdf_path)
        
        output_path = os.path.join(output_dir, "extracted.txt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(raw_content)
        
        print(f"Success! Extracted text saved to {output_path}")

    except Exception as e:
        print(f"An error occurred during extraction: {e}")
        sys.exit(1)
