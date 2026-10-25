BEGIN;
CREATE TABLE IF NOT EXISTS documents (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_name text NOT NULL,
    file_path text NOT NULL,
    file_hash text NOT NULL UNIQUE CHECK (file_hash ~ '^[0-9a-f]{64}$'),
    total_pages integer NOT NULL CHECK (total_pages > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- แยกข้อมูลแต่ละหน้าเพื่อให้โน้ตและผลสรุปอ้างอิงหน้าที่มีอยู่ในเอกสาร
CREATE TABLE IF NOT EXISTS document_pages (
    document_id bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number integer NOT NULL CHECK (page_number > 0),
    PRIMARY KEY (document_id, page_number)
);
CREATE TABLE IF NOT EXISTS notes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint NOT NULL,
    page_number integer NOT NULL,
    content text NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (document_id, page_number),
    FOREIGN KEY (document_id, page_number)
        REFERENCES document_pages(document_id, page_number) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS ai_summaries (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint NOT NULL,
    page_number integer NOT NULL,
    model_name text NOT NULL,
    content text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id, page_number)
        REFERENCES document_pages(document_id, page_number) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ai_summaries_page_idx
    ON ai_summaries(document_id, page_number, id DESC);
COMMIT;
