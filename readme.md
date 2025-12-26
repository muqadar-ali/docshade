# DocShade

This repository contains a **Streamlit** application designed to enhance document privacy. It allows users to redact sensitive information from PDF files and apply custom watermarks. The tool is robust, capable of handling both digitally created PDFs and scanned documents using Optical Character Recognition (OCR).

## Features

- **Dual-Layer Redaction**:
  - **Digital Search**: Quickly finds and redacts text in standard PDFs with selectable text layers.
  - **OCR Search**: Utilizes `EasyOCR` to detect and redact text within images or scanned pages, ensuring mixed-content documents are protected.
- **Adaptive Watermarking**: Automatically scales the watermark font size based on the document's page dimensions and applies it diagonally across the center.
- **Batch Processing**: Support for uploading and processing multiple PDF files simultaneously.
- **Smart Output**:
  - Single processed files are available for direct download.
  - Multiple processed files are automatically bundled into a ZIP archive.

## Prerequisites

Ensure you have Python installed. The application relies on the following external libraries:

- Streamlit (UI framework)
- PyMuPDF (fitz) (PDF manipulation)
- EasyOCR (Text recognition)
- Pillow (Image processing)

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/muqadar-ali/docshade.git
   cd docshade
   ```

2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```
   or 
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```
   

3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the application:
   ```bash
   streamlit run app.py
   ```

2. The app will open in your default web browser.

3. **Upload**: Drag and drop one or more PDF files into the upload area.
4. **Watermark**: Customize the watermark text (default: "RENTAL USE ONLY").
5. **Sensitive Data**: Enter the words or phrases you wish to redact in the text area (one pattern per line).
6. **Process**: Click the **Process & Protect** button.
7. **Download**: Once finished, download your protected PDF or ZIP file.

## How It Works

1. **Digital Redaction**: The app searches for text strings directly within the PDF structure and applies redaction annotations.
2. **OCR Redaction**: It converts pages to images and runs EasyOCR to find text coordinates for scanned content, mapping them back to the PDF page to apply redactions.
3. **Watermarking**: It calculates the page diagonal to determine an appropriate font size and inserts a semi-transparent, rotated text overlay.
