BEGIN;

INSERT OR IGNORE INTO context(uuid,name,description) VALUES
('ctx-default','Default','Default context');

INSERT OR IGNORE INTO registration_authority(uuid,name,description) VALUES
('ra-local','Local RA','Local Registration Authority');

-- Object Class: Person
INSERT OR IGNORE INTO registrable_item(uuid,item_type,preferred_name,definition,context_uuid,registration_authority_uuid,registration_status,administrative_status,steward,submitting_organization,version)
VALUES
('oc-person','OBJECT_CLASS','Person','A human being.','ctx-default','ra-local','Recorded','Released','Data Steward','Example Org',1);
INSERT OR IGNORE INTO object_class(uuid) VALUES ('oc-person');

-- Property: Date of birth
INSERT OR IGNORE INTO registrable_item(uuid,item_type,preferred_name,definition,context_uuid,registration_authority_uuid,registration_status,administrative_status)
VALUES
('prop-dob','PROPERTY','Date of Birth','The date on which a person was born.','ctx-default','ra-local','Recorded','Released');
INSERT OR IGNORE INTO property(uuid) VALUES ('prop-dob');

-- Conceptual Domain: Dates
INSERT OR IGNORE INTO registrable_item(uuid,item_type,preferred_name,definition,context_uuid,registration_authority_uuid,registration_status,administrative_status)
VALUES
('cd-dates','CONCEPTUAL_DOMAIN','Dates','Conceptual domain for date values.','ctx-default','ra-local','Recorded','Released');
INSERT OR IGNORE INTO conceptual_domain(uuid,description) VALUES ('cd-dates','Date values');

-- Value Domain: ISO Date
INSERT OR IGNORE INTO registrable_item(uuid,item_type,preferred_name,definition,context_uuid,registration_authority_uuid,registration_status,administrative_status)
VALUES
('vd-iso-date','VALUE_DOMAIN','ISO Date','Dates in ISO 8601 format.','ctx-default','ra-local','Recorded','Released');
INSERT OR IGNORE INTO value_domain(uuid,datatype,format,conceptual_domain_uuid,max_length)
VALUES
('vd-iso-date','date','YYYY-MM-DD','cd-dates',10);

-- Data Element Concept: Person + Date of Birth
INSERT OR IGNORE INTO registrable_item(uuid,item_type,preferred_name,definition,context_uuid,registration_authority_uuid,registration_status,administrative_status)
VALUES
('dec-person-dob','DATA_ELEMENT_CONCEPT','Person Date of Birth','The concept of a person’s date of birth.','ctx-default','ra-local','Recorded','Released');
INSERT OR IGNORE INTO data_element_concept(uuid,object_class_uuid,property_uuid,conceptual_domain_uuid)
VALUES
('dec-person-dob','oc-person','prop-dob','cd-dates');

-- Data Element: Person DOB + ISO Date
INSERT OR IGNORE INTO registrable_item(uuid,item_type,preferred_name,definition,context_uuid,registration_authority_uuid,registration_status,administrative_status)
VALUES
('de-person-dob','DATA_ELEMENT','Person.dateOfBirth','A person’s date of birth in ISO format.','ctx-default','ra-local','Recorded','Released');
INSERT OR IGNORE INTO data_element(uuid,data_element_concept_uuid,value_domain_uuid)
VALUES
('de-person-dob','dec-person-dob','vd-iso-date');

-- Designations (multi language)
INSERT OR IGNORE INTO designation(uuid,item_uuid,context_uuid,language_tag,designation,designation_type,is_preferred)
VALUES
('des-1','oc-person','ctx-default','en','Person','preferred',1),
('des-2','oc-person','ctx-default','de','Person','preferred',1),
('des-3','prop-dob','ctx-default','en','Date of Birth','preferred',1),
('des-4','prop-dob','ctx-default','de','Geburtsdatum','synonym',0);

-- Example enumerated Value Domain: Gender Code
INSERT OR IGNORE INTO registrable_item(uuid,item_type,preferred_name,definition,context_uuid,registration_authority_uuid,registration_status,administrative_status)
VALUES
('vd-gender','VALUE_DOMAIN','Gender Code','Administrative gender codes.','ctx-default','ra-local','Recorded','Released');
INSERT OR IGNORE INTO value_domain(uuid,datatype,conceptual_domain_uuid)
VALUES
('vd-gender','code',NULL);

INSERT OR IGNORE INTO permissible_value(uuid,value_domain_uuid,code,meaning,sort_order)
VALUES
('pv-g-1','vd-gender','M','Male',1),
('pv-g-2','vd-gender','F','Female',2),
('pv-g-3','vd-gender','X','Diverse/Unspecified',3);

-- Classification Scheme: Person Attributes
INSERT OR IGNORE INTO registrable_item(uuid,item_type,preferred_name,definition,context_uuid,registration_authority_uuid,registration_status,administrative_status)
VALUES
('cs-person-attr','CLASSIFICATION_SCHEME','Person Attributes','Classification scheme for person-related metadata.','ctx-default','ra-local','Recorded','Released');
INSERT OR IGNORE INTO classification_scheme(uuid,scheme_uri) VALUES ('cs-person-attr','urn:example:cs:person-attributes');

-- Classification Items
INSERT OR IGNORE INTO registrable_item(uuid,item_type,preferred_name,definition,context_uuid,registration_authority_uuid,registration_status,administrative_status)
VALUES
('ci-identity','CLASSIFICATION_ITEM','Identity','Identity related attributes.','ctx-default','ra-local','Recorded','Released'),
('ci-demographics','CLASSIFICATION_ITEM','Demographics','Demographic attributes.','ctx-default','ra-local','Recorded','Released'),
('ci-dob','CLASSIFICATION_ITEM','Birth Date','Birth date related.','ctx-default','ra-local','Recorded','Released');
INSERT OR IGNORE INTO classification_item(uuid,scheme_uuid,parent_uuid,item_code)
VALUES
('ci-identity','cs-person-attr',NULL,'IDENT'),
('ci-demographics','cs-person-attr',NULL,'DEMO'),
('ci-dob','cs-person-attr','ci-demographics','DOB');

-- Assign classifications
INSERT OR IGNORE INTO item_classification(uuid,item_uuid,classification_item_uuid,assigned_by)
VALUES
('ic-1','de-person-dob','ci-dob','Data Steward'),
('ic-2','prop-dob','ci-dob','Data Steward');

COMMIT;
