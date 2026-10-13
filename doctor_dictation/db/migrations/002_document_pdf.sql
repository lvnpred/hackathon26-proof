-- 002_document_pdf.sql — record the rendered prescription PDF path (Task 8).
-- Additive: rendering fails soft (browser print-to-PDF is the fallback), so
-- pdf_path stays NULL when no server-side PDF was produced.
ALTER TABLE documents ADD COLUMN pdf_path TEXT;
