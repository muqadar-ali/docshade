import streamlit as st
import fitz  # PyMuPDF
import io
import easyocr
import math
import zipfile
from PIL import Image, ImageDraw

@st.cache_resource
def load_easyocr_reader():
    return easyocr.Reader(['de'])

def process_file(file_content, file_name, sensitive_patterns, watermark_text):
    file_ext = file_name.split('.')[-1].lower()
    if file_ext == 'jpeg': file_ext = 'jpg'

    doc = fitz.open(stream=file_content, filetype=file_ext)
    is_pdf = file_ext == 'pdf'
    
    # For images, we'll collect redactions and apply them at the end
    image_redactions = [] if not is_pdf else None
    
    for page in doc:
        # 1. ROBUST REDACTION (Digital + OCR) - PDF only
        if is_pdf and sensitive_patterns:
            # --- Stage 1: Digital Search (Fast and Precise) ---
            for text in sensitive_patterns:
                matches = page.search_for(text)
                for rect in matches:
                    if rect.height > 3:
                        rect.y0 += 2
                        rect.y1 -= 1
                    page.add_redact_annot(rect, fill=(0, 0, 0))

        # --- Stage 2: OCR Search (for Scanned/Image content) ---
        if sensitive_patterns:
            reader = load_easyocr_reader()
            
            if is_pdf:
                pix = page.get_pixmap(dpi=300)
                scale = 72 / 300
            else:
                pix = page.get_pixmap()
                scale = 1.0

            img_bytes = pix.tobytes("png")
            results = reader.readtext(img_bytes)
            
            ocr_words = []
            for (bbox, text, prob) in results:
                # Use a very low confidence threshold (>0.05) to catch difficult-to-read text like MRZ zones
                if prob > 0.05 and text.strip():
                    xs = [point[0] for point in bbox]
                    ys = [point[1] for point in bbox]
                    left = min(xs)
                    top = min(ys)
                    width = max(xs) - left
                    height = max(ys) - top
                    full_text = text.strip()
                    
                    # Split multi-word OCR results into individual words
                    words = full_text.split()
                    if len(words) > 1:
                        # Estimate word width per character
                        char_width = width / len(full_text)
                        current_pos = left
                        for word in words:
                            word_width = len(word) * char_width
                            ocr_words.append({
                                'text': word,
                                'left': current_pos,
                                'top': top,
                                'width': word_width,
                                'height': height
                            })
                            current_pos += word_width + char_width  # Add space width
                    else:
                        ocr_words.append({
                            'text': full_text,
                            'left': left,
                            'top': top,
                            'width': width,
                            'height': height
                        })
            
            # Normalize function to remove separators for flexible matching
            def normalize_text(text):
                # Remove common separators and noise characters, keeping only alphanumeric
                normalized = text.lower()
                # Remove all non-alphanumeric characters except spaces
                normalized = ''.join(c for c in normalized if c.isalnum() or c.isspace())
                # Remove spaces
                normalized = normalized.replace(' ', '')
                return normalized
            
            for pattern in sensitive_patterns:
                pattern_normalized = normalize_text(pattern)
                
                # Build a combined text of all OCR words for substring matching
                all_ocr_normalized = ''.join(normalize_text(w['text']) for w in ocr_words)
                
                # Try to match the pattern across consecutive words (for multi-word patterns)
                for i in range(len(ocr_words)):
                    # Check single word match first
                    word_data = ocr_words[i]
                    word_normalized = normalize_text(word_data['text'])
                    
                    if word_normalized == pattern_normalized:
                        w_data = word_data
                        # Add 15% padding to the right to ensure complete redaction
                        padded_width = w_data['width'] * 1.15
                        rect_coords = (
                            int(w_data['left'] * scale),
                            int(w_data['top'] * scale),
                            int((w_data['left'] + padded_width) * scale),
                            int((w_data['top'] + w_data['height']) * scale)
                        )
                        if is_pdf:
                            rect = fitz.Rect(rect_coords)
                            page.add_redact_annot(rect, fill=(0, 0, 0))
                        else:
                            image_redactions.append(rect_coords)
                    else:
                        # Try to match across consecutive words (for patterns like "01 01 1990")
                        combined_text = word_normalized
                        j = i + 1
                        word_list = [word_data]
                        
                        while j < len(ocr_words) and len(combined_text) < len(pattern_normalized):
                            next_word = ocr_words[j]
                            combined_text += normalize_text(next_word['text'])
                            word_list.append(next_word)
                            j += 1
                        
                        if combined_text == pattern_normalized and len(word_list) > 1:
                            # Redact all words in the sequence
                            min_left = min(w['left'] for w in word_list)
                            max_right = max(w['left'] + w['width'] for w in word_list)
                            min_top = min(w['top'] for w in word_list)
                            max_bottom = max(w['top'] + w['height'] for w in word_list)
                            
                            rect_coords = (
                                int(min_left * scale),
                                int(min_top * scale),
                                int(max_right * scale),  # 5% padding
                                int(max_bottom * scale)
                            )
                            if is_pdf:
                                rect = fitz.Rect(rect_coords)
                                page.add_redact_annot(rect, fill=(0, 0, 0))
                            else:
                                image_redactions.append(rect_coords)
                
                # Fallback: substring matching if pattern not found as exact word matches
                # This handles cases where OCR might split or merge characters differently
                if pattern_normalized in all_ocr_normalized:
                    pattern_start_idx = all_ocr_normalized.find(pattern_normalized)
                    if pattern_start_idx >= 0:
                        # Find which words contain this substring and redact them
                        current_pos = 0
                        words_to_redact = []
                        
                        for w_idx, w in enumerate(ocr_words):
                            w_normalized = normalize_text(w['text'])
                            w_start = current_pos
                            w_end = current_pos + len(w_normalized)
                            
                            # Check if this word overlaps with the pattern
                            pattern_end_idx = pattern_start_idx + len(pattern_normalized)
                            if not (w_end <= pattern_start_idx or w_start >= pattern_end_idx):
                                words_to_redact.append(w)
                            
                            current_pos = w_end
                        
                        if words_to_redact:
                            min_left = min(w['left'] for w in words_to_redact)
                            max_right = max(w['left'] + w['width'] for w in words_to_redact)
                            min_top = min(w['top'] for w in words_to_redact)
                            max_bottom = max(w['top'] + w['height'] for w in words_to_redact)
                            
                            rect_coords = (
                                int(min_left * scale),
                                int(min_top * scale),
                                int(max_right * scale),
                                int(max_bottom * scale)
                            )
                            if is_pdf:
                                rect = fitz.Rect(rect_coords)
                                page.add_redact_annot(rect, fill=(0, 0, 0))
                            else:
                                image_redactions.append(rect_coords)
        
        if is_pdf:
            page.apply_redactions()

        # 2. ADAPTIVE WATERMARK - PDF only
        if is_pdf and watermark_text:
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
    if is_pdf:
        doc.save(output_buffer)
    else:
        # For images, apply redactions using PIL
        pix = doc[0].get_pixmap(alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        
        # Apply redactions
        if image_redactions:
            draw = ImageDraw.Draw(img)
            for rect in image_redactions:
                draw.rectangle(rect, fill=(0, 0, 0))
        
        # Save as PNG
        img.save(output_buffer, format="PNG")

    doc.close()
    output_buffer.seek(0)
    return output_buffer

# --- UI Layout (Remains consistent) ---
st.set_page_config(page_title="DocShade", layout="wide")
st.title("🛡️ DocShade")

uploaded_files = st.file_uploader("Upload Files (Drag & Drop)", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True)

if uploaded_files and sum(f.size for f in uploaded_files) > 10 * 1024 * 1024:
    st.error("Total file size exceeds the 10 MB limit.")

col1, col2 = st.columns([1, 1])
with col1:
    watermark_text = st.text_input("Watermark Text", value="RENTAL USE ONLY")
    st.info("💡 The font size will now automatically scale based on the page size.")

with col2:
    raw_sensitive_data = st.text_area("Sensitive Data (case insensitive, one per line)", height=150)
    st.caption("Hint: Files often have inconsistent spacing or artifacts between words. To ensure successful redaction, break multi-word phrases into individual words on separate lines.")

if st.button("Process & Protect", type="primary"):
    if not uploaded_files:
        st.warning("Please upload files first.")
    elif sum(f.size for f in uploaded_files) > 10 * 1024 * 1024:
        pass
    else:
        sensitive_list = [l.strip() for l in raw_sensitive_data.split('\n') if l.strip()]
        processed_results = []

        with st.spinner('Processing...'):
            for uploaded_file in uploaded_files:
                try:
                    res = process_file(uploaded_file.read(), uploaded_file.name, sensitive_list, watermark_text)
                    processed_results.append((uploaded_file.name, res))
                except Exception as e:
                    st.error(f"Error in {uploaded_file.name}: {e}")

        if processed_results:
            if len(processed_results) == 1:
                st.download_button("Download Protected File", processed_results[0][1], f"protected_{processed_results[0][0]}")
            else:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for name, data in processed_results:
                        zf.writestr(f"protected_{name}", data.getvalue())
                st.download_button("Download All (ZIP)", zip_buffer.getvalue(), "protected_batch.zip")