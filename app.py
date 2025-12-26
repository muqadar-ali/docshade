import streamlit as st
import fitz  # PyMuPDF
import io
import easyocr
import math
import zipfile

@st.cache_resource
def load_easyocr_reader():
    return easyocr.Reader(['de'])

def process_single_pdf(file_content, sensitive_patterns, watermark_text):
    doc = fitz.open(stream=file_content, filetype="pdf")
    
    for page in doc:
        # 1. ROBUST REDACTION (Digital + OCR)
        # We run both digital and OCR search on every page to ensure maximum coverage.
        # This handles text-based, scanned, and mixed-content PDFs reliably.

        # --- Stage 1: Digital Search (Fast and Precise) ---
        # This finds text in digitally-created PDFs or those with a text layer.
        if sensitive_patterns:
            for text in sensitive_patterns:
                matches = page.search_for(text)
                for rect in matches:
                    # Adjust rectangle to avoid overlapping with the line above
                    # Shrink the box slightly from the top (y0) and bottom (y1)
                    if rect.height > 3:
                        rect.y0 += 2
                        rect.y1 -= 1

                    page.add_redact_annot(rect, fill=(0, 0, 0))

        # --- Stage 2: OCR Search (for Scanned/Image content) ---
        # This finds text within images, which is crucial for scanned documents.
        if sensitive_patterns:
            reader = load_easyocr_reader()
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            results = reader.readtext(img_bytes)
            
            ocr_words = []
            for (bbox, text, prob) in results:
                # Use a confidence threshold (>0.4) to filter out OCR noise.
                if prob > 0.4 and text.strip():
                    xs = [point[0] for point in bbox]
                    ys = [point[1] for point in bbox]
                    left = min(xs)
                    top = min(ys)
                    ocr_words.append({
                        'text': text.strip(),
                        'left': left,
                        'top': top,
                        'width': max(xs) - left,
                        'height': max(ys) - top
                    })
            for pattern in sensitive_patterns:
                pattern_parts = pattern.split()
                if not pattern_parts: continue
                
                # Sliding window search for the pattern sequence
                for i in range(len(ocr_words) - len(pattern_parts) + 1):
                    match = True
                    for j, part in enumerate(pattern_parts):
                        # Loose match: check if pattern part is in OCR word
                        if part.lower() not in ocr_words[i+j]['text'].lower():
                            match = False
                            break
                    
                    if match:
                        # Redact all words that form the matched pattern
                        for k in range(len(pattern_parts)):
                            w_data = ocr_words[i+k]
                            scale = 72 / 300
                            rect = fitz.Rect(
                                w_data['left'] * scale,
                                w_data['top'] * scale,
                                (w_data['left'] + w_data['width']) * scale,
                                (w_data['top'] + w_data['height']) * scale
                            )
                            page.add_redact_annot(rect, fill=(0, 0, 0))
        
        page.apply_redactions()

        # 2. ADAPTIVE WATERMARK
        if watermark_text:
            width, height = page.rect.width, page.rect.height
            diagonal = math.sqrt(width**2 + height**2)
            adaptive_font_size = diagonal * 0.05
            center_x, center_y = width / 2, height / 2
            
            page.insert_text(
                (center_x - (len(watermark_text) * adaptive_font_size * 0.2), center_y),
                watermark_text,
                fontsize=adaptive_font_size,
                color=(0.5, 0.5, 0.5),
                fill_opacity=0.5,
                morph=(fitz.Point(center_x, center_y), fitz.Matrix(45))
            )

    output_buffer = io.BytesIO()
    doc.save(output_buffer)
    doc.close()
    output_buffer.seek(0)
    return output_buffer

# --- UI Layout (Remains consistent) ---
st.set_page_config(page_title="🛡️ DocShade", layout="wide")
st.title("🛡️ DocShade")

uploaded_files = st.file_uploader("Upload PDFs (Drag & Drop)", type="pdf", accept_multiple_files=True)

col1, col2 = st.columns([1, 1])
with col1:
    watermark_text = st.text_input("Watermark Text", value="RENTAL USE ONLY")
    st.info("💡 The font size will now automatically scale based on the page size.")

with col2:
    raw_sensitive_data = st.text_area("Sensitive Data (one per line)", height=150)
    st.caption("Hint: Scanned PDFs often have inconsistent spacing or artifacts between words. To ensure successful redaction, break multi-word phrases into individual words on separate lines.")

if st.button("Process & Protect", type="primary"):
    if not uploaded_files:
        st.warning("Please upload files first.")
    else:
        sensitive_list = [l.strip() for l in raw_sensitive_data.split('\n') if l.strip()]
        processed_results = []

        with st.spinner('Processing...'):
            for uploaded_file in uploaded_files:
                try:
                    res = process_single_pdf(uploaded_file.read(), sensitive_list, watermark_text)
                    processed_results.append((uploaded_file.name, res))
                except Exception as e:
                    st.error(f"Error in {uploaded_file.name}: {e}")

        if processed_results:
            if len(processed_results) == 1:
                st.download_button("Download Protected PDF", processed_results[0][1], f"protected_{processed_results[0][0]}")
            else:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for name, data in processed_results:
                        zf.writestr(f"protected_{name}", data.getvalue())
                st.download_button("Download All (ZIP)", zip_buffer.getvalue(), "protected_batch.zip")