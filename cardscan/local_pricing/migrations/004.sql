-- Literal edition labels were previously retained raw but not normalized.
-- Enrich edition only; do not infer non-holo finish or touch price history.
CREATE TABLE sku_attribute_reviews(id INTEGER PRIMARY KEY,sku_id INTEGER NOT NULL REFERENCES skus(id),field TEXT NOT NULL,previous_value TEXT,new_value TEXT NOT NULL,rule TEXT NOT NULL,proof_document_id INTEGER REFERENCES documents(id));
INSERT INTO sku_attribute_reviews(sku_id,field,previous_value,new_value,rule,proof_document_id)
SELECT v.id,'edition',NULL,CASE json_extract(v.raw_variant_json,'$.var') WHEN '1st Edition' THEN 'first edition' ELSE 'unlimited' END,
'literal source variant edition label v2',
(SELECT document_id FROM observations WHERE sku_id=v.id ORDER BY id DESC LIMIT 1)
FROM skus v WHERE edition IS NULL AND json_extract(raw_variant_json,'$.var') IN ('1st Edition','Unlimited');
UPDATE skus SET edition=CASE json_extract(raw_variant_json,'$.var') WHEN '1st Edition' THEN 'first edition' ELSE 'unlimited' END,
completeness_json=json_set(completeness_json,'$.edition',json('true')),
provenance_json=json_set(provenance_json,'$.edition','explicit_variant_edition_label_v2')
WHERE edition IS NULL AND json_extract(raw_variant_json,'$.var') IN ('1st Edition','Unlimited');
PRAGMA user_version=4;
