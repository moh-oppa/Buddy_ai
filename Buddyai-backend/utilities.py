from io import BytesIO
from PyPDF2 import PdfReader
from fastapi import File, HTTPException, UploadFile

MAX_TEXT_LENGTH = 80000

# Utility functions for parsing different document types (PDF, TXT, DOCX) and extracting text content.
async def parse_pdf(doc: UploadFile = File(...)):
    try:
        content = await doc.read()
        raw = BytesIO(content)

        reader = PdfReader(raw)

        result = "\n".join(page.extract_text() for page in reader.pages)
        return result[:MAX_TEXT_LENGTH]

    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error processing file: {str(e)}")

# For TXT files, we can simply read the content and decode it as UTF-8.
async def parse_text(doc: UploadFile = File(...)):
    try:
        content = await doc.read()
        result = content.decode("utf-8", errors="ignore")
        return result[:MAX_TEXT_LENGTH]

    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error processing file: {str(e)}")


async def parse_docx(doc: UploadFile = File(...)):
    try:
        from docx import Document as DocxDocument

        content = await doc.read()
        raw = BytesIO(content)

        docx_doc = DocxDocument(raw)
        result = "\n".join(paragraph.text for paragraph in docx_doc.paragraphs)
        return result[:MAX_TEXT_LENGTH]

    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Error processing file: {str(e)}")
