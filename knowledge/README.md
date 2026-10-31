# Fictional Policy Corpus

This directory contains fictional policy documents for HR, IT Support, and Operations. Do not place real employee, customer, credential, or production-company information here.

Every Markdown document must begin with YAML front matter containing exactly the policy identity and authorization metadata below:

```yaml
document_id: HR-LEAVE-01
title: Example Policy
domain: hr
allowed_roles: [employee, manager, hr_specialist]
allowed_regions: [US]
effective_date: 2026-01-01
version: "1.0"
status: published
owner_role: hr_specialist
review_due_date: 2027-01-01
```

`domain` must match the immediate folder name. The ingestion service fails closed for invalid metadata, unsupported roles, non-published lifecycle states, duplicate active versions, or content that cannot be chunked.
